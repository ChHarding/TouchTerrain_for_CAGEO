from __future__ import annotations

import functools
import logging
import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeAlias

import numpy
import shapely
from shapely.prepared import prep
from shapely.ops import unary_union

# try to import gdal from multiple sources
try:
    import gdal
except ImportError:
    from osgeo import gdal

from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.user_config import TouchTerrainConfig
from touchterrain.common.utils import geoCoordToPrint2DCoord, arrayCellCoordToQuadPrint2DCoords
from touchterrain.common.shapely_utils import flatten_geometries, flatten_geometries_borderEdge, sort_line_segment_based_contains
from touchterrain.common.wall_visualization import BorderEdgePlotRecord

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

EdgeBuckets: TypeAlias = dict[str, list[BorderEdge]]
PreparedClippingPolygon: TypeAlias = tuple[shapely.Polygon, Any]
PolygonClipUpdates: TypeAlias = tuple[
    list[tuple[int, int]],
    list[tuple[int, int, list[shapely.Geometry]]],
    list[tuple[int, int, EdgeBuckets]],
    list[tuple[int, int]],
]
EDGE_BUCKET_KEYS = ("N", "W", "S", "E", "other")
OPPOSITE_SIDE = {"N": "S", "S": "N", "W": "E", "E": "W"}


def _empty_edge_buckets() -> EdgeBuckets:
    return {key: [] for key in EDGE_BUCKET_KEYS}


def _polygon_clip_row_ranges(
    row_count: int,
    worker_count: int,
) -> list[tuple[int, int]]:
    """Split polygon clipping rows into deterministic worker chunks."""
    if row_count <= 0:
        return []

    bounded_workers = max(1, min(worker_count, row_count))
    base_rows_per_worker = row_count // bounded_workers
    extra_rows = row_count % bounded_workers
    row_ranges = []
    start_row = 0
    for worker_idx in range(bounded_workers):
        rows_for_worker = (
            base_rows_per_worker
            + (1 if worker_idx < extra_rows else 0)
        )
        end_row = start_row + rows_for_worker
        row_ranges.append((start_row, end_row))
        start_row = end_row
    return row_ranges


def _log_info(msg: str) -> None:
    """Send logging to configured handlers or stdout when none are present."""
    if logger.hasHandlers():
        logger.info(msg)
    else:
        print(msg)


def _polygon_parts(geometry: shapely.Geometry) -> list[shapely.Polygon]:
    """Return non-empty polygon parts from a Shapely geometry."""
    if geometry.is_empty:
        return []
    if isinstance(geometry, shapely.Polygon):
        return [geometry] if geometry.area > 0 else []
    polygons: list[shapely.Polygon] = []
    if hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            polygons.extend(_polygon_parts(child))
    return polygons


def _union_clipping_polygons(
    polygons: list[shapely.Polygon],
) -> list[shapely.Polygon]:
    """Return polygon parts for the unioned clipping footprint."""
    if not polygons:
        return []
    return _polygon_parts(shapely.union_all(polygons))


def _geodataframe_has_finite_geometry(
    polygon_boundary_gdf: Any,
) -> bool:
    for geometry in polygon_boundary_gdf.geometry:
        if geometry is None or geometry.is_empty:
            continue
        if not all(numpy.isfinite(value) for value in geometry.bounds):
            return False
    return True


def _nad83_projection_fallbacks(
    target_crs: Any,
) -> list[tuple[str, Any]]:
    import pyproj

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        proj4 = target_crs.to_proj4()
    fallbacks = [("original PROJ string", pyproj.CRS.from_proj4(proj4))]
    if "+datum=NAD83" in proj4:
        fallbacks.append(
            (
                "NAD83 ellipsoid",
                pyproj.CRS.from_proj4(
                    proj4.replace("+datum=NAD83", "+ellps=GRS80")
                ),
            )
        )
    return fallbacks


def _project_polygon_boundary_gdf(
    polygon_boundary_gdf: Any,
    dem_projection: str,
) -> Any:
    import pyproj

    projected_gdf = polygon_boundary_gdf.to_crs(dem_projection)
    if _geodataframe_has_finite_geometry(projected_gdf):
        return projected_gdf

    target_crs = pyproj.CRS.from_wkt(dem_projection)
    for fallback_name, fallback_crs in _nad83_projection_fallbacks(target_crs):
        fallback_gdf = polygon_boundary_gdf.to_crs(fallback_crs)
        if _geodataframe_has_finite_geometry(fallback_gdf):
            _log_info(
                f"Reprojected clipping polygon with {fallback_name} fallback "
                "after DEM WKT transform produced non-finite coordinates."
            )
            return fallback_gdf
    return projected_gdf


def _process_polygon_clip_cell(
    i: int,
    j: int,
    clipping_print2d_polys: list[PreparedClippingPolygon],
    cell_size_mm: float,
    tile_y_shape: int,
) -> tuple[bool, list[shapely.Geometry], EdgeBuckets | None, bool]:
    """Collect clipping results based on intersection between a single cell and clipping poly."""
    quadPrint2DCoords = arrayCellCoordToQuadPrint2DCoords(
        array_coord_2D=(i, j),
        cell_size=cell_size_mm,
        tile_y_shape=tile_y_shape,
    )

    cell_disjoint = True
    cell_polygon_intersection_geometry: list[shapely.Geometry] = []
    cell_polygon_intersection_edge_buckets: EdgeBuckets | None = None
    cell_contains_properly = False

    for clippingPrint2DPoly, preparedClippingPrint2DPoly in clipping_print2d_polys:
        disjoint, intersection_geoms, intersection_edges, contains_properly = find_intersection_geometries(
            clippingPrint2DPoly=clippingPrint2DPoly,
            quadPrint2DCoords=quadPrint2DCoords,
            preparedClippingPrint2DPoly=preparedClippingPrint2DPoly,
        )
        
        # Mark cell as not disjoint if needed
        cell_disjoint &= disjoint
        
        # Add to cell's "all intersection geometries flattened to polygons"
        if intersection_geoms:
            cell_polygon_intersection_geometry.extend(intersection_geoms)
            
        # Add to cell's "all intersection geometries flattened to single edges and sorted into buckets in a dict"
        if intersection_edges:
            if cell_polygon_intersection_edge_buckets is None:
                cell_polygon_intersection_edge_buckets = _empty_edge_buckets()
            for k, v in intersection_edges.items():
                cell_polygon_intersection_edge_buckets[k].extend(v)
                
        # Set cell's polygon_intersection_contains_properly
        if contains_properly:
            cell_contains_properly = True

    return cell_disjoint, cell_polygon_intersection_geometry, cell_polygon_intersection_edge_buckets, cell_contains_properly

def _process_polygon_clip_rows(
    row_range: tuple[int, int],
    clipping_print2d_polys: list[shapely.Polygon],
    cell_size_mm: float,
    tile_y_shape: int,
    grid_width: int,
) -> PolygonClipUpdates:
    """Get cell and clipping poly intersection results for a range of rows.
    Worker can run this to process a chunk of rows. Returns lists of update info to apply in main process."""
    start_row, end_row = row_range
    _log_info(f"Polygon clipping starting rows [{start_row}, {end_row})")
    prepared_clipping_print2d_polys = [
        (clipping_poly, prep(clipping_poly))
        for clipping_poly in clipping_print2d_polys
    ]
    disjoint_cells = []
    polygon_intersection_geometry_updates = []
    polygon_intersection_edge_buckets_updates = []
    polygon_intersection_contains_properly_updates = []

    for j in range(start_row, end_row):
        for i in range(grid_width):
            cell_disjoint, cell_intersection_geoms, cell_edge_buckets, cell_contains_properly = _process_polygon_clip_cell(
                i=i,
                j=j,
                clipping_print2d_polys=prepared_clipping_print2d_polys,
                cell_size_mm=cell_size_mm,
                tile_y_shape=tile_y_shape,
            )

            if cell_disjoint:
                disjoint_cells.append((j, i))
            if cell_intersection_geoms:
                polygon_intersection_geometry_updates.append((j, i, cell_intersection_geoms))
            if cell_edge_buckets and any(len(v) > 0 for v in cell_edge_buckets.values()):
                polygon_intersection_edge_buckets_updates.append((j, i, cell_edge_buckets))
            if cell_contains_properly:
                polygon_intersection_contains_properly_updates.append((j, i))

    _log_info(f"Polygon clipping finished rows [{start_row}, {end_row})")
    return disjoint_cells, polygon_intersection_geometry_updates, polygon_intersection_edge_buckets_updates, polygon_intersection_contains_properly_updates

def _apply_polygon_clip_updates(
    surface_raster_variant: list[RasterVariants],
    top_hint: numpy.ndarray | None,
    updates: PolygonClipUpdates,
) -> None:
    """Apply passed updates to the first RasterVariant.
    :param updates: Updates to the RasterVariant as a tuple of lists. Each list contains tuples with the cell location to update and any update data. Lists are in order of disjoint cells, polygon_intersection_geometry, polygon_intersection_edge_buckets, polygon_intersection_contains_properly
    """
    disjoint_cells, polygon_intersection_geometry_updates, polygon_intersection_edge_buckets_updates, polygon_intersection_contains_properly_updates = updates

    for j, i in disjoint_cells:
        for rv in surface_raster_variant:
            rv.set_location_in_variants(location=(j, i), new_value=numpy.nan, set_edge_interpolation=False)
        if top_hint is not None:
            top_hint[j][i] = numpy.nan

    for j, i, geoms in polygon_intersection_geometry_updates:
        surface_raster_variant[0].polygon_intersection_geometry[j][i] = geoms

    for j, i, edges in polygon_intersection_edge_buckets_updates:
        surface_raster_variant[0].polygon_intersection_edge_buckets[j][i] = edges

    for j, i in polygon_intersection_contains_properly_updates:
        surface_raster_variant[0].polygon_intersection_contains_properly[j][i] = True

def find_intersection_geometries(
    clippingPrint2DPoly: shapely.Polygon,
    quadPrint2DCoords: list[tuple[float, float]],
    preparedClippingPrint2DPoly: Any | None = None,
) -> tuple[bool, list[shapely.Geometry] | None, EdgeBuckets | None, bool]:
    """Check if clipping polygon and cell polygon have no/partial/complete overlap. Return whether to set the cell to NaN, intersection polygons, intersection edges. 
    
    Returned intersection edges are a flat list of all edges making up the intersection polygons sorted into buckets depending on them lying on a specific cardinal edge or not.

    :param clippingPrint2DPoly: Clipping polygon in print 2D coordinates
    :type clippingPrint2DPoly: shapely.Polygon
    :param quadPrint2DCoords: Cell quad vertices in print 2D coordinates
    :type quadPrint2DCoords: list[tuple[float, float]]
    :return: (Should set raster locations to NaN, polygon_intersection_geometry, polygon_intersection_edge_buckets, polygon_intersection_contains_properly)
    """
    # TODO: use shapely.box for optimization?
    quadPrint2DPoly = shapely.Polygon(quadPrint2DCoords)
    clipping_predicates = (
        preparedClippingPrint2DPoly
        if preparedClippingPrint2DPoly is not None
        else clippingPrint2DPoly
    )
    
    if clipping_predicates.contains_properly(quadPrint2DPoly): # quad is entirely inside polygon
        # We check if quad is entirely inside border poly with `contains_properly` instead using `contains` due to possible shared edges and points between quad and poly because a shared edge could have a neighboring cell with a partial intersection that does NOT contain the shared edge. i.e. There is a gap between the neighbor cell's intersection polygon and the shared edge. This neighboring cell will have a non-NaN value that does not work with our normal way of checking for wall existence on cells with full normal quads.
        return (False, None, None, True)
    
    if clipping_predicates.disjoint(quadPrint2DPoly): # quad is entirely not in polygon
        # set the all variants to NaN in that location
        #surface_raster_variant.set_location_in_variants(location=(j,i), new_value=numpy.nan, set_edge_interpolation=False)
        return (True, None, None, False) # the edge interpolation raster should not be changed and set to NaN
    else: # quad is partially inside poly or shares an edge/point
        intersection_geometry = clippingPrint2DPoly.intersection(quadPrint2DPoly)
        
        # Get flat list of all intersecting geometries excluding point geometries. Point geometries do not matter for wall generation. If an intersection only has points, we treat the cell like there were no intersections.
        flat_intersection_geometries = flatten_geometries([intersection_geometry])
        if len(flat_intersection_geometries) == 0:
            print("find_intersection_geometries: only point intersection geometries found")
            #surface_raster_variant.polygon_intersection_geometry[j][i] = flat_intersection_geometries
            
        #intersection geometry as a list of single line segments
        flat_intersection_borderEdges = flatten_geometries_borderEdge([intersection_geometry])
        
        #expect quad print2D vertices in CCW order NW SW SE NE
        #quad 2D edges in CCW order N W S E
        quadPrint2DNorthEdge = shapely.LineString([list(quadPrint2DCoords[3]),list(quadPrint2DCoords[0])])
        quadPrint2DWestEdge = shapely.LineString([list(quadPrint2DCoords[0]),list(quadPrint2DCoords[1])])
        quadPrint2DSouthEdge = shapely.LineString([list(quadPrint2DCoords[1]),list(quadPrint2DCoords[2])])
        quadPrint2DEastEdge = shapely.LineString([list(quadPrint2DCoords[2]),list(quadPrint2DCoords[3])])
        
        # sort every lines into buckets based on if the quad edge contains them
        intersection_edge_buckets = _empty_edge_buckets()
        for be in flat_intersection_borderEdges:
            bucket_key = sort_line_segment_based_contains(line_segment=be, north=quadPrint2DNorthEdge, west=quadPrint2DWestEdge, south=quadPrint2DSouthEdge, east=quadPrint2DEastEdge)
            
            # mark line segment as generating a wall if it is not along a quad edge
            if bucket_key[1] == False:
                be.make_wall = True
            
            if bucket_key[0] not in intersection_edge_buckets:
                print(f'Unknown bucket key {bucket_key}')
            intersection_edge_buckets[bucket_key[0]].append(be)
            
        return (False, flat_intersection_geometries, intersection_edge_buckets, False)

def find_polygon_clipping_edges(config: TouchTerrainConfig, dem: gdal.Dataset, surface_raster_variant: list[RasterVariants], top_hint: numpy.ndarray|None, print3D_resolution_mm: float):
    """Find the intersection polygon between each raster cell and the clipping polygon. Sort all individual edges of intersection polygons into buckets stored in RasterVariants based on if the edge lies on a cardinal direction edge of the cell quad. Marks all interior edges as needing walls created. 
    
    Use the first RasterVariant in the list for calculations. Propagate any "set to NaN" changes to any other RasterVariants
    """
    import geopandas

    if config.edge_clipping_polygon == None:
        print('find_polygon_clipping_edges: config.edge_fit_polygon_file not defined!')
        return
    if config.tileScale == None:
        print('find_polygon_clipping_edges: config.tileScale not defined!')
        return
    
    # if len(surface_raster_variant) == 0:
    #     raise ValueError("list of RasterVariant had no objects")
    
    # Read the GeoPackage into a GeoDataFrame
    polygon_boundary_gdf = geopandas.read_file(config.edge_clipping_polygon)

    # reproject vector boundary to same projected CRS as raster
    polygon_boundary_gdf = _project_polygon_boundary_gdf(
        polygon_boundary_gdf,
        dem.GetProjectionRef(),
    )

    # Initialize an empty list to store boundary Shapely Polygon objects
    shapely_polygons: list[shapely.Polygon] = []

    # Iterate through the GeoDataFrame and extract polygon geometries
    for index, row in polygon_boundary_gdf.iterrows():
        geometry = row.geometry
        # Check if the geometry is a Polygon or MultiPolygon
        if isinstance(geometry, shapely.Polygon):
            shapely_polygons.append(geometry)
        elif geometry.geom_type == 'MultiPolygon':
            # If it's a MultiPolygon, iterate through its individual polygons
            for poly in geometry.geoms:
                shapely_polygons.append(poly)
        else:
            print('unhandled geometry type when flattening clipping polygon file into polygon')

    # Now, 'shapely_polygons' contains a list of boundary Shapely Polygon objects
    if shapely_polygons:
        print(f"Found {len(shapely_polygons)} polygons in the GeoPackage.")
        for idx, poly in enumerate(shapely_polygons, start=1):
            print(f"Polygon {idx} area: {poly.area}")
    else:
        print("No polygons found in the GeoPackage or the specified layer.")
        
    ulx, pixelwidthx, xskew, uly, yskew, pixelheighty = dem.GetGeoTransform()
    ncol = dem.RasterXSize
    nrow = dem.RasterYSize
    # Calculate lower-right corner coordinates
    lrx = ulx + (ncol * pixelwidthx) + (nrow * xskew)
    lry = uly + (ncol * yskew) + (nrow * pixelheighty)
        
    # Create clipping_intersection_geometry and polygon_intersection_lines_buckets for the first time
    if surface_raster_variant[0].original is None:
        print('find_polygon_clipping_edges: original variant is None')
        return
    surface_raster_variant[0].polygon_intersection_geometry = numpy.empty(surface_raster_variant[0].original.shape, dtype=object)
    surface_raster_variant[0].polygon_intersection_edge_buckets = numpy.empty(surface_raster_variant[0].original.shape, dtype=object)
    surface_raster_variant[0].polygon_intersection_contains_properly = numpy.zeros(surface_raster_variant[0].original.shape, dtype=bool)
        
    # Precompute clipping polygons in print2D coordinates once (same for all cells)
    clipping_print2d_polys: list[shapely.Polygon] = []
    for clippingGeoPoly in shapely_polygons:
        clippingPrint2DPoly = geoCoordToPrint2DCoord(
            geoCoord2D=clippingGeoPoly,
            scale=config.tileScale,
            geoXMin=ulx,
            geoYMin=lry,
        )
        if isinstance(clippingPrint2DPoly, shapely.Polygon):
            clipping_print2d_polys.append(clippingPrint2DPoly)
        elif hasattr(clippingPrint2DPoly, "geoms"):
            for geom in clippingPrint2DPoly.geoms:
                if isinstance(geom, shapely.Polygon):
                    clipping_print2d_polys.append(geom)
        else:
            print("clippingPrint2DPoly is not a shapely Polygon")

    clipping_print2d_polys = _union_clipping_polygons(
        clipping_print2d_polys,
    )

    # determine intersection for polygon(s) in boundary and each cell quad
    rows = surface_raster_variant[0].original.shape[0]
    cols = surface_raster_variant[0].original.shape[1]

    # Decide whether to use worker row chunks for clipping.
    use_workers = config.CPU_cores_to_use not in (None, 1)
    worker_fn = functools.partial(
        _process_polygon_clip_rows,
        clipping_print2d_polys=clipping_print2d_polys,
        cell_size_mm=print3D_resolution_mm,
        tile_y_shape=rows,
        grid_width=cols,
    )

    if not use_workers:
        updates = worker_fn((0, rows))
        _apply_polygon_clip_updates(surface_raster_variant, top_hint, updates)
    else:
        available_cores = max(1, (os.cpu_count() or 1) - 1)
        requested_cores = (
            available_cores
            if config.CPU_cores_to_use == 0
            else config.CPU_cores_to_use
        )
        worker_cores = max(1, min(requested_cores, rows))
        _log_info(f"Computing cell and clipping polygon with {worker_cores} workers")
        row_ranges = _polygon_clip_row_ranges(rows, worker_cores)

        with ThreadPoolExecutor(max_workers=worker_cores) as executor:
            for updates in executor.map(worker_fn, row_ranges):
                _apply_polygon_clip_updates(
                    surface_raster_variant,
                    top_hint,
                    updates,
                )

def mark_overlapping_edges_for_walls(cell_1_edges: list[BorderEdge], cell_2_edges: list[BorderEdge]):
    """Mark overlapping edges between a cell and neighbor cell to make a wall. Sets the make_wall property of only the cell with the Polygon side of a match. 

    :param cell_1_edges: The target cell
    :type cell_1_edges: list[BorderEdge]
    :param cell_2_edges: The neighbor cell
    :type cell_2_edges: list[BorderEdge]
    """

    # check if cell 1 edge contains cell 2 edge or if cell 2 edge contains cell 1 edge
    
    # split the containing edge by the conatined edge
    
    # mark the contained edge and matching split containing edge sub-edge as skip_future_eval_for_walls to skip in future loops. Check if wall is needed based on if matched edge from a cell is a polygon_line and matched edge from other cell is NOT a polygon_line. L<>PL = make wall. L<>L or PL<>PL = no wall. Mark whichever of these 2 edges is on the PL side as make_wall.
    
    # delete the containing edge from the list, add the new split edges to the list end
    
    # if containing edge was on cell 1, do not increment iterator
    
    # if cell 1 edge is same as cell 2 edge, make wall on P side, mark the edges as skip
    
    # all edges on cell 1 and 2 should match with an edge on other cell at the end of the loop. i.e. all edges on the shared side of both cells should be marked as skip at the very end
    
    c1eIdx = 0
    while c1eIdx < len(cell_1_edges):
        c1e = cell_1_edges[c1eIdx]
        if c1e.skip_future_eval_for_walls:
            c1eIdx += 1
            continue
        c2eIdx = 0
        while c2eIdx < len(cell_2_edges):
            c2e = cell_2_edges[c2eIdx]
            if c2e.skip_future_eval_for_walls:
                c2eIdx += 1
                continue
            make_wall = c1e.polygon_line != c2e.polygon_line # Should we make a wall on matching edges? L<>L and PL<>PL have no wall
            wall_ce = BorderEdge(geometry=shapely.LineString())
            if make_wall: # mark wall on the P side
                if c1e.polygon_line:
                    wall_ce = c1e
                elif c2e.polygon_line:
                    wall_ce = c2e
            
            containingEdgeList: list[BorderEdge] = []
            containingEdgeIdx: int = -1
            splitter: BorderEdge | None = None

            if c1e.geometry.equals(c2e.geometry):
                wall_ce.make_wall = make_wall
                c1e.skip_future_eval_for_walls = True
                c2e.skip_future_eval_for_walls = True
            elif c1e.geometry.contains(c2e.geometry):
                containingEdgeList = cell_1_edges
                containingEdgeIdx = c1eIdx
                splitter = c2e
            elif c2e.geometry.contains(c1e.geometry):
                containingEdgeList = cell_2_edges
                containingEdgeIdx = c2eIdx
                splitter = c1e
            # If edges are not equal but overlap each other, split edges by each other to get sub edges
            if splitter: # check for side effect of contains() == True
                sub_edges = unary_union([c1e.geometry, c2e.geometry])
                splitter.skip_future_eval_for_walls = True
                splitter.make_wall = splitter is wall_ce
                for segment in sub_edges.geoms:
                    is_matching_splitter = segment.equals(splitter.geometry)
                    segment_make_wall = is_matching_splitter and containingEdgeList[containingEdgeIdx].polygon_line and make_wall
                    containingEdgeList.append(BorderEdge(
                        geometry=segment, 
                        polygon_line=containingEdgeList[containingEdgeIdx].polygon_line, 
                        skip_future_eval_for_walls=is_matching_splitter, 
                        make_wall=segment_make_wall
                        ))
                del containingEdgeList[containingEdgeIdx] #remove current evaluated cell 1 edge because it has been replaced by the sub edges
                if containingEdgeList is cell_1_edges:
                    # Move onto the next cell 1 edge because we matched and split c1 edge. Do not increment cell 1 iterator because we removed the cell 1 edge we just evaluated
                    c1eIdx -= 1 # balance out c1 iterator increment that happens after c2 loop ends
                    break 
                elif containingEdgeList is cell_2_edges:
                    # Move onto the next cell 2 edge because we matched and split a c2 edge. Skip incrementing cell 2 iterator because we removed the cell 2 edge we just evaluated
                    continue
            
            c2eIdx += 1
        c1eIdx += 1

def _cell_location_in_range(
    location: tuple[int, int],
    shape: tuple[int, int],
) -> bool:
    return 0 <= location[0] < shape[0] and 0 <= location[1] < shape[1]


def _cell_has_mesh(
    elevation_raster: numpy.ndarray,
    location: tuple[int, int],
) -> bool:
    return not numpy.isnan(elevation_raster[location])


def _cell_is_contained(
    polygon_intersection_contains_properly: numpy.ndarray | None,
    location: tuple[int, int],
) -> bool:
    return (
        polygon_intersection_contains_properly is not None
        and bool(polygon_intersection_contains_properly[location])
    )


def _cell_clip_state(
    polygon_intersection_edge_buckets: numpy.ndarray,
    polygon_intersection_contains_properly: numpy.ndarray | None,
    elevation_raster: numpy.ndarray,
    location: tuple[int, int],
) -> str:
    """Return outside, contained, or partial for one clipped cell."""
    if not _cell_location_in_range(location, elevation_raster.shape):
        return "outside"
    if not _cell_has_mesh(elevation_raster, location):
        return "outside"
    if _cell_is_contained(polygon_intersection_contains_properly, location):
        return "contained"
    if isinstance(polygon_intersection_edge_buckets[location], dict):
        return "partial"
    raise ValueError(
        "Clipped cell has mesh but is neither contained nor partial at "
        f"row={location[0]}, col={location[1]}."
    )


def _quad_side_line(
    cell_location: tuple[int, int],
    side: str,
    cell_size_mm: float,
    tile_y_shape: int,
) -> shapely.LineString:
    quad_coords = arrayCellCoordToQuadPrint2DCoords(
        array_coord_2D=(cell_location[1], cell_location[0]),
        cell_size=cell_size_mm,
        tile_y_shape=tile_y_shape,
    )
    side_coords = {
        "N": (quad_coords[3], quad_coords[0]),
        "W": (quad_coords[0], quad_coords[1]),
        "S": (quad_coords[1], quad_coords[2]),
        "E": (quad_coords[2], quad_coords[3]),
    }
    return shapely.LineString(side_coords[side])


def _contained_side_edge(
    cell_location: tuple[int, int],
    side: str,
    cell_size_mm: float,
    tile_y_shape: int,
    make_wall: bool = False,
) -> BorderEdge:
    return BorderEdge(
        geometry=_quad_side_line(
            cell_location,
            side,
            cell_size_mm,
            tile_y_shape,
        ),
        polygon_line=True,
        make_wall=make_wall,
    )


def _mark_all_edges_for_wall(edges: list[BorderEdge]) -> None:
    for edge in edges:
        edge.make_wall = True


def _side_edges_for_wall_marking(
    polygon_intersection_edge_buckets: numpy.ndarray,
    location: tuple[int, int],
    state: str,
    side: str,
    cell_size_mm: float,
    tile_y_shape: int,
) -> list[BorderEdge]:
    if state == "partial":
        return polygon_intersection_edge_buckets[location][side]
    if state == "contained":
        return [
            _contained_side_edge(
                location,
                side,
                cell_size_mm,
                tile_y_shape,
            )
        ]
    return []


def _mark_shared_side_for_walls(
    polygon_intersection_edge_buckets: numpy.ndarray,
    polygon_intersection_contains_properly: numpy.ndarray | None,
    elevation_raster: numpy.ndarray,
    current_location: tuple[int, int],
    neighbor_location: tuple[int, int],
    current_side: str,
    cell_size_mm: float,
) -> None:
    tile_y_shape = polygon_intersection_edge_buckets.shape[0]
    current_state = _cell_clip_state(
        polygon_intersection_edge_buckets,
        polygon_intersection_contains_properly,
        elevation_raster,
        current_location,
    )
    neighbor_state = _cell_clip_state(
        polygon_intersection_edge_buckets,
        polygon_intersection_contains_properly,
        elevation_raster,
        neighbor_location,
    )
    neighbor_side = OPPOSITE_SIDE[current_side]

    if current_state == "outside" and neighbor_state == "outside":
        return
    if current_state == "contained" and neighbor_state == "contained":
        return

    if current_state == "partial" and neighbor_state == "outside":
        _mark_all_edges_for_wall(
            polygon_intersection_edge_buckets[current_location][current_side]
        )
        return
    if current_state == "outside" and neighbor_state == "partial":
        _mark_all_edges_for_wall(
            polygon_intersection_edge_buckets[neighbor_location][neighbor_side]
        )
        return

    if "partial" not in (current_state, neighbor_state):
        # Contained-vs-outside walls are ordinary cardinal raster borders.
        return

    current_edges = _side_edges_for_wall_marking(
        polygon_intersection_edge_buckets,
        current_location,
        current_state,
        current_side,
        cell_size_mm,
        tile_y_shape,
    )
    neighbor_edges = _side_edges_for_wall_marking(
        polygon_intersection_edge_buckets,
        neighbor_location,
        neighbor_state,
        neighbor_side,
        cell_size_mm,
        tile_y_shape,
    )
    mark_overlapping_edges_for_walls(
        cell_1_edges=current_edges,
        cell_2_edges=neighbor_edges,
    )


def mark_shared_edges_of_cell_for_walls(
    polygon_intersection_edge_buckets: numpy.ndarray,
    elevation_raster: numpy.ndarray,
    cell_location: tuple[int, int],
    direction: tuple[int, int],
    *,
    polygon_intersection_contains_properly: numpy.ndarray | None = None,
    cell_size_mm: float | None = None,
) -> None:
    """Mark clipped shared side edges that need surface polygon walls."""
    if cell_size_mm is None:
        cell_size_mm = 1.0
    if direction[0] != 0:
        current_side = "N" if direction[0] == -1 else "S"
        neighbor_location = (
            cell_location[0] + direction[0],
            cell_location[1],
        )
        _mark_shared_side_for_walls(
            polygon_intersection_edge_buckets,
            polygon_intersection_contains_properly,
            elevation_raster,
            cell_location,
            neighbor_location,
            current_side,
            cell_size_mm,
        )
    if direction[1] != 0:
        current_side = "W" if direction[1] == -1 else "E"
        neighbor_location = (
            cell_location[0],
            cell_location[1] + direction[1],
        )
        _mark_shared_side_for_walls(
            polygon_intersection_edge_buckets,
            polygon_intersection_contains_properly,
            elevation_raster,
            cell_location,
            neighbor_location,
            current_side,
            cell_size_mm,
        )


def mark_shared_edges_for_walls(
    polygon_intersection_edge_buckets: numpy.ndarray,
    elevation_raster: numpy.ndarray,
    direction: tuple[int, int],
    *,
    polygon_intersection_contains_properly: numpy.ndarray | None = None,
    cell_size_mm: float | None = None,
) -> None:
    """Mark clipped side edges that need surface polygon walls."""
    if cell_size_mm is None:
        cell_size_mm = 1.0
    row_count = polygon_intersection_edge_buckets.shape[0]
    progress_step = max(1, row_count // 10)
    for j in range(row_count):
        if j == 0 or j == row_count - 1 or j % progress_step == 0:
            _log_info(
                "Marking clipped shared edges for row "
                f"{j}/{row_count}"
            )
        for i in range(polygon_intersection_edge_buckets.shape[1]):
            mark_shared_edges_of_cell_for_walls(
                polygon_intersection_edge_buckets=(
                    polygon_intersection_edge_buckets
                ),
                elevation_raster=elevation_raster,
                cell_location=(j, i),
                direction=direction,
                polygon_intersection_contains_properly=(
                    polygon_intersection_contains_properly
                ),
                cell_size_mm=cell_size_mm,
            )


def clipping_wall_visualization_edge_records(
    polygon_intersection_edge_buckets: numpy.ndarray,
    elevation_raster: numpy.ndarray,
    polygon_intersection_contains_properly: numpy.ndarray | None,
    cell_size_mm: float,
) -> list[list[BorderEdgePlotRecord]]:
    """Return grouped debug plot records for clipped wall ownership."""
    edge_groups: list[list[BorderEdgePlotRecord]] = []
    tile_y_shape = polygon_intersection_edge_buckets.shape[0]

    for location, buckets in numpy.ndenumerate(polygon_intersection_edge_buckets):
        if isinstance(buckets, dict):
            edge_groups.append(
                [
                    BorderEdgePlotRecord(edge=edge)
                    for side in EDGE_BUCKET_KEYS
                    for edge in buckets[side]
                ]
            )

    cardinal_sides = {
        "N": (-1, 0),
        "W": (0, -1),
        "S": (1, 0),
        "E": (0, 1),
    }
    for location, _value in numpy.ndenumerate(elevation_raster):
        if not _cell_is_contained(
            polygon_intersection_contains_properly,
            location,
        ):
            continue
        for side, offset in cardinal_sides.items():
            neighbor_location = (
                location[0] + offset[0],
                location[1] + offset[1],
            )
            if (
                not _cell_location_in_range(
                    neighbor_location,
                    elevation_raster.shape,
                )
                or not _cell_has_mesh(elevation_raster, neighbor_location)
            ):
                edge_groups.append(
                    [
                        BorderEdgePlotRecord(
                            edge=_contained_side_edge(
                                location,
                                side,
                                cell_size_mm,
                                tile_y_shape,
                                make_wall=True,
                            ),
                            source="contained_cardinal_wall",
                        )
                    ]
                )
    return edge_groups


def clipping_wall_visualization_edges(
    polygon_intersection_edge_buckets: numpy.ndarray,
    elevation_raster: numpy.ndarray,
    polygon_intersection_contains_properly: numpy.ndarray | None,
    cell_size_mm: float,
) -> list[list[BorderEdge]]:
    """Return grouped raw edges for debug plots of clipped wall ownership."""
    return [
        [record.edge for record in edge_group]
        for edge_group in clipping_wall_visualization_edge_records(
            polygon_intersection_edge_buckets=(
                polygon_intersection_edge_buckets
            ),
            elevation_raster=elevation_raster,
            polygon_intersection_contains_properly=(
                polygon_intersection_contains_properly
            ),
            cell_size_mm=cell_size_mm,
        )
    ]
