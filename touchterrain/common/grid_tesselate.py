# grid_tesselate.py
# create triangles from a top and bottom np 2D array, including walls

'''
@author:     Chris Harding
@license:    GPL
@contact:    charding@iastate.edu

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
# CH: May  2023: modified refactored optimized version (lower memory foot print) by keerl
# CH: Apr. 2019: converted to Python 3
# CH: Feb. 2018: added use of tempfile as file buffer to lower memory footprint
# CH: Feb. 2017: added calculations for normals in stl files
# CH: Jan. 22, 16: putting the vert index behind a comment makes some programs crash
#                  when loading the obj file, so I removed those.
# FIX: (CH, Nov.16,15): make the vertex index a per grid attribute rather than
#  a vertex class attribute as this seem to index not found fail eventually when
#  multiple grids are processed together.
# CH July 2015

import io
import multiprocessing
import os
import shutil
import struct # for making binary STL
import sys

# get root logger, will later be redirected into a logfile
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from collections.abc import Sequence
from typing import Union, Any

import numpy as np
import shapely

from touchterrain.common.Vertex import vertex
from touchterrain.common.Quad import quad


from touchterrain.common.tile_info import TouchTerrainTileInfo

from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.nudge_corner import (
    IntermediateCorner,
)

from touchterrain.common.shapely_utils import flatten_geometries
from touchterrain.common.shapely_polygon_utils import (
    polygon_to_list_of_vertex,
)

from touchterrain.common.mesh_vocabulary import (
    BottomSurfaceProvider,
    Coordinate,
    EmittedBottomSurface,
    MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    PositiveZNudgePlan,
    SerializedVertexCache,
    TopFootprintProvider,
    TopFootprintSource,
    _empty_borders,
    _parallel_range_results,
    _should_parallelize_rows,
    single_job_parallel_workers,
)
from touchterrain.common.mesh_serialization import (
    _boundary_line_map_by_serialized_xy,
    _line_with_serialized_xy,
    normalize_coordinate_to_match_mesh_serialization,
)
from touchterrain.common.Cell import cell
from touchterrain.common import nudge_apply
from touchterrain.common.nudge_geometry import (
    full_cell_footprint,
)
from touchterrain.common.surface_geometry import (
    _build_cardinal_wall_borders,
    _clipped_cell_surface_polygons,
    _create_cell_bottom_geometry,
    _current_surface_footprint,
    _surface_planes_from_current_geometry,
    get_normal,
    make_wall_without_exact_duplicate_vertices,
)
from touchterrain.common.raster_interpolation import (
    _cell_corner_elevations,
    _interpolated_corner_grid,
    _zero_elevations_below_threshold,
)


BINARY_STL_FACET = struct.Struct("<12fH")
BINARY_STL_HEADER = struct.Struct("80sI")
ASCII_STL_FACET_TEMPLATE = (
    "facet normal "
    "{face[0]:.{precision}f} "
    "{face[1]:.{precision}f} "
    "{face[2]:.{precision}f}\n"
    "outer loop\n"
    "vertex "
    "{face[3]:.{precision}f} "
    "{face[4]:.{precision}f} "
    "{face[5]:.{precision}f}\n"
    "vertex "
    "{face[6]:.{precision}f} "
    "{face[7]:.{precision}f} "
    "{face[8]:.{precision}f}\n"
    "vertex "
    "{face[9]:.{precision}f} "
    "{face[10]:.{precision}f} "
    "{face[11]:.{precision}f}\n"
    "endloop\n"
    "endfacet\n"
)


def cleanup_cells_for_mesh_serialization(
    cells: np.ndarray,
    output_fileformat: str,
    split_rotation: int,
    parallel_workers: int = 1,
) -> None:
    """Clean cell geometry before serial mesh writes or topology scans."""
    def cleanup_rows(row_start: int, row_end: int) -> None:
        for row_index in range(row_start, row_end):
            serialized_vertices: SerializedVertexCache = {}
            for current_cell in cells[row_index]:
                if current_cell is not None:
                    current_cell.remove_geometry_collapsed_by_mesh_serialization(
                        output_fileformat=output_fileformat,
                        split_rotation=split_rotation,
                        serialized_vertices=serialized_vertices,
                    )

    row_count = cells.shape[0]
    worker_count = max(1, min(parallel_workers, row_count))
    if not _should_parallelize_rows(row_count, worker_count):
        cleanup_rows(0, row_count)
        return

    for _result in _parallel_range_results(
        0,
        row_count,
        worker_count,
        cleanup_rows,
    ):
        pass


class ProcessingTile:
    """Raster variants and output state needed to process one mesh tile."""

    __slots__ = (
        "tile_info",
        "top_raster_variants",
        "bottom_raster_variants",
        "bottom_surface_provider",
        "positive_contact_top_raster",
        "positive_z_nudge_plan",
        "return_grid",
        "defer_triangle_writes",
        "defer_serialization_cleanup",
    )

    tile_info: TouchTerrainTileInfo
    top_raster_variants: RasterVariants
    bottom_raster_variants: Union[None, RasterVariants]
    bottom_surface_provider: BottomSurfaceProvider | None
    positive_contact_top_raster: np.ndarray | None
    positive_z_nudge_plan: PositiveZNudgePlan | None
    return_grid: bool
    defer_triangle_writes: bool
    defer_serialization_cleanup: bool

    def __init__(
        self,
        tile_info: TouchTerrainTileInfo,
        top: RasterVariants,
        bottom: Union[None, RasterVariants],
        bottom_surface_provider: BottomSurfaceProvider | None = None,
        positive_contact_top_raster: np.ndarray | None = None,
        positive_z_nudge_plan: PositiveZNudgePlan | None = None,
        return_grid: bool = False,
        defer_triangle_writes: bool = False,
        defer_serialization_cleanup: bool = False,
    ):
        self.tile_info = tile_info
        self.top_raster_variants = top
        self.bottom_raster_variants = bottom
        self.bottom_surface_provider = bottom_surface_provider
        self.positive_contact_top_raster = positive_contact_top_raster
        self.positive_z_nudge_plan = positive_z_nudge_plan
        self.return_grid = return_grid
        self.defer_triangle_writes = defer_triangle_writes
        self.defer_serialization_cleanup = defer_serialization_cleanup

def _requested_cardinal_borders(
    padded_row: int,
    padded_col: int,
    ymaxidx: int,
    xmaxidx: int,
    borders_top_raster: np.ndarray,
    check_nan_neighbors: bool = True,
) -> set[str]:
    """Return N/S/E/W sides that need exterior walls for this cell."""
    borders: set[str] = set()
    if padded_row == 1:
        borders.add("N")
    if padded_row == ymaxidx:
        borders.add("S")
    if padded_col == 1:
        borders.add("W")
    if padded_col == xmaxidx:
        borders.add("E")

    if not check_nan_neighbors:
        return borders

    if np.isnan(borders_top_raster[padded_row - 1, padded_col]):
        borders.add("N")
    if np.isnan(borders_top_raster[padded_row + 1, padded_col]):
        borders.add("S")
    if np.isnan(borders_top_raster[padded_row, padded_col - 1]):
        borders.add("W")
    if np.isnan(borders_top_raster[padded_row, padded_col + 1]):
        borders.add("E")

    return borders


def _wall_border_edges_from_buckets(buckets: Any) -> list[BorderEdge]:
    """Return the clipping edges in a cell bucket that request walls."""
    if not isinstance(buckets, dict):
        return []
    return [
        border_edge
        for bucket in buckets.values()
        if isinstance(bucket, list)
        for border_edge in bucket
        if isinstance(border_edge, BorderEdge) and border_edge.make_wall
    ]


def _surface_polygon_edges(
    surface_polygons: Sequence[shapely.Polygon],
) -> list[shapely.LineString]:
    """Return the individual boundary lines from surface polygons."""
    return [
        geometry
        for surface_polygon in surface_polygons
        for geometry in flatten_geometries(
            geometries=[surface_polygon],
            to_single_lines=True,
        )
        if isinstance(geometry, shapely.LineString)
    ]


class grid:
    """makes cell data structure from two np arrays (top, bottom) of the same shape."""
    tile: ProcessingTile
    tile_info: TouchTerrainTileInfo
    bottom_thru_base: bool
    cells: np.ndarray | None
    positive_z_nudge_plan: PositiveZNudgePlan
    xmaxidx: int
    ymaxidx: int
    cell_size: float
    offsetx: float
    offsety: float
    num_triangles: int

    def __init__(self, tile: ProcessingTile):
        '''tile: Includes Top and Bottom raster variants and tile_info dict
        '''
        self.tile = tile
        self.tile_info = tile.tile_info

        self.bottom_thru_base = tile.tile_info.config.bottom_thru_base

        if self.tile_info.config.fileformat == "obj":
            vertex.vertex_index_dict = {}  # will be filled with vertex indices
        else:
            vertex.vertex_index_dict = -1

        self.cells = None
        self.positive_z_nudge_plan: PositiveZNudgePlan = (
            tile.positive_z_nudge_plan or {}
        )

        if tile.top_raster_variants.dilated is None:
            print("grid.init() error: No prepared top raster. tile.top_raster_variants.dilated is None")
            return None

        if tile.bottom_raster_variants is None:
            print("grid.init() error: No bottom_raster_variants passed in. bottom_raster_variants required to be passed in even if the variants are None.") # We may set bottom_raster_variants to None later to signal that we are not in "difference mesh" mode.
            return None

        # Important: in 2D np arrays, x and y coordinate are "flipped" in the sense that when printing top
        # top[0,0] appears to the upper left (NW) corner and [0,1] (East) of it:
        #[[11  12 13]       top[0,1] => 12
        # [Nan 22 23]       top[2,0] => NaN (Not a Number -> undefined elevation)
        # [31  32 33]       top[2,1] => 32
        # [41  42 43]]
        # Note: the actual array will be edge-padded which is important to be able to interpolate the border cells


        # cell size (x and y delta)
        self.cell_size = self.tile_info.pixel_mm

        # does top have NaNs?
        self.tile_info.have_nan = np.any(np.isnan(tile.top_raster_variants.dilated)) # True => we have NaN values

        bottom_dilated = tile.bottom_raster_variants.dilated
        self.tile_info.have_bot_nan = (
            isinstance(bottom_dilated, np.ndarray)
            and np.any(np.isnan(bottom_dilated))
        )

        # A missing prepared bottom means normal-mesh mode.
        if not isinstance(bottom_dilated, np.ndarray):
            tile.bottom_raster_variants = None
        # can't have a bottom_image and NaNs in top
        elif (
            self.tile_info.config.bottom_image is not None
            and self.tile_info.have_nan
        ):
            tile.bottom_raster_variants = None
            print("Top has NaN values, requested bottom image will be ignored!")

        # need to use the tilewide min/max for each tile, otherwise the boudaries don't line up perfectly!

        #
        # Convert elevation from real word elevation (m) to model print3D height (mm)
        #
        if self.tile_info.config.use_geo_coords is None: # Coordinates need to be in mm

            scz = 1 / self.tile_info.scale * 1000.0 # scale z to mm
            scale_min_elev = self.tile_info.config.min_elev

            if tile.bottom_raster_variants is not None: # Top-Bottom difference mesh mode
                if not self.bottom_thru_base:  # normal case,
                    tile.bottom_raster_variants -= scale_min_elev

                    tile.bottom_raster_variants *= scz * self.tile_info.config.zscale # apply z-scale to bottom
                    tile.bottom_raster_variants += self.tile_info.config.basethick # add base thickness to bottom

                    if tile.bottom_raster_variants.dilated is not None:
                        # Update with per-tile mm min/max
                        self.tile_info.min_bot_elev = np.nanmin(tile.bottom_raster_variants.dilated)
                        self.tile_info.max_bot_elev = np.nanmax(tile.bottom_raster_variants.dilated)
                        print("bottom min/max (mm) for tile:", self.tile_info.min_bot_elev, self.tile_info.max_bot_elev)
                    else:
                        print("tile.bottom_raster_variants.dilated not found")
                        return None
            tile.top_raster_variants -= scale_min_elev
            tile.top_raster_variants *= scz * self.tile_info.config.zscale # apply z-scale to top
            tile.top_raster_variants += self.tile_info.config.basethick # add base thickness to top

            if tile.positive_contact_top_raster is not None:
                positive_contact_top_raster = (
                    tile.positive_contact_top_raster.copy().astype(np.float64)
                )
                positive_contact_top_raster -= scale_min_elev
                positive_contact_top_raster *= scz * self.tile_info.config.zscale
                positive_contact_top_raster += self.tile_info.config.basethick
                tile.positive_contact_top_raster = positive_contact_top_raster

            # post-scale (i.e. in mm) top elevations (for this tile)
            self.tile_info.config.min_elev = np.nanmin(tile.top_raster_variants.dilated)
            self.tile_info.max_elev = np.nanmax(tile.top_raster_variants.dilated)
            print("top min/max for tile (mm):", self.tile_info.config.min_elev, self.tile_info.max_elev)

        else:  # using geo coords (UTM, meter based) - thickness is meters
            # TODO: Just noticed that we don't apply a z-scale to the top. Not sure if we should
            tile.bottom_raster_variants.dilated = self.tile_info.config.min_elev - self.tile_info.config.basethick * 10
            logger.info("Using geo coords with a base thickness of " + str(self.tile_info.config.basethick * 10) + " meters")

        # After this point, all values are in real print3D units (mm) and 0 is the bottom.

        # max index in x and y for "inner" raster
        self.xmaxidx = tile.top_raster_variants.dilated.shape[1]-2
        self.ymaxidx = tile.top_raster_variants.dilated.shape[0]-2
        # offset so that 0/0 is the center of this tile (local) or so that 0/0 is the lower left corner of all tiles (global)
        if not self.tile_info.config.tile_centered: # global offset, best for looking at all tiles together
            self.offsetx = -self.tile_info.tile_width  * (self.tile_info.tile_no_x-1)  # tile_no starts with 1! This is the top end of the tile, not 0!
            self.offsety = -self.tile_info.tile_height * (self.tile_info.tile_no_y-1)  + self.tile_info.tile_height * self.tile_info.config.ntilesy

        else: # local centered for printing
            self.offsetx = self.tile_info.tile_width / 2.0
            self.offsety = self.tile_info.tile_height / 2.0

        # geo coords are in meters (UTM). tile_centered is ignored for geo coords
        if self.tile_info.config.use_geo_coords is not None:

            geo_transform = self.tile_info.geo_transform
            self.cell_size = abs(geo_transform[1]) # rw pixel size of geotiff in m
            tile_width_m  = self.xmaxidx * self.cell_size # number of (unpadded) pixels of current tile
            tile_height_m = self.ymaxidx * self.cell_size

            # Place the tiles so that the center is at 0/0, which is what Blender GIS needs.
            if self.tile_info.config.use_geo_coords == "centered":

                self.offsetx = -tile_width_m  * (self.tile_info.tile_no_x-1)
                self.offsety = tile_height_m  * self.tile_info.config.ntilesy - tile_height_m * (self.tile_info.tile_no_y-1)

                # center by half the total size
                self.offsetx += (self.tile_info.full_raster_width * self.cell_size) / 2
                self.offsety -= (self.tile_info.full_raster_height * self.cell_size) / 2

                # correct for off-by-1 cells
                self.offsetx -= self.cell_size
                self.offsety += self.cell_size

            # size in meters but the UTM zone's origin is used, i.e. each vertex is in full
            # UTM coordinates. Not sure what CAD/modelling system uses that but if needed it's an option.
            else:  # "UTM"

                self.offsetx = -tile_width_m  * (self.tile_info.tile_no_x-1)
                self.offsety = -tile_height_m * (self.tile_info.tile_no_y-1)

                self.offsetx = -geo_transform[0] + self.offsetx # UTM x of upper left corner
                self.offsety =  geo_transform[3] + self.offsety # UTM y


        # put corner coordinates tile info dict (may later be needed for 2 bottom triangles)
        if not self.tile_info.config.tile_centered:
            self.tile_info.W = self.tile_info.tile_width  * (self.tile_info.tile_no_x-1)
            self.tile_info.E = self.tile_info.W + self.tile_info.tile_width
            tot_height = self.tile_info.tile_height * self.tile_info.config.ntilesy
            # y tiles index goes top(0) DOWN to bottom
            self.tile_info.N = tot_height - (self.tile_info.tile_height * (self.tile_info.tile_no_y-1))
            self.tile_info.S = self.tile_info.N - self.tile_info.tile_height
        else:
            self.tile_info.W = -self.tile_info.tile_width / 2
            self.tile_info.E =  self.tile_info.tile_width / 2
            self.tile_info.S = -self.tile_info.tile_height / 2
            self.tile_info.N =  self.tile_info.tile_height / 2

    def extract_emitted_top_bottom_surfaces(self) -> BottomSurfaceProvider:
        """Return each emitted top surface reoriented as bottom geometry."""
        if self.cells is None:
            raise RuntimeError("Cannot extract surfaces before cells exist.")

        def surfaces_for_rows(
            row_start: int,
            row_end: int,
        ) -> BottomSurfaceProvider:
            output: BottomSurfaceProvider = []
            for row_index in range(row_start, row_end):
                surface_row: list[EmittedBottomSurface] = []
                for current_cell in self.cells[row_index]:
                    if current_cell is None:
                        surface_row.append((None, None))
                    else:
                        surface_row.append(
                            current_cell.emitted_top_as_bottom_surfaces()
                        )
                output.append(surface_row)
            return output

        row_count = self.cells.shape[0]
        worker_count = single_job_parallel_workers(
            getattr(self.tile_info, "config", None),
            row_count,
        )
        if not _should_parallelize_rows(row_count, worker_count):
            return surfaces_for_rows(0, row_count)

        surfaces: BottomSurfaceProvider = []
        for surface_rows in _parallel_range_results(
            0,
            row_count,
            worker_count,
            surfaces_for_rows,
        ):
            surfaces.extend(surface_rows)
        return surfaces

    def extract_emitted_top_footprints(self) -> TopFootprintProvider:
        """Return each cell's current emitted top footprint."""
        if self.cells is None:
            raise RuntimeError("Cannot extract footprints before cells exist.")

        def footprints_for_rows(
            row_start: int,
            row_end: int,
        ) -> TopFootprintProvider:
            output: TopFootprintProvider = []
            for row_index in range(row_start, row_end):
                footprint_row: list[TopFootprintSource | None] = []
                for col_index, current_cell in enumerate(
                    self.cells[row_index],
                ):
                    if current_cell is None:
                        footprint_row.append(None)
                        continue

                    W, E, N, S = self.cell_bounds(
                        row_index + 1,
                        col_index + 1,
                    )
                    full_footprint = full_cell_footprint(W, E, N, S)
                    footprint = _current_surface_footprint(
                        current_cell.topSurfacePolygons,
                        full_footprint,
                        current_cell.topquad,
                    )
                    has_surface_planes = bool(
                        _surface_planes_from_current_geometry(
                            current_cell.topquad,
                            current_cell.topSurfacePolygons,
                            self.tile_info.config.split_rotation,
                        )
                    )
                    if footprint.is_empty or not has_surface_planes:
                        footprint_row.append(None)
                    else:
                        footprint_row.append(footprint)
                output.append(footprint_row)
            return output

        row_count = self.cells.shape[0]
        worker_count = single_job_parallel_workers(
            getattr(self.tile_info, "config", None),
            row_count,
        )
        if not _should_parallelize_rows(row_count, worker_count):
            return footprints_for_rows(0, row_count)

        footprints: TopFootprintProvider = []
        for footprint_rows in _parallel_range_results(
            0,
            row_count,
            worker_count,
            footprints_for_rows,
        ):
            footprints.extend(footprint_rows)
        return footprints

    def cell_bounds(
        self,
        padded_row: int,
        padded_col: int,
    ) -> tuple[float, float, float, float]:
        """Return W/E/N/S coordinates for a padded raster cell location."""
        W = (padded_col - 1) * self.cell_size - self.offsetx
        E = W + self.cell_size
        N = -((padded_row - 1) * self.cell_size) + self.offsety
        S = N - self.cell_size
        return W, E, N, S

    def _can_skip_simple_serialization_cleanup(
        self,
        using_difference_mesh: bool,
        nudge_enabled: bool,
    ) -> bool:
        """Return whether ordinary rectangular cells can skip cleanup."""
        return (
            not using_difference_mesh
            and not nudge_enabled
            and not self.tile_info.have_nan
            and self.tile.bottom_surface_provider is None
            and self.tile.top_raster_variants.polygon_intersection_geometry
            is None
            and self.tile.top_raster_variants.polygon_intersection_edge_buckets
            is None
            and (
                self.tile.top_raster_variants
                .polygon_intersection_contains_properly
            )
            is None
            and self.tile_info.config.bottom_image is None
        )

    def _cell_xy_survives_mesh_serialization(
        self,
        W: float,
        E: float,
        N: float,
        S: float,
        output_fileformat: str,
    ) -> bool:
        """Return whether the rectangular cell footprint has output area."""
        output_w = normalize_coordinate_to_match_mesh_serialization(
            W,
            output_fileformat,
        )
        output_e = normalize_coordinate_to_match_mesh_serialization(
            E,
            output_fileformat,
        )
        output_n = normalize_coordinate_to_match_mesh_serialization(
            N,
            output_fileformat,
        )
        output_s = normalize_coordinate_to_match_mesh_serialization(
            S,
            output_fileformat,
        )
        return output_w != output_e and output_n != output_s

    def apply_positive_z_plan_to_existing_cells(
        self,
        positive_z_nudge_plan: PositiveZNudgePlan,
        positive_contact_top_raster: np.ndarray | None = None,
        positive_z_difference_top_footprints: (
            TopFootprintProvider | None
        ) = None,
    ) -> None:
        """Delegate to nudge_apply.apply_positive_z_plan_to_existing_cells()."""
        return nudge_apply.apply_positive_z_plan_to_existing_cells(
            self,
            positive_z_nudge_plan=positive_z_nudge_plan,
            positive_contact_top_raster=positive_contact_top_raster,
            positive_z_difference_top_footprints=positive_z_difference_top_footprints,
        )

    def _add_unmatched_cardinal_surface_walls(
        self,
        positive_z_nudge_plan: PositiveZNudgePlan,
        split_rotation: int,
        output_fileformat: str,
    ) -> None:
        """Delegate to nudge_apply._add_unmatched_cardinal_surface_walls()."""
        return nudge_apply._add_unmatched_cardinal_surface_walls(
            self,
            positive_z_nudge_plan=positive_z_nudge_plan,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
        )

    def _close_local_positive_z_boundary_edge_loops(
        self,
        positive_z_nudge_plan: PositiveZNudgePlan,
        split_rotation: int,
        output_fileformat: str,
    ) -> None:
        """Delegate to nudge_apply._close_local_positive_z_boundary_edge_loops()."""
        return nudge_apply._close_local_positive_z_boundary_edge_loops(
            self,
            positive_z_nudge_plan=positive_z_nudge_plan,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
        )

    def create_cells(self):
        '''Creates a data structure for each raster cell based on quads for top, any walls and possible bottom.
        Once created, each cell is converted into triangles for each file format, which are stored as a stream buffer (self.s)
        If using temp files, this buffer serves as a cache for occasionally writing to disk (self.fo)
        Note that for obj, two streams/files are needed, one for indices that define the vertices for each triangle and one
        for vertex coordinates. Here, only the index part (s[1] and fo[1]) is stored, the vertex coordinates will be
        created and stored later based on the keys of the vertex class attribute vertex_index_dict'''
        if self.tile_info is None:
            print("create_cells: Error: self.tile_info is None")
            return

        # Cells that are not emitted remain explicit None entries.
        self.cells = np.full(
            (self.ymaxidx, self.xmaxidx),
            None,
            dtype=object,
        )

        # report progress in %
        percent = 10
        pc_step = int(self.ymaxidx/percent) + 1
        progress = 0
        print("creating internal triangle data structure for", multiprocessing.current_process(), file=sys.stderr)
        output_fileformat = self.tile_info.config.fileformat
        split_rotation = self.tile_info.config.split_rotation
        top_variants = self.tile.top_raster_variants
        bottom_variants = self.tile.bottom_raster_variants
        using_difference_mesh = bottom_variants is not None
        top_dilated = top_variants.dilated
        top: np.ndarray | None = top_dilated
        if using_difference_mesh and self.tile_info.config.bottom_thru_base:
            top = bottom_variants.nan_close
        borders_top_raster: np.ndarray | None = top_dilated
        if using_difference_mesh and self.bottom_thru_base:
            borders_top_raster = top_variants.nan_close
        polygon_contains_properly = (
            top_variants.polygon_intersection_contains_properly
        )
        polygon_intersection_geometry = (
            top_variants.polygon_intersection_geometry
        )
        polygon_edge_buckets = top_variants.polygon_intersection_edge_buckets
        nudge_enabled = (
            self.tile_info.config.nudge_in_overused_edges_vertex
            and not self.tile_info.config.no_bottom
        )
        skip_simple_serialization_cleanup = (
            self._can_skip_simple_serialization_cleanup(
                using_difference_mesh,
                nudge_enabled,
            )
        )
        emit_cell_bottom = (
            not self.tile_info.config.no_bottom
            and (
                self.tile_info.have_nan
                or using_difference_mesh
                or nudge_enabled
            )
        )

        if not self.tile_info.have_nan:
            top_interpolation_raster = top_dilated
        elif top_variants.edge_interpolation is not None:
            top_interpolation_raster = top_variants.edge_interpolation
        else:
            top_interpolation_raster = top_variants.original
        top_corner_elevations = _interpolated_corner_grid(
            top_interpolation_raster,
        )
        bottom_raster_for_z0_nudge: np.ndarray | None = None
        bottom_corner_elevations: np.ndarray | None = None
        if using_difference_mesh and not self.bottom_thru_base:
            if self.tile_info.have_bot_nan:
                bottom_raster_for_z0_nudge = (
                    bottom_variants.original
                )
            else:
                bottom_raster_for_z0_nudge = (
                    bottom_variants.dilated
                )
            bottom_corner_elevations = _interpolated_corner_grid(
                bottom_raster_for_z0_nudge,
            )

        nudge_settings = nudge_apply.build_nudge_settings(
            nudge_enabled=nudge_enabled,
            existing_plan=self.tile.positive_z_nudge_plan,
            positive_contact_top_raster=(
                self.tile.positive_contact_top_raster
            ),
            top_interpolation_raster=top_interpolation_raster,
            split_emit_raster=top_variants.dilated,
            bottom_raster_for_z0_nudge=bottom_raster_for_z0_nudge,
            using_difference_mesh=using_difference_mesh,
            has_bottom_surface_provider=(
                self.tile.bottom_surface_provider is not None
            ),
            cell_size=self.cell_size,
            offsetx=self.offsetx,
            offsety=self.offsety,
            ymaxidx=self.ymaxidx,
            xmaxidx=self.xmaxidx,
            zero_threshold=self.tile_info.config.basethick,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
            config=self.tile_info.config,
            parallel_task_count=self.ymaxidx,
        )
        self.positive_z_nudge_plan = nudge_settings.plan
        cell_size = self.cell_size
        offsetx = self.offsetx
        offsety = self.offsety

        for j in range(1, self.ymaxidx+1):# y dimension for looping within the +1 padded raster
            cell_row = j - 1
            N = -(cell_row * cell_size) + offsety
            S = N - cell_size
            serialized_row_vertices: SerializedVertexCache = {}
            if j % pc_step == 0:
                progress += percent
                print(progress, "%", multiprocessing.current_process(), file=sys.stderr)

            for i in range(1, self.xmaxidx + 1):# x dim.
                cell_col = i - 1
                # A NaN center is outside the emitted raster footprint.
                if self.tile_info.have_nan and np.isnan(top[j, i]):
                    continue

                # XY cell bounds use the upper-left raster origin.
                W = cell_col * cell_size - offsetx
                E = W + cell_size
                top_elevations = _cell_corner_elevations(
                    top_corner_elevations,
                    i,
                    j,
                )
                if np.isnan(top_elevations).any():
                    continue
                if self.tile_info.have_nan:
                    # Restore the zero base after edge interpolation used a
                    # value just below basethick as its fill elevation.
                    top_elevations = _zero_elevations_below_threshold(
                        top_elevations,
                        self.tile_info.config.basethick,
                    )
                (
                    top_ne_elevation,
                    top_nw_elevation,
                    top_se_elevation,
                    top_sw_elevation,
                ) = top_elevations

                # This vertex order emits counterclockwise top triangles.
                topq = quad(
                    vertex(W, N, top_nw_elevation),
                    vertex(W, S, top_sw_elevation),
                    vertex(E, S, top_se_elevation),
                    vertex(E, N, top_ne_elevation),
                )

                top_bottom_surface_geometries_2D: list[shapely.Geometry] | None = None
                if (
                    polygon_contains_properly is not None
                    and polygon_intersection_geometry is not None
                    and not polygon_contains_properly[cell_row][cell_col]
                ):
                    top_bottom_surface_geometries_2D = (
                        polygon_intersection_geometry[cell_row][cell_col]
                    )

                if not using_difference_mesh or self.bottom_thru_base:
                    bottom_elevations = (0, 0, 0, 0)
                else:
                    if bottom_corner_elevations is None:
                        raise RuntimeError(
                            "Difference mesh corner elevations are missing."
                        )
                    bottom_elevations = _cell_corner_elevations(
                        bottom_corner_elevations,
                        i,
                        j,
                    )
                    if np.isnan(bottom_elevations).any():
                        continue
                    if self.tile_info.have_bot_nan:
                        bottom_elevations = (
                            _zero_elevations_below_threshold(
                                bottom_elevations,
                                self.tile_info.config.basethick,
                            )
                        )
                botq = None
                bottom_corner_vertices: dict[IntermediateCorner, vertex] | None = None

                if not skip_simple_serialization_cleanup:
                    # These vertices may become emitted bottom surfaces, walls,
                    # or source planes for clipped/nudged cells.
                    (
                        botq,
                        bottom_corner_vertices,
                    ) = _create_cell_bottom_geometry(
                        W,
                        E,
                        N,
                        S,
                        *bottom_elevations,
                        nudge_enabled,
                    )

                top_surface_polygons_triangulated_3D = None
                bottom_surface_polygons_triangulated_3D = None
                clipped_surfaces_collapsed_after_output = False
                if top_bottom_surface_geometries_2D is not None:
                    if botq is None:
                        raise RuntimeError(
                            "Clipped cell surface creation needs a bottom quad."
                        )
                    (
                        top_surface_polygons_triangulated_3D,
                        bottom_surface_polygons_triangulated_3D,
                        clipped_surfaces_collapsed_after_output,
                    ) = _clipped_cell_surface_polygons(
                        top_bottom_surface_geometries_2D,
                        topq,
                        botq,
                        split_rotation,
                        output_fileformat,
                    )

                # Repair overused Z=0 and positive-Z contacts before any
                # walls exist for this cell.
                nudge_outcome = nudge_apply.nudge_cell_surfaces(
                    nudge_settings,
                    j=j,
                    i=i,
                    topq=topq,
                    botq=botq,
                    bottom_corner_vertices=bottom_corner_vertices,
                    bottom_elevations=bottom_elevations,
                    top_bottom_surface_geometries_2D=(
                        top_bottom_surface_geometries_2D
                    ),
                    top_surface_polygons_triangulated_3D=(
                        top_surface_polygons_triangulated_3D
                    ),
                    bottom_surface_polygons_triangulated_3D=(
                        bottom_surface_polygons_triangulated_3D
                    ),
                    clipped_surfaces_collapsed_after_output=(
                        clipped_surfaces_collapsed_after_output
                    ),
                    W=W,
                    E=E,
                    N=N,
                    S=S,
                )
                top_surface_polygons_triangulated_3D = (
                    nudge_outcome.top_polygons
                )
                bottom_surface_polygons_triangulated_3D = (
                    nudge_outcome.bottom_polygons
                )
                clipped_surfaces_collapsed_after_output = (
                    nudge_outcome.surfaces_collapsed
                )
                if nudge_outcome.bottomquad is not None:
                    botq = nudge_outcome.bottomquad

                if clipped_surfaces_collapsed_after_output:
                    continue

                requested_cardinal_sides = _requested_cardinal_borders(
                    j,
                    i,
                    self.ymaxidx,
                    self.xmaxidx,
                    borders_top_raster,
                    check_nan_neighbors=self.tile_info.have_nan,
                )

                # Materialize only the requested exterior walls.
                if requested_cardinal_sides:
                    if botq is None:
                        (
                            botq,
                            bottom_corner_vertices,
                        ) = _create_cell_bottom_geometry(
                            W,
                            E,
                            N,
                            S,
                            *bottom_elevations,
                            nudge_enabled,
                        )
                    borders = _build_cardinal_wall_borders(
                        requested_cardinal_sides,
                        topq.vl,
                        botq.vl,
                        output_fileformat,
                    )
                else:
                    borders = _empty_borders()

                # create borders if there is a top surface polygon using the edge buckets
                surface_polygon_borders_3D: list[quad] | None = None
                buckets = (
                    polygon_edge_buckets[cell_row][cell_col]
                    if polygon_edge_buckets is not None
                    else None
                )
                if buckets is not None:
                    wall_border_edges = _wall_border_edges_from_buckets(
                        buckets,
                    )

                    if (
                        top_bottom_surface_geometries_2D
                        and top_surface_polygons_triangulated_3D
                        and bottom_surface_polygons_triangulated_3D
                    ):
                        top_edges_by_key = _boundary_line_map_by_serialized_xy(
                            _surface_polygon_edges(
                                top_surface_polygons_triangulated_3D,
                            ),
                            output_fileformat,
                        )
                        bottom_edges_by_key = (
                            _boundary_line_map_by_serialized_xy(
                                _surface_polygon_edges(
                                    bottom_surface_polygons_triangulated_3D,
                                ),
                                output_fileformat,
                            )
                        )

                        serialized_border_lines = [
                            border_line
                            for border_edge in wall_border_edges
                            for border_line in [
                                _line_with_serialized_xy(
                                    border_edge.geometry,
                                    output_fileformat,
                                )
                            ]
                            if border_line is not None
                        ]
                        wall_border_linework = (
                            shapely.union_all(serialized_border_lines)
                            if serialized_border_lines
                            else shapely.GeometryCollection()
                        )

                        # Build one wall for each emitted clipped surface edge
                        # covered by this cell's wall border linework.
                        for edge_key, top_edge_matches in (
                            top_edges_by_key.items()
                        ):
                            edge_line = shapely.LineString(
                                [edge_key[0], edge_key[1]],
                            )
                            if not wall_border_linework.covers(edge_line):
                                continue

                            bottom_edge_matches = bottom_edges_by_key.get(
                                edge_key,
                                [],
                            )
                            if len(top_edge_matches) != len(
                                bottom_edge_matches,
                            ):
                                raise RuntimeError(
                                    "Border creation found different top and "
                                    "bottom edge match counts."
                                )

                            for top_edge_match, bottom_edge_match in zip(
                                top_edge_matches,
                                bottom_edge_matches,
                            ):
                                # Success condition where wall border linework
                                # covers a top/bottom surface edge pair.
                                top_edge_v0 = vertex(*top_edge_match.coords[1])
                                top_edge_v1 = vertex(*top_edge_match.coords[0])
                                bot_edge_v0 = vertex(
                                    *bottom_edge_match.coords[1],
                                )
                                bot_edge_v1 = vertex(
                                    *bottom_edge_match.coords[0],
                                )
                                tb_wall = make_wall_without_exact_duplicate_vertices(
                                    top_edge_v0,
                                    top_edge_v1,
                                    bot_edge_v0,
                                    bot_edge_v1,
                                    output_fileformat=output_fileformat,
                                )
                                if tb_wall is not None:
                                    if surface_polygon_borders_3D is None:
                                        surface_polygon_borders_3D = []
                                    surface_polygon_borders_3D.append(tb_wall)
                            # create border geometry with top and bot edge
                            # top and bot edges are in CW order (viewed from top) from shapely
                (
                    surface_polygon_borders_3D,
                    borders,
                ) = nudge_apply.rebuild_nudged_cell_borders(
                    nudge_outcome,
                    top_surface_polygons_triangulated_3D,
                    bottom_surface_polygons_triangulated_3D,
                    borders,
                    surface_polygon_borders_3D,
                    W=W,
                    E=E,
                    N=N,
                    S=S,
                    output_fileformat=output_fileformat,
                )

                c = cell(
                    topq,
                    botq if emit_cell_bottom else None,
                    borders,
                )

                # set surface polygons for cell if clipping border affects this cell
                if top_surface_polygons_triangulated_3D:
                    c.topSurfacePolygons = top_surface_polygons_triangulated_3D
                if bottom_surface_polygons_triangulated_3D:
                    c.bottomSurfacePolygons = bottom_surface_polygons_triangulated_3D
                if surface_polygon_borders_3D:
                    c.surfacePolygonBorders = surface_polygon_borders_3D

                if (
                    self.tile.bottom_surface_provider is not None
                    and not nudge_outcome.nudge_owns_bottom_surface()
                ):
                    bottom_provider = self.tile.bottom_surface_provider
                    bottom_quad, bottom_polygons = (
                        bottom_provider[cell_row][cell_col]
                    )
                    if bottom_quad is None and bottom_polygons is None:
                        if (
                            c.bottomquad is None
                            and c.bottomSurfacePolygons is None
                        ):
                            raise RuntimeError(
                                "Interlocking pair difference cell needs a "
                                "bottom surface at "
                                f"row={cell_row}, col={cell_col}."
                            )
                    else:
                        c.replace_bottom_surfaces(
                            bottom_surface_quad=bottom_quad,
                            bottom_surface_polygons=bottom_polygons,
                            split_rotation=split_rotation,
                            output_fileformat=output_fileformat,
                        )

                preservation = nudge_apply.finish_cell_nudge(
                    nudge_settings,
                    nudge_outcome,
                    c,
                    W=W,
                    E=E,
                    N=N,
                    S=S,
                )
                preserve_zero_height_xy = (
                    preservation.xy if preservation is not None else None
                )
                preserve_zero_height_edges = (
                    preservation.edges if preservation is not None else None
                )

                if (
                    using_difference_mesh or nudge_enabled
                ):
                    c.remove_zero_height_volumes(
                        split_rotation=split_rotation,
                        output_fileformat=output_fileformat,
                        preserve_zero_height_xy=preserve_zero_height_xy,
                        preserve_zero_height_edges=preserve_zero_height_edges,
                        serialized_vertices=serialized_row_vertices,
                    )

                nudge_apply.finish_positive_z_difference_nudge(
                    nudge_settings,
                    nudge_outcome,
                    c,
                    W=W,
                    E=E,
                    N=N,
                    S=S,
                    bottom_surface_provider=(
                        self.tile.bottom_surface_provider
                    ),
                    cell_row=cell_row,
                    cell_col=cell_col,
                    serialized_vertices=serialized_row_vertices,
                )

                # if we have nan cells, do some postprocessing on this cell to get rid of stair case patterns
                # This will create special triangle cells that have a triangle of any orientation at top/bottom, which
                # are flagged as is_tri_cell = True, and have only v0, v1 and v2. One border is deleted, the other
                # is set as a diagonal wall.
                # Note: this will not be done if we have a bottom as it will lead to lots of triangle holes!
                if (
                    self.tile_info.have_nan
                    and self.tile_info.config.smooth_borders
                    and not using_difference_mesh
                ):
                    if c.check_for_tri_cell():
                        c.convert_to_tri_cell()

                # Normalize and remove geometry that would collapse during mesh
                # serialization before storing the cell.
                if (
                    not self.tile.defer_serialization_cleanup
                    and not (
                        skip_simple_serialization_cleanup
                        and self._cell_xy_survives_mesh_serialization(
                            W,
                            E,
                            N,
                            S,
                            output_fileformat,
                        )
                    )
                ):
                    c.remove_geometry_collapsed_by_mesh_serialization(
                        output_fileformat=output_fileformat,
                        split_rotation=split_rotation,
                        serialized_vertices=serialized_row_vertices,
                    )

                self.cells[cell_row, cell_col] = c

                if not self.tile.defer_triangle_writes:
                    self.write_cell_meshes_to_buffer(c)

        print("100%", multiprocessing.current_process(), "\n", file=sys.stderr)

    def write_cell_meshes_to_buffer(
        self,
        current_cell: cell,
        coordinates_normalized: bool = False,
    ) -> None:
        """Write one finalized cell's meshes to the current output buffer."""
        if self._uses_fast_binary_stl_no_normals_writer():
            self._write_cell_meshes_to_binary_stl_no_normals(
                current_cell,
                coordinates_normalized,
            )
            return

        def triangle_rounded_to_precision(
            decimals: int,
            triangle: list[vertex],
        ) -> list[vertex]:
            output: list[vertex] = []
            for tv in triangle:
                output.append(
                    tv.vertex_rounded_to_precision(
                        decimals=decimals,
                    )
                )
            return output

        decimal_precision = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION
        for q in current_cell.iter_meshes_for_model():
            if isinstance(q, quad):
                quad_triangles = q.get_triangles(
                    split_rotation=self.tile_info.config.split_rotation,
                )
                for t in quad_triangles:
                    self.write_triangle_to_buffer(
                        tuple(
                            triangle_rounded_to_precision(
                                decimals=decimal_precision,
                                triangle=list(t),
                            )
                        )
                    )
            elif isinstance(q, shapely.Polygon):
                t0 = polygon_to_list_of_vertex(polygon=q)
                if len(t0) == 4 and t0[0].coords == t0[3].coords:
                    self.write_triangle_to_buffer(
                        tuple(
                            triangle_rounded_to_precision(
                                decimals=decimal_precision,
                                triangle=list(t0[:3]),
                            )
                        )
                    )
                else:
                    raise ValueError(
                        "create_cells: found a polygon to write to buffer "
                        "that is not a triangle. Expected a tri of length "
                        "3+1=4 and [0]==[3] vertex. Polygon had vertex "
                        f"count f{len(t0)}."
                    )

    def _uses_fast_binary_stl_no_normals_writer(self) -> bool:
        """Return whether triangles can be serialized without vertex objects."""
        return (
            self.tile_info.config.fileformat == "STLb"
            and self.tile_info.config.no_normals is True
        )

    def _write_triangle_coords_to_binary_stl_no_normals(
        self,
        triangle: Sequence[Coordinate],
        coordinates_normalized: bool = False,
    ) -> None:
        """Write one no-normal binary STL triangle from raw coordinates."""
        self.num_triangles += 1
        write = self.s.write
        pack_facet = BINARY_STL_FACET.pack
        c0, c1, c2 = triangle
        if coordinates_normalized:
            write(
                pack_facet(
                    0.0,
                    0.0,
                    0.0,
                    c0[0] + 0.0,
                    c0[1] + 0.0,
                    c0[2] + 0.0,
                    c1[0] + 0.0,
                    c1[1] + 0.0,
                    c1[2] + 0.0,
                    c2[0] + 0.0,
                    c2[1] + 0.0,
                    c2[2] + 0.0,
                    0,
                )
            )
            if self.tile_info.temp_file is not None:
                self.write_buffer_to_file()
            return

        decimal_precision = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION
        round_coord = round
        to_float = float
        write(
            pack_facet(
                0.0,
                0.0,
                0.0,
                round_coord(to_float(c0[0]), decimal_precision) + 0.0,
                round_coord(to_float(c0[1]), decimal_precision) + 0.0,
                round_coord(to_float(c0[2]), decimal_precision) + 0.0,
                round_coord(to_float(c1[0]), decimal_precision) + 0.0,
                round_coord(to_float(c1[1]), decimal_precision) + 0.0,
                round_coord(to_float(c1[2]), decimal_precision) + 0.0,
                round_coord(to_float(c2[0]), decimal_precision) + 0.0,
                round_coord(to_float(c2[1]), decimal_precision) + 0.0,
                round_coord(to_float(c2[2]), decimal_precision) + 0.0,
                0,
            )
        )
        if self.tile_info.temp_file is not None:
            self.write_buffer_to_file()

    def _write_cell_meshes_to_binary_stl_no_normals(
        self,
        current_cell: cell,
        coordinates_normalized: bool = False,
    ) -> None:
        """Write finalized cell meshes through the fast binary STL path."""
        split_rotation = self.tile_info.config.split_rotation
        for mesh in current_cell.iter_meshes_for_model():
            if isinstance(mesh, quad):
                for triangle in mesh.get_triangles(
                    split_rotation=split_rotation,
                ):
                    self._write_triangle_coords_to_binary_stl_no_normals(
                        tuple(v.coords for v in triangle),
                        coordinates_normalized,
                    )
            elif isinstance(mesh, shapely.Polygon):
                coords = mesh.exterior.coords
                if len(coords) == 4 and coords[0] == coords[3]:
                    self._write_triangle_coords_to_binary_stl_no_normals(
                        (coords[0], coords[1], coords[2]),
                        coordinates_normalized,
                    )
                else:
                    raise ValueError(
                        "create_cells: found a polygon to write to buffer "
                        "that is not a triangle. Expected a tri of length "
                        "3+1=4 and [0]==[3] vertex. Polygon had vertex "
                        f"count f{len(coords)}."
                    )

    def _cleanup_cell_for_mesh_serialization(
        self,
        current_cell: cell,
    ) -> None:
        """Normalize and drop cell geometry that cannot serialize."""
        current_cell.remove_geometry_collapsed_by_mesh_serialization(
            output_fileformat=self.tile_info.config.fileformat,
            split_rotation=self.tile_info.config.split_rotation,
        )

    def _cleanup_existing_cells_for_serialization(
        self,
        parallel_workers: int | None = None,
    ) -> None:
        """Clean deferred cells before serial mesh writes."""
        if self.cells is None:
            raise RuntimeError("Cannot clean cells before create_cells().")

        worker_count = (
            parallel_workers
            if parallel_workers is not None
            else single_job_parallel_workers(
                self.tile_info.config,
                self.cells.shape[0],
            )
        )
        cleanup_cells_for_mesh_serialization(
            self.cells,
            self.tile_info.config.fileformat,
            self.tile_info.config.split_rotation,
            worker_count,
        )

    def write_existing_cells_to_buffer(
        self,
        parallel_cleanup_workers: int | None = None,
    ) -> None:
        """Write already-created cells to the current output buffer."""
        if self.cells is None:
            raise RuntimeError("Cannot write cells before create_cells().")

        if self.tile_info.config.fileformat != "obj":
            self._cleanup_existing_cells_for_serialization(
                parallel_cleanup_workers,
            )
            for row in self.cells:
                for current_cell in row:
                    if current_cell is not None:
                        self.write_cell_meshes_to_buffer(
                            current_cell,
                            coordinates_normalized=True,
                        )
            return

        for row in self.cells:
            for current_cell in row:
                if current_cell is not None:
                    self._cleanup_cell_for_mesh_serialization(current_cell)
                    self.write_cell_meshes_to_buffer(current_cell)

    def _should_add_simple_bottom(self) -> bool:
        """Return whether this grid should add one tile-wide bottom."""
        if self.tile_info.config.no_bottom:
            return False
        if self.tile_info.have_nan:
            return False
        if (
            self.tile_info.config.bottom_image is not None
            or self.tile_info.config.bottom_elevation is not None
        ):
            return False
        return not self.tile_info.config.nudge_in_overused_edges_vertex

    def _add_simple_bottom_to_buffer(self) -> None:
        """Add the two-triangle tile bottom used by simple normal meshes."""
        v0 = vertex(self.tile_info.W, self.tile_info.S, 0)
        v1 = vertex(self.tile_info.E, self.tile_info.S, 0)
        v2 = vertex(self.tile_info.E, self.tile_info.N, 0)
        v3 = vertex(self.tile_info.W, self.tile_info.N, 0)

        self.write_triangle_to_buffer((v0, v2, v1))
        self.write_triangle_to_buffer((v0, v3, v2))

    def write_triangle_to_buffer(self, t: tuple[vertex, ...]) -> None:
        """Write a triangle to the in-memory output buffer."""
        self.num_triangles += 1

        # Create triangle coords list, for STL including normal coords (no normals for obj)
        if self.tile_info.config.fileformat != "obj":
            tl = (
                get_normal(t)
                if not self.tile_info.config.no_normals
                else [0, 0, 0]
            )
            for v in t:
                coords = v.get() # get() => list of coords [x,y,z]
                # pack 64 bit float to 32 bit and unpack 32 bit back to 64 bit to try to get the same value represented in 32 bit
                #coords = tuple(map(lambda x: struct.unpack('<f', struct.pack('<f', x))[0], coords))
                # add 0.0 to value to force -0 value to +0
                coords = tuple(coord + 0.0 for coord in coords)
                tl.extend(coords) # like append() but extend() unpacks that list!
            tl.append(0) # append attribute byte 0

        if self.tile_info.config.fileformat == "STLb":
            # en.wikipedia.org/wiki/STL_%28file_format%29#Binary_STL
            self.s.write(BINARY_STL_FACET.pack(*tl))  # append to s

        elif self.tile_info.config.fileformat == "STLa":
            self.s.write(
                ASCII_STL_FACET_TEMPLATE.format(
                    face=tl,
                    precision=MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
                )
            )

        elif self.tile_info.config.fileformat == "obj":
            # add facet indices to index stream buffer
            vl = [v.get_id() + 1 for v in t] # vertex list +1 b/c obj indices start at 1
            self.s[1].write(f"f {vl[0]}, {vl[1]}, {vl[2]}\n")

        # for STL maybe write to temp file. This can't work for obj b/c we need the full list
        # of tri indices first. Once we have that, we can create a buffer/tempfile
        if (
            self.tile_info.config.fileformat != "obj"
            and self.tile_info.temp_file is not None
        ):
            self.write_buffer_to_file()

    def write_buffer_to_file(self, flush=False, chunk_size=100000):
        # write buffer to file every 10k triangles
        # chunksize is the number of triangles that need to have been collected into the buffer in order to actually write to disk. (cache)
        # flusk=True forces a write: use this to flush whatever is in the buffer.  Will NOT close the file!
        # for obj, write only the indices [1], vertices [0] will be done later

        # Only write to file if we're actually using temp files, otherwise just bail out
        if self.tile_info.temp_file is None:
            return

        if self.num_triangles % chunk_size == 0 or flush:
            if self.tile_info.config.fileformat == "STLb":
                self.fo.write(self.s.getbuffer())   # append (partial) binary buffer to file
                self.s.close()
                self.s = io.BytesIO()
            elif self.tile_info.config.fileformat == "STLa":
                self.fo.write(self.s.getvalue())   # append (partial) text buffer to file
                self.s.close()
                self.s = io.StringIO()
            elif self.tile_info.config.fileformat == "obj":
                self.fo[1].write(self.s[1].getvalue())
                self.s[1].close()
                self.s[1] = io.StringIO()

        if flush:
            # close buffers (needed?)
            if self.tile_info.config.fileformat == "obj":
                self.s[1].close()
            else: # STLb and STLa
                self.s.close()


    # Convert grid into a file or memory buffer containing triangles (plus indices for obj)
    def make_file_buffer(
        self,
        create_cells: bool = True,
        parallel_cleanup_workers: int | None = None,
    ):

        if self.tile_info is None:
            print("make_file_buffer: Error: self.tile_info is None")
            return

        # check that we have a valid triangle file format
        if self.tile_info.config.fileformat not in ["obj", "STLa", "STLb"]:
            raise ValueError(f"Invalid file format: {self.tile_info.config.fileformat}. Supported formats are 'obj', 'STLa', and 'STLb'")

        temp_file = self.tile_info.temp_file

        self.num_triangles = 0

        # Open in-memory stream buffers s
        # s is used to collect the data that is eventually written into a proper file
        if self.tile_info.config.fileformat == "STLb":
            self.s = io.BytesIO()
            mode = "ab" if create_cells else "wb"  # for using open() later
        elif self.tile_info.config.fileformat == "STLa":
            self.s = io.StringIO()
            mode = "a" if create_cells else "w"
        elif self.tile_info.config.fileformat == "obj":
            mode = "a" if create_cells else "w"
            # 2 buffers: vertices and indices
            self.s = [io.StringIO(), io.StringIO()]

        # open temp file for appending, file object self.fo will be used in create_cells()
        if temp_file is not None:
            if self.tile_info.config.fileformat == "STLa" or self.tile_info.config.fileformat == "STLb":
                try:
                    self.fo = open(temp_file, mode)
                except Exception as e:
                    print("Error opening:", temp_file, e, file=sys.stderr)
                    return e
            elif self.tile_info.config.fileformat == "obj":
                # for obj we need 2  temp files and file objects, so s and fo are now lists
                try:
                    vertsfo =  open(temp_file, mode)
                except Exception as e:
                    print("Error opening:", temp_file, e, file=sys.stderr)
                    return e
                idx_temp_file = temp_file + ".idx" # index temp file just has .idx at the end

                try:
                    idxfo = open(idx_temp_file, mode)
                except Exception as e:
                    print("Error opening:", idx_temp_file, e, file=sys.stderr)
                    return e
                self.fo = [vertsfo, idxfo]

        # header for STLa and obj
        # (STLb header can only pre-pended later)
        if self.tile_info.config.fileformat == "STLa":
            self.s.write('solid digital_elevation_model\n') # digital_elevation_model is the name of the model
        elif self.tile_info.config.fileformat == "obj":
            self.s[0].write("g vert\n")
            self.s[1].write("g tris\n")

        if create_cells:
            # Populate self.cells and write triangles into buffer/file.
            self.create_cells()
        else:
            self.write_existing_cells_to_buffer(parallel_cleanup_workers)

        # Can we use 2-triangle bottoms?
        add_simple_bottom = self._should_add_simple_bottom()

        # For simple bottom, add 2 triangles based on the corners of the tile
        if add_simple_bottom:
            self._add_simple_bottom_to_buffer()

        # using buffer
        if temp_file is None:

            # finish STLa stream buffer
            if self.tile_info.config.fileformat == "STLa":
                self.s.write('endsolid digital_elevation_model') # append end clause
                buf = self.s.getvalue()

            # For STLb buffer, prepend the header
            if self.tile_info.config.fileformat == "STLb":
                stlb_header = io.BytesIO()
                stlb_header.write(
                    BINARY_STL_HEADER.pack(
                        b'Binary STL Writer',
                        self.num_triangles,
                    )
                )
                stlb_header.write(self.s.getbuffer()) # append body to header
                del self.s # no longer needed
                buf = stlb_header.getvalue()  # CH 5/2025 changed from getbuffer to not return a memory object that c an't be pickled

            # fill s[0] and append s[1]
            elif self.tile_info.config.fileformat == "obj":
                # fill s[0] with all vertices used (keys of vertex class attribute dict)
                print("Appending obj triangle indices\n", file=sys.stderr)
                for vc in vertex.vertex_index_dict:
                    self.s[0].write(f"v {vc[0]}, {vc[1]}, {vc[2]}\n")

                self.s[0].write(self.s[1].getvalue()) # append indices
                del self.s[1]
                buf = self.s[0].getvalue()

            return buf

        # using temp file
        else:
            self.write_buffer_to_file(flush=True) # write leftover buffer to file, will NOT close fo!

            # STLa: append last line
            if self.tile_info.config.fileformat == "STLa":
                self.fo.write('endsolid digital_elevation_model')
                self.fo.close()

            # for binary STL we can only now prepend a header as we didn't have num_triangles until now.
            elif self.tile_info.config.fileformat == "STLb":
                # rename curent file so we can append it to the header file
                self.fo.close()
                body_file = temp_file + ".body"
                os.replace(temp_file, body_file)
                with open(body_file, "rb") as fbody:
                    with open(temp_file, "ab") as fheader: # new temp_file
                        fheader.write(
                            BINARY_STL_HEADER.pack(
                                b'Binary STL Writer',
                                self.num_triangles,
                            )
                        )
                        shutil.copyfileobj(fbody, fheader) # append the body to the header
                os.remove(body_file)

            # For obj the the fo[0] temp file (vertices) must be filled, then the
            # .idx temp file needs to be appended to i
            elif self.tile_info.config.fileformat == "obj":
                # fill vertex temp file
                print("Appending obj triangle indices\n", file=sys.stderr)
                for vc in vertex.vertex_index_dict:
                    self.fo[0].write(f"v {vc[0]}, {vc[1]}, {vc[2]}\n")
                self.fo[0].close()
                self.fo[1].close()

                # append index temp file top vertex temp file
                idx_temp_file = temp_file + ".idx"
                with open(idx_temp_file, "r") as idx_fo:
                    with open(temp_file, "a") as vert_fo:
                        shutil.copyfileobj(idx_fo, vert_fo)
                os.remove(idx_temp_file)

            return temp_file
