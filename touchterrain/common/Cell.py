# Cell.py
# one raster cell's emitted top surface, bottom surface, and walls

"""The tesselation unit: one cell's emitted geometry.

A cell owns a top surface, a bottom surface, and the walls that close the gap
between them. Each surface is either a full quad or, once clipping or nudging
has cut it, a list of triangulated polygons.

This lives below nudging in the import order because confirming a positive-Z
contact needs to build a throwaway cell and run zero-height cleanup on it. The
nudge operations that rewrite a cell are therefore free functions in
``nudge_cell_ops``, reached here through thin delegating methods.
"""

from collections.abc import Iterator, Sequence
from typing import Union

import shapely

from touchterrain.common import nudge_cell_ops
from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.interpolate_Z import interpolate_z_planar
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.shapely_polygon_utils import (
    polygons_equal_3d,
)
from touchterrain.common.mesh_vocabulary import (
    CARDINAL_DIRECTIONS,
    CardinalWallMap,
    Coordinate,
    Edge3D,
    EmittedBottomSurface,
    SerializedVertexCache,
    SurfaceMesh,
    XYEdge,
    _empty_borders,
)
from touchterrain.common.mesh_serialization import (
    _serialized_vertex_from_cache,
    normalize_coordinate_to_match_mesh_serialization,
    polygon_normalized_to_match_mesh_serialization,
    quad_normalized_to_match_mesh_serialization,
    surface_polygon_normalized_to_match_mesh_serialization,
)
from touchterrain.common.surface_geometry import (
    _build_cardinal_wall_borders,
    _linework_covers_footprint,
    _rebuild_matching_surface_polygon_borders,
    _surface_wall_requested_lines,
)


class cell:
    '''a cell with a top and bottom quad, constructor: uses refs and does NOT copy ...
       except for triangle cells
       '''
    __slots__ = (
        "topquad",
        "bottomquad",
        "borders",
        "is_tri_cell",
        "topSurfacePolygons",
        "bottomSurfacePolygons",
        "surfacePolygonBorders",
    )

    topquad: quad | None
    bottomquad: quad | None
    borders: CardinalWallMap
    is_tri_cell: bool

    topSurfacePolygons: list[shapely.Polygon] | None
    "list of polygons (preferably tris) with X,Y,Z to use for the mesh instead of the topquad"
    bottomSurfacePolygons: list[shapely.Polygon] | None
    "list of polygons (preferably tris) with X,Y,Z to use for the mesh instead of the bottomquad"
    surfacePolygonBorders: list[quad] | None
    # surface polygon borders should be generated using raster polygon edge buckets BorderEdge wall value

    def __init__(
        self,
        topquad: quad | None,
        bottomquad: quad | None,
        borders: CardinalWallMap,
        is_tri_cell: bool = False,
    ) -> None:
        self.topquad = topquad
        self.bottomquad = bottomquad
        self.borders = borders
        self.is_tri_cell = is_tri_cell
        self.topSurfacePolygons = None
        self.bottomSurfacePolygons = None
        self.surfacePolygonBorders = None

    def __str__(self):
        r = hex(id(self)) + "\n top:" + str(self.topquad) + "\n btm:" + str(self.bottomquad) + "\n borders:\n"
        for d in CARDINAL_DIRECTIONS:
            border = self.borders.get(d)
            if border:
                r = r + "  " + d + ": " + str(border) + "\n"
        return r

    def top_surface_meshes(self) -> list[SurfaceMesh]:
        """Return the emitted top surface meshes for this cell."""
        if self.topSurfacePolygons:
            return list(self.topSurfacePolygons)
        return [self.topquad] if self.topquad is not None else []

    def bottom_surface_meshes(self) -> list[SurfaceMesh]:
        """Return the emitted bottom surface meshes for this cell."""
        if self.bottomSurfacePolygons:
            return list(self.bottomSurfacePolygons)
        return [self.bottomquad] if self.bottomquad is not None else []

    def iter_meshes_for_model(
        self,
    ) -> Iterator[Union[quad, shapely.Polygon]]:
        """Yield the meshes to include in the output model for this cell."""
        if self.topSurfacePolygons:
            yield from self.topSurfacePolygons
        elif self.topquad is not None:
            yield self.topquad

        if not self.topSurfacePolygons and self.topquad:
            # if we use topquad, we also use cardinal direction borders
            yield from self.borders.values()

        if self.bottomSurfacePolygons:
            yield from self.bottomSurfacePolygons
        elif self.bottomquad is not None:
            yield self.bottomquad

        if self.surfacePolygonBorders:
            yield from self.surfacePolygonBorders

    def clear_geometry(self) -> None:
        """Remove all emitted geometry from this cell."""
        self.topquad = None
        self.bottomquad = None
        self.topSurfacePolygons = None
        self.bottomSurfacePolygons = None
        self.surfacePolygonBorders = None
        self.borders = _empty_borders()

    def meshes_for_model(self) -> list[Union[quad, shapely.Polygon]]:
        """Return the meshes to include in the output model for this cell."""
        return list(self.iter_meshes_for_model())

    def remove_geometry_collapsed_by_mesh_serialization(
        self,
        output_fileformat: str,
        split_rotation: int,
        serialized_vertices: SerializedVertexCache | None = None,
    ) -> None:
        """Remove cell meshes that collapse at output precision."""
        def normalize_surface_polygons(
            surface_polygons: list[shapely.Polygon] | None,
        ) -> list[shapely.Polygon] | None:
            if not surface_polygons:
                return None

            output: list[shapely.Polygon] = []
            for surface_polygon in surface_polygons:
                output_polygon = (
                    surface_polygon_normalized_to_match_mesh_serialization(
                        surface_polygon,
                        output_fileformat,
                        serialized_vertices=serialized_vertices,
                    )
                )
                if output_polygon is not None:
                    output.append(output_polygon)
            return output or None

        had_top_surface_polygons = bool(self.topSurfacePolygons)
        had_bottom_surface_polygons = bool(self.bottomSurfacePolygons)
        if serialized_vertices is None:
            serialized_vertices = {}

        if self.topquad is not None:
            self.topquad = quad_normalized_to_match_mesh_serialization(
                self.topquad,
                output_fileformat,
                split_rotation,
                serialized_vertices,
            )

        if self.bottomquad is not None:
            self.bottomquad = quad_normalized_to_match_mesh_serialization(
                self.bottomquad,
                output_fileformat,
                split_rotation,
                serialized_vertices,
            )

        for direction, border in list(self.borders.items()):
            output_border = quad_normalized_to_match_mesh_serialization(
                border,
                output_fileformat,
                split_rotation,
                serialized_vertices,
            )
            if output_border is None:
                self.borders.pop(direction)
            else:
                self.borders[direction] = output_border

        if self.surfacePolygonBorders:
            surface_borders = []
            for surface_border in self.surfacePolygonBorders:
                output_border = quad_normalized_to_match_mesh_serialization(
                    surface_border,
                    output_fileformat,
                    split_rotation,
                    serialized_vertices,
                )
                if output_border is not None:
                    surface_borders.append(output_border)
            self.surfacePolygonBorders = surface_borders or None

        self.topSurfacePolygons = normalize_surface_polygons(
            self.topSurfacePolygons,
        )
        self.bottomSurfacePolygons = normalize_surface_polygons(
            self.bottomSurfacePolygons,
        )
        if had_top_surface_polygons and not self.topSurfacePolygons:
            self.topquad = None
        if had_bottom_surface_polygons and not self.bottomSurfacePolygons:
            self.bottomquad = None

        if self.topquad is None and not self.topSurfacePolygons:
            self.clear_geometry()

    def emitted_top_as_bottom_surfaces(
        self,
    ) -> EmittedBottomSurface:
        """Return emitted top surfaces reoriented for use as a bottom."""
        if self.topSurfacePolygons:
            return (
                None,
                [
                    shapely.orient_polygons(polygon, exterior_cw=True)
                    for polygon in self.topSurfacePolygons
                ],
            )

        if self.topquad is None:
            return None, None

        top_vertices = self.topquad.vl
        if top_vertices[3] is None:
            return (
                quad(
                    top_vertices[0],
                    top_vertices[2],
                    top_vertices[1],
                    None,
                    forced_split_edge=self.topquad.forced_split_edge,
                ),
                None,
            )
        return (
            quad(
                top_vertices[0],
                top_vertices[3],
                top_vertices[2],
                top_vertices[1],
                forced_split_edge=self.topquad.forced_split_edge,
            ),
            None,
        )

    def replace_bottom_surfaces(
        self,
        bottom_surface_quad: quad | None,
        bottom_surface_polygons: list[shapely.Polygon] | None,
        split_rotation: int,
        output_fileformat: str | None = None,
    ) -> None:
        """Replace bottom geometry and rebuild walls against the current top.

        Pair mode uses this after the normal mesh is emitted. The replacement
        preserves the difference top surface and wall footprint decisions, but
        swaps the bottom surface to the exact normal top geometry for the same
        cell.
        """
        replacement_bottom_quad = bottom_surface_quad
        if self.topSurfacePolygons and bottom_surface_quad is not None:
            bottom_surface_polygons = []
            bottom_planes = bottom_surface_quad.get_triangles_in_polygons(
                split_rotation=split_rotation,
            )
            kept_top_surface_polygons: list[shapely.Polygon] = []
            for top_polygon in self.topSurfacePolygons:
                bottom_polygon = interpolate_z_planar(
                    geometry_2d=shapely.orient_polygons(
                        shapely.force_2d(top_polygon),
                        exterior_cw=True,
                    ),
                    planes_3d=bottom_planes,
                )
                if not isinstance(bottom_polygon, shapely.Polygon):
                    raise TypeError(
                        "Shared pair clipped bottom interpolation did not "
                        "return a Polygon."
                    )
                if output_fileformat is not None:
                    bottom_polygon = (
                        polygon_normalized_to_match_mesh_serialization(
                            bottom_polygon,
                            output_fileformat,
                        )
                    )
                    if bottom_polygon is None:
                        continue
                kept_top_surface_polygons.append(top_polygon)
                bottom_surface_polygons.append(bottom_polygon)
            self.topSurfacePolygons = kept_top_surface_polygons
            if not bottom_surface_polygons:
                self.clear_geometry()
                return
            bottom_surface_quad = None

        if (
            bottom_surface_polygons is not None
            and not self.topSurfacePolygons
            and self.topquad is not None
        ):
            top_planes = self.topquad.get_triangles_in_polygons(
                split_rotation=split_rotation,
            )
            promoted_top_polygons: list[shapely.Polygon] = []
            kept_bottom_polygons: list[shapely.Polygon] = []
            for bottom_polygon in bottom_surface_polygons:
                top_polygon = interpolate_z_planar(
                    geometry_2d=shapely.orient_polygons(
                        shapely.force_2d(bottom_polygon),
                        exterior_cw=False,
                    ),
                    planes_3d=top_planes,
                )
                if not isinstance(top_polygon, shapely.Polygon):
                    raise TypeError(
                        "Shared pair top promotion did not return a Polygon."
                    )
                promoted_top_polygons.append(top_polygon)
                kept_bottom_polygons.append(bottom_polygon)

            self.topSurfacePolygons = promoted_top_polygons or None
            bottom_surface_polygons = kept_bottom_polygons or None
            if bottom_surface_polygons is None:
                self.clear_geometry()
                return

        if bottom_surface_polygons is not None:
            if not self.topSurfacePolygons:
                raise RuntimeError(
                    "Shared pair bottom has clipped polygons but the "
                    "difference top does not."
                )
            if replacement_bottom_quad is not None:
                self.bottomquad = replacement_bottom_quad
            self.bottomSurfacePolygons = bottom_surface_polygons
            self.borders = _empty_borders()
            self._rebuild_surface_polygon_borders(output_fileformat)
            return

        if bottom_surface_quad is None:
            raise RuntimeError("Shared pair bottom surface is missing.")
        if self.topquad is None:
            raise RuntimeError("Difference top surface is missing.")

        self._force_top_split_to_bottom_surface(
            bottom_surface_quad,
            None,
            split_rotation,
        )
        self.bottomquad = bottom_surface_quad
        self.bottomSurfacePolygons = None
        self.surfacePolygonBorders = None
        self._rebuild_cardinal_borders(output_fileformat)

    def _force_top_split_to_bottom_surface(
        self,
        bottom_surface_quad: quad | None,
        bottom_surface_polygons: list[shapely.Polygon] | None,
        split_rotation: int,
    ) -> None:
        """Force a full top quad to use the provider bottom diagonal."""
        if self.topquad is None:
            return
        bottom_split_edge = self._bottom_surface_split_edge(
            bottom_surface_quad,
            bottom_surface_polygons,
            split_rotation,
        )
        if bottom_split_edge is None:
            return
        if (
            self.topquad.get_split_edge_indices(split_rotation)
            != bottom_split_edge
        ):
            self.topquad.forced_split_edge = bottom_split_edge

    def _bottom_surface_split_edge(
        self,
        bottom_surface_quad: quad | None,
        bottom_surface_polygons: list[shapely.Polygon] | None,
        split_rotation: int,
    ) -> tuple[int, int] | None:
        """Return the provider split edge when it is a full-cell diagonal."""
        if self.topquad is None or self.topquad.vl[3] is None:
            return None
        if (
            bottom_surface_quad is not None
            and bottom_surface_quad.vl[3] is not None
        ):
            return bottom_surface_quad.get_split_edge_indices(split_rotation)
        if not bottom_surface_polygons:
            return None

        def edge_key(coord0: Coordinate, coord1: Coordinate) -> XYEdge:
            return tuple(
                sorted(
                    (
                        (
                            round(float(coord0[0]), 6),
                            round(float(coord0[1]), 6),
                        ),
                        (
                            round(float(coord1[0]), 6),
                            round(float(coord1[1]), 6),
                        ),
                    )
                )
            )

        top_vertices = self.topquad.vl
        default_edge = edge_key(
            top_vertices[0].coords,
            top_vertices[2].coords,
        )
        rotated_edge = edge_key(
            top_vertices[1].coords,
            top_vertices[3].coords,
        )
        provider_split_edges: set[tuple[int, int]] = set()
        for polygon in bottom_surface_polygons:
            coords = list(polygon.exterior.coords)
            for index, coord0 in enumerate(coords[:-1]):
                coord1 = coords[(index + 1) % (len(coords) - 1)]
                polygon_edge = edge_key(coord0, coord1)
                if polygon_edge == default_edge:
                    provider_split_edges.add(quad._default_split_edge)
                elif polygon_edge == rotated_edge:
                    provider_split_edges.add(quad._rotated_split_edge)
        if len(provider_split_edges) != 1:
            return None
        return next(iter(provider_split_edges))

    def _rebuild_cardinal_borders(
        self,
        output_fileformat: str | None,
    ) -> None:
        """Rebuild existing cardinal walls after replacing a bottom quad."""
        self.borders = _build_cardinal_wall_borders(
            self.borders,
            self.topquad.vl,
            self.bottomquad.vl,
            output_fileformat or "STLb",
        )

    def _rebuild_surface_polygon_borders(
        self,
        output_fileformat: str | None,
    ) -> None:
        """Rebuild existing clipped wall footprints with shared bottom edges."""
        mesh_fileformat = output_fileformat or "STLb"
        requested_lines = _surface_wall_requested_lines(
            self.surfacePolygonBorders,
            output_fileformat=mesh_fileformat,
        )
        if requested_lines is None:
            self.surfacePolygonBorders = None
            return

        self.surfacePolygonBorders = (
            _rebuild_matching_surface_polygon_borders(
                self.topSurfacePolygons,
                self.bottomSurfacePolygons,
                lambda footprint: _linework_covers_footprint(
                    requested_lines,
                    footprint,
                ),
                mesh_fileformat,
            )
            or None
        )

    def split_surface_boundary_midpoints(
        self,
        split_sides: set[str],
        contact_corners: Sequence[IntermediateCorner],
        W: float,
        E: float,
        N: float,
        S: float,
        split_rotation: int,
        output_fileformat: str,
        include_contact_cut_walls: bool = True,
        top_midpoint_corner_vertices: (
            dict[IntermediateCorner, vertex] | None
        ) = None,
        top_midpoint_z_by_name: dict[str, float] | None = None,
        bottom_midpoint_corner_vertices: (
            dict[IntermediateCorner, vertex] | None
        ) = None,
        bottom_midpoint_z_by_name: dict[str, float] | None = None,
        side_cut_wall_sides: set[str] | None = None,
    ) -> bool:
        """Delegate to nudge_cell_ops.split_surface_boundary_midpoints()."""
        return nudge_cell_ops.split_surface_boundary_midpoints(
            self,
            split_sides=split_sides,
            contact_corners=contact_corners,
            W=W,
            E=E,
            N=N,
            S=S,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
            include_contact_cut_walls=include_contact_cut_walls,
            top_midpoint_corner_vertices=top_midpoint_corner_vertices,
            top_midpoint_z_by_name=top_midpoint_z_by_name,
            bottom_midpoint_corner_vertices=bottom_midpoint_corner_vertices,
            bottom_midpoint_z_by_name=bottom_midpoint_z_by_name,
            side_cut_wall_sides=side_cut_wall_sides,
        )

    def apply_positive_z_normal_nudge(
        self,
        affected_corners: Sequence[IntermediateCorner],
        W: float,
        E: float,
        N: float,
        S: float,
        split_rotation: int,
        output_fileformat: str,
        top_midpoint_corner_vertices: (
            dict[IntermediateCorner, vertex] | None
        ) = None,
        top_midpoint_z_by_name: dict[str, float] | None = None,
        difference_footprint: shapely.Geometry | None = None,
    ) -> bool:
        """Delegate to nudge_cell_ops.apply_positive_z_normal_nudge()."""
        return nudge_cell_ops.apply_positive_z_normal_nudge(
            self,
            affected_corners=affected_corners,
            W=W,
            E=E,
            N=N,
            S=S,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
            top_midpoint_corner_vertices=top_midpoint_corner_vertices,
            top_midpoint_z_by_name=top_midpoint_z_by_name,
            difference_footprint=difference_footprint,
        )

    def apply_positive_z_difference_nudge(
        self,
        affected_corners: Sequence[IntermediateCorner],
        W: float,
        E: float,
        N: float,
        S: float,
        split_rotation: int,
        output_fileformat: str,
        top_midpoint_corner_vertices: (
            dict[IntermediateCorner, vertex] | None
        ) = None,
        top_midpoint_z_by_name: dict[str, float] | None = None,
        bottom_midpoint_corner_vertices: (
            dict[IntermediateCorner, vertex] | None
        ) = None,
        bottom_midpoint_z_by_name: dict[str, float] | None = None,
        side_cut_wall_sides: set[str] | None = None,
    ) -> bool:
        """Delegate to nudge_cell_ops.apply_positive_z_difference_nudge()."""
        return nudge_cell_ops.apply_positive_z_difference_nudge(
            self,
            affected_corners=affected_corners,
            W=W,
            E=E,
            N=N,
            S=S,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
            top_midpoint_corner_vertices=top_midpoint_corner_vertices,
            top_midpoint_z_by_name=top_midpoint_z_by_name,
            bottom_midpoint_corner_vertices=bottom_midpoint_corner_vertices,
            bottom_midpoint_z_by_name=bottom_midpoint_z_by_name,
            side_cut_wall_sides=side_cut_wall_sides,
        )

    def flip_bottom_positive_z_contact_edges(
        self,
        split_rotation: int,
        output_fileformat: str,
        allowed_edges: set[Edge3D] | None = None,
    ) -> bool:
        """Delegate to nudge_cell_ops.flip_bottom_positive_z_contact_edges()."""
        return nudge_cell_ops.flip_bottom_positive_z_contact_edges(
            self,
            split_rotation=split_rotation,
            output_fileformat=output_fileformat,
            allowed_edges=allowed_edges,
        )

    def check_for_tri_cell(self) -> bool:
        """Return whether two adjacent walls allow triangular smoothing."""
        if self.is_tri_cell:
            return False
        border_sides = {
            direction
            for direction, border in self.borders.items()
            if border
        }

        if len(border_sides) != 2:
            return False
        if border_sides in ({"N", "S"}, {"E", "W"}):
            return False

        return True

    def convert_to_tri_cell(self) -> None:
        """Collapse a cell with two adjacent walls into a triangular cell."""
        if self.is_tri_cell:
            return
        if self.topquad is None or self.bottomquad is None:
            raise RuntimeError(
                "Triangular smoothing needs top and bottom quads."
            )

        b = self.borders
        tvl = self.topquad.vl
        bvl = self.bottomquad.vl

        # Keep one outer wall and replace it with the new diagonal wall.

        if b.get("N") and b.get("W"):
            self.topquad = quad(tvl[3], tvl[1], tvl[2], None) # ccw, order doesn't matter
            self.bottomquad = quad(bvl[1], bvl[2], bvl[3], None) # cw!
            b["N"] = quad(tvl[1], tvl[3], bvl[1], bvl[3]) # diagonal wall (ccw!)
            b.pop("W")
        elif b.get("N") and b.get("E"):
            self.topquad = quad(tvl[0], tvl[1], tvl[2], None)
            self.bottomquad = quad(bvl[0], bvl[2], bvl[3], None)
            b["N"] = quad(tvl[0], tvl[2], bvl[2], bvl[0])
            b.pop("E")
        elif b.get("S") and b.get("E"):
            self.topquad = quad(tvl[3], tvl[0], tvl[1], None)
            self.bottomquad = quad(bvl[3], bvl[0], bvl[1], None)
            b["S"] = quad(tvl[3], tvl[1], bvl[3], bvl[1])
            b.pop("E")
        elif b.get("S") and b.get("W"):
            self.topquad = quad(tvl[2], tvl[3], tvl[0], None)
            self.bottomquad = quad(bvl[0], bvl[1], bvl[2], None)
            b["S"] = quad(tvl[2], tvl[0], bvl[0], bvl[2])
            b.pop("W")
        else:
            raise RuntimeError(
                f"Invalid triangular smoothing walls: {self.borders}"
            )

        self.is_tri_cell = True

    def remove_zero_height_volumes(
        self,
        split_rotation: int,
        output_fileformat: str = "STLb",
        preserve_zero_height_xy: set[tuple[float, float]] | None = None,
        preserve_zero_height_edges: set[XYEdge] | None = None,
        serialized_vertices: SerializedVertexCache | None = None,
    ) -> None:
        """Remove zero-height cell geometry in place.

        This mutates quads, cardinal borders, clipped surface polygons, and
        clipped wall borders. Cardinal quads are compared as the triangles
        emitted for ``split_rotation``. Matching clipped top/bottom polygons
        are deleted, then ``surfacePolygonBorders`` is filtered or rebuilt so
        only walls still supported by both remaining clipped-surface boundaries
        are kept.
        """
        # Step 1: compare at serialized mesh precision, not raw float
        # precision, so cleanup matches the STL/OBJ vertices that are written.
        if serialized_vertices is None:
            serialized_vertices = {}

        def output_signature(coord: Coordinate) -> tuple[float, ...]:
            return _serialized_vertex_from_cache(
                coord,
                output_fileformat,
                serialized_vertices,
            )

        def ordinary_quad_zero_height_corner_count() -> int | None:
            """Return matching corner count for simple top/bottom quads."""
            if self.topSurfacePolygons or self.bottomSurfacePolygons:
                return None
            if self.topquad is None or self.bottomquad is None:
                return None
            top_vertices = self.topquad.vl
            bottom_vertices = self.bottomquad.vl
            if top_vertices[3] is None or bottom_vertices[3] is None:
                return None

            corner_pairs = (
                (top_vertices[0], bottom_vertices[0]),  # NW
                (top_vertices[1], bottom_vertices[3]),  # SW
                (top_vertices[2], bottom_vertices[2]),  # SE
                (top_vertices[3], bottom_vertices[1]),  # NE
            )

            def vertices_match(
                top_vertex: vertex,
                bottom_vertex: vertex,
            ) -> bool:
                top_coords = top_vertex.coords
                bottom_coords = bottom_vertex.coords
                if top_coords[:2] != bottom_coords[:2]:
                    return (
                        output_signature(top_coords)
                        == output_signature(bottom_coords)
                    )
                if top_coords[2] == bottom_coords[2]:
                    return True
                return (
                    normalize_coordinate_to_match_mesh_serialization(
                        top_coords[2],
                        output_fileformat,
                    )
                    == normalize_coordinate_to_match_mesh_serialization(
                        bottom_coords[2],
                        output_fileformat,
                    )
                )

            matching_corners = 0
            remaining_corners = len(corner_pairs)
            for top_vertex, bottom_vertex in corner_pairs:
                remaining_corners -= 1
                if vertices_match(top_vertex, bottom_vertex):
                    matching_corners += 1
                if matching_corners + remaining_corners < 3:
                    break
            return matching_corners

        zero_height_corner_count = ordinary_quad_zero_height_corner_count()
        if zero_height_corner_count is not None and zero_height_corner_count < 3:
            return

        protected_zero_height_xy = {
            output_signature((xy[0], xy[1], 0.0))[:2]
            for xy in (preserve_zero_height_xy or set())
        }

        def surface_border_footprint(
            surface_border: quad,
        ) -> shapely.LineString | None:
            # Collapse a clipped wall quad/tri to its two unique XY endpoints.
            xy_coords: list[tuple[float, float]] = []
            for v in surface_border.vl:
                if v is None:
                    continue
                output_coord = output_signature(v.coords)
                xy = (output_coord[0], output_coord[1])
                if xy not in xy_coords:
                    xy_coords.append(xy)
            if len(xy_coords) != 2:
                return None
            return shapely.LineString(xy_coords)

        def edge_xy_signature(
            coord0: Coordinate,
            coord1: Coordinate,
        ) -> XYEdge:
            # Normalize XY edge direction so dictionary lookup is stable.
            return tuple(
                sorted(
                    (
                        output_signature(coord0)[:2],
                        output_signature(coord1)[:2],
                    )
                )
            )

        protected_zero_height_edges = {
            edge_xy_signature(
                (edge[0][0], edge[0][1], 0.0),
                (edge[1][0], edge[1][1], 0.0),
            )
            for edge in (preserve_zero_height_edges or set())
        }

        def polygon_edge_footprints(polygon: shapely.Polygon) -> set[XYEdge]:
            # Collect all XY boundary edges for a removed clipped polygon.
            footprints: set[XYEdge] = set()
            rings = [polygon.exterior, *polygon.interiors]
            for ring in rings:
                coords = list(ring.coords)
                for ci in range(len(coords) - 1):
                    footprints.add(
                        edge_xy_signature(coords[ci], coords[ci + 1])
                    )
            return footprints

        def polygon_has_protected_edge(polygon: shapely.Polygon) -> bool:
            """Return whether a zero-height polygon carries protected edge."""
            return bool(
                protected_zero_height_edges
                and (
                    polygon_edge_footprints(polygon)
                    & protected_zero_height_edges
                )
            )

        def polygon_has_protected_vertex(polygon: shapely.Polygon) -> bool:
            """Return whether a zero-height polygon carries protected XY."""
            if not protected_zero_height_xy:
                return False
            rings = [polygon.exterior, *polygon.interiors]
            for ring in rings:
                for coord in ring.coords:
                    if output_signature(coord)[:2] in protected_zero_height_xy:
                        return True
            return False

        # Step 2: cardinal quads are cleaned up using the triangles that will
        # actually be emitted for the active split_rotation.
        def triangle_signature(
            triangle: tuple[vertex, ...],
        ) -> tuple[tuple[float, ...], ...]:
            """Return a serialized-coordinate triangle signature."""
            # Sort vertices so opposite top/bottom winding still matches.
            return tuple(
                sorted(output_signature(v.coords) for v in triangle)
            )

        def triangle_boundary_footprints(
            triangles: list[tuple[vertex, ...]],
        ) -> set[XYEdge]:
            """Return serialized XY boundary footprints for triangles."""
            # Collect the serialized XY boundary edges still present.
            footprints: set[XYEdge] = set()
            for triangle in triangles:
                for vi, v0 in enumerate(triangle):
                    v1 = triangle[(vi + 1) % len(triangle)]
                    footprints.add(edge_xy_signature(v0.coords, v1.coords))
            return footprints

        def filter_cardinal_borders(
            top_triangles: list[tuple[vertex, ...]],
            bottom_triangles: list[tuple[vertex, ...]],
        ) -> None:
            """Keep cardinal walls still supported by both surfaces."""
            # After a cardinal surface triangle is removed, drop any N/S/E/W
            # wall whose footprint is no longer present on both surfaces.
            top_footprints = triangle_boundary_footprints(top_triangles)
            bottom_footprints = triangle_boundary_footprints(bottom_triangles)
            for direction, border in list(self.borders.items()):
                footprint = surface_border_footprint(border)
                if footprint is None:
                    self.borders.pop(direction)
                    continue
                footprint_key = edge_xy_signature(
                    footprint.coords[0],
                    footprint.coords[1],
                )
                if (
                    footprint_key not in top_footprints
                    or footprint_key not in bottom_footprints
                ):
                    self.borders.pop(direction)

        def remove_matching_cardinal_corners() -> bool:
            """Remove a zero-height corner when split diagonals differ."""
            # This preserves the old 3-corner cleanup for cases where top and
            # bottom choose different diagonals, so triangle signatures miss
            # the zero-height corner.
            if self.topquad is None or self.bottomquad is None:
                return False
            tvl = self.topquad.vl
            bvl = self.bottomquad.vl
            if tvl[3] is None or bvl[3] is None:
                return False

            # Corner index mapping by shared XY position:
            #     position: NW  SW  SE  NE
            #     top:       0   1   2   3
            #     bottom:    0   3   2   1
            corners_match = {
                "NW": output_signature(tvl[0].coords)
                == output_signature(bvl[0].coords),
                "SW": output_signature(tvl[1].coords)
                == output_signature(bvl[3].coords),
                "SE": output_signature(tvl[2].coords)
                == output_signature(bvl[2].coords),
                "NE": output_signature(tvl[3].coords)
                == output_signature(bvl[1].coords),
            }

            if all(corners_match.values()):
                self.topquad = None
                self.bottomquad = None
                self.borders.clear()
                return True

            if corners_match["NW"] and corners_match["NE"] and corners_match["SW"]:
                self.topquad = quad(tvl[3], tvl[1], tvl[2], None)
                self.bottomquad = quad(bvl[1], bvl[2], bvl[3], None)
                self.borders.pop("N", None)
                self.borders.pop("W", None)
                return True

            if corners_match["NW"] and corners_match["NE"] and corners_match["SE"]:
                self.topquad = quad(tvl[0], tvl[1], tvl[2], None)
                self.bottomquad = quad(bvl[0], bvl[2], bvl[3], None)
                self.borders.pop("N", None)
                self.borders.pop("E", None)
                return True

            if corners_match["NE"] and corners_match["SW"] and corners_match["SE"]:
                self.topquad = quad(tvl[3], tvl[0], tvl[1], None)
                self.bottomquad = quad(bvl[3], bvl[0], bvl[1], None)
                self.borders.pop("S", None)
                self.borders.pop("E", None)
                return True

            if corners_match["NW"] and corners_match["SW"] and corners_match["SE"]:
                self.topquad = quad(tvl[2], tvl[3], tvl[0], None)
                self.bottomquad = quad(bvl[0], bvl[1], bvl[2], None)
                self.borders.pop("S", None)
                self.borders.pop("W", None)
                return True

            return False

        def remove_matching_cardinal_triangles() -> None:
            """Remove zero-height cardinal triangles for the active split."""
            # Match top and bottom triangles by serialized coordinates. If
            # only one pair remains, keep that triangle and filter its walls.
            if self.topquad is None or self.bottomquad is None:
                return

            top_triangles = self.topquad.get_triangles(
                split_rotation=split_rotation,
            )
            bottom_triangles = self.bottomquad.get_triangles(
                split_rotation=split_rotation,
            )
            if len(top_triangles) != len(bottom_triangles):
                return

            bottom_signatures = [
                triangle_signature(triangle)
                for triangle in bottom_triangles
            ]
            matched_top_indexes: set[int] = set()
            matched_bottom_indexes: set[int] = set()

            # Match each top triangle to at most one serialized-equal bottom.
            for top_index, top_triangle in enumerate(top_triangles):
                top_signature = triangle_signature(top_triangle)
                for bottom_index, bottom_signature in enumerate(
                    bottom_signatures,
                ):
                    if bottom_index in matched_bottom_indexes:
                        continue
                    if top_signature != bottom_signature:
                        continue
                    matched_top_indexes.add(top_index)
                    matched_bottom_indexes.add(bottom_index)
                    break

            if not matched_top_indexes:
                if (
                    self.topquad.get_split_edge_indices(split_rotation)
                    != self.bottomquad.get_split_edge_indices(split_rotation)
                ):
                    remove_matching_cardinal_corners()
                return

            remaining_top_triangles = [
                triangle
                for index, triangle in enumerate(top_triangles)
                if index not in matched_top_indexes
            ]
            remaining_bottom_triangles = [
                triangle
                for index, triangle in enumerate(bottom_triangles)
                if index not in matched_bottom_indexes
            ]

            if not remaining_top_triangles and not remaining_bottom_triangles:
                self.topquad = None
                self.bottomquad = None
                self.borders.clear()
                return

            if (
                len(remaining_top_triangles) == 1
                and len(remaining_bottom_triangles) == 1
            ):
                top_triangle = remaining_top_triangles[0]
                bottom_triangle = remaining_bottom_triangles[0]
                self.topquad = quad(
                    top_triangle[0],
                    top_triangle[1],
                    top_triangle[2],
                    None,
                )
                self.bottomquad = quad(
                    bottom_triangle[0],
                    bottom_triangle[1],
                    bottom_triangle[2],
                    None,
                )
                filter_cardinal_borders(
                    remaining_top_triangles,
                    remaining_bottom_triangles,
                )

        # Run cardinal cleanup before clipped cleanup; unclipped cells use
        # topquad, bottomquad, and the N/S/E/W wall dictionary.
        remove_matching_cardinal_triangles()

        # Step 3: clipped cells already have explicit triangulated surfaces,
        # so remove exact matching top/bottom polygons directly.
        removed_surface_polygon = False
        removed_surface_edge_footprints: set[XYEdge] = set()
        if self.topSurfacePolygons and self.bottomSurfacePolygons:
            ti = 0
            while ti < len(self.topSurfacePolygons):
                match = False
                bi = 0
                while bi < len(self.bottomSurfacePolygons):
                    top_surface_polygon = self.topSurfacePolygons[ti]
                    bottom_surface_polygon = self.bottomSurfacePolygons[bi]
                    normalized_top_surface = (
                        surface_polygon_normalized_to_match_mesh_serialization(
                            top_surface_polygon,
                            output_fileformat,
                            serialized_vertices=serialized_vertices,
                        )
                    )
                    normalized_bottom_surface = (
                        surface_polygon_normalized_to_match_mesh_serialization(
                            bottom_surface_polygon,
                            output_fileformat,
                            serialized_vertices=serialized_vertices,
                        )
                    )
                    if (
                        normalized_top_surface is not None
                        and normalized_bottom_surface is not None
                        and polygons_equal_3d(
                            normalized_top_surface,
                            normalized_bottom_surface,
                        )
                    ):
                        if polygon_has_protected_vertex(
                            top_surface_polygon,
                        ) or polygon_has_protected_vertex(
                            bottom_surface_polygon,
                        ) or polygon_has_protected_edge(
                            top_surface_polygon,
                        ) or polygon_has_protected_edge(
                            bottom_surface_polygon,
                        ):
                            bi += 1
                            continue
                        removed_surface_edge_footprints.update(
                            polygon_edge_footprints(top_surface_polygon)
                        )
                        removed_surface_edge_footprints.update(
                            polygon_edge_footprints(bottom_surface_polygon)
                        )
                        del self.topSurfacePolygons[ti]
                        del self.bottomSurfacePolygons[bi]
                        removed_surface_polygon = True
                        match = True
                        break
                    bi += 1
                if not match:
                    ti += 1

        if removed_surface_polygon:
            # Step 4: after clipped surface removal, split final top/bottom
            # boundary edges at each other's wall vertices, then rebuild walls
            # from exact serialized XY matches.
            requested_line_parts: list[shapely.Geometry] = [
                shapely.LineString(footprint)
                for footprint in removed_surface_edge_footprints
            ]
            requested_clipped_lines = _surface_wall_requested_lines(
                self.surfacePolygonBorders,
                output_fileformat=output_fileformat,
            )
            if requested_clipped_lines is not None:
                requested_line_parts.append(requested_clipped_lines)
            requested_lines = (
                shapely.union_all(requested_line_parts)
                if requested_line_parts
                else None
            )

            self.surfacePolygonBorders = (
                _rebuild_matching_surface_polygon_borders(
                    self.topSurfacePolygons,
                    self.bottomSurfacePolygons,
                    lambda footprint: _linework_covers_footprint(
                        requested_lines,
                        footprint,
                    ),
                    output_fileformat,
                )
                or None
            )
