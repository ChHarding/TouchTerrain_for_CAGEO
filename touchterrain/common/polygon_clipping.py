import geopandas
import numpy
import shapely
from shapely.ops import unary_union

# try to import gdal from multiple sources
try:
    import gdal
except ImportError as err:
    from osgeo import gdal

from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.user_config import TouchTerrainConfig
from touchterrain.common.utils import geoCoordToPrint2DCoord, arrayCellCoordToQuadPrint2DCoords
from touchterrain.common.shapely_utils import flatten_geometries, flatten_geometries_borderEdge, sort_line_segment_based_contains
from touchterrain.common.shapely_plot import plot_intersection_of_shapely_polygons

def find_intersection_geometries(clippingPrint2DPoly: shapely.Polygon, quadPrint2DCoords: list[tuple[float, float]]) -> tuple[bool, list[shapely.Geometry] | None, dict[str, list[BorderEdge]] | None]:
    """Check if clipping polygon and cell polygon have no/partial/complete overlap. Return whether to set the cell to NaN, intersection polygons, intersection edges. 
    
    Returned intersection edges are a flat list of all edges making up the intersection polygons sorted into buckets depending on them lying on a specific cardinal edge or not.

    :param clippingPrint2DPoly: Clipping polygon in print 2D coordinates
    :type clippingPrint2DPoly: shapely.Polygon
    :param quadPrint2DCoords: Cell quad vertices in print 2D coordinates
    :type quadPrint2DCoords: list[tuple[float, float]]
    :return: (Should set raster locations to NaN, polygon_intersection_geometry, polygon_intersection_edge_buckets)
    :rtype: tuple[bool, list[shapely.Geometry]]
    """
    # TODO: use shapely.box for optimization?
    quadPrint2DPoly = shapely.Polygon(quadPrint2DCoords)
    
    if clippingPrint2DPoly.disjoint(quadPrint2DPoly): # quad is entirely not in polygon
        # set the all variants to NaN in that location
        #surface_raster_variant.set_location_in_variants(location=(j,i), new_value=numpy.nan, set_edge_interpolation=False)
        return (True, None, None) # the edge interpolation raster should not be changed and set to NaN
    elif clippingPrint2DPoly.contains_properly(quadPrint2DPoly): # quad is entirely inside polygon
        # We check if quad is entirely inside border poly with `contains_properly` instead using `contains` due to possible shared edges and points between quad and poly because a shared edge could have a neighboring cell with a partial intersection that does NOT contain the shared edge. i.e. There is a gap between the neighbor cell's intersection polygon and the shared edge. This neighboring cell will have a non-NaN value that does not work with our normal way of checking for wall existence on cells with full normal quads.
        # leave the cell unchanged
        pass
    else: # quad is partially inside poly or shares an edge/point
        intersection_geometry = clippingPrint2DPoly.intersection(quadPrint2DPoly)
        
        # Get flat list of all intersecting geometries excluding point geometries. Point geometries do not matter for wall generation. If an intersection only has points, we treat the cell like there were no intersections.
        flat_intersection_geometries = flatten_geometries([intersection_geometry])
        if len(flat_intersection_geometries) == 0:
            print("find_intersection_geometries: only point intersection geometries found")
            #surface_raster_variant.polygon_intersection_geometry[j][i] = flat_intersection_geometries
            pass
            
        #intersection geometry as a list of single line segments
        flat_intersection_borderEdges = flatten_geometries_borderEdge([intersection_geometry])
        
        #qual 2D edges in CCW order N W S E
        quadPrint2DNorthEdge = shapely.LineString([list(quadPrint2DCoords[3]),list(quadPrint2DCoords[0])])
        quadPrint2DWestEdge = shapely.LineString([list(quadPrint2DCoords[0]),list(quadPrint2DCoords[1])])
        quadPrint2DSouthEdge = shapely.LineString([list(quadPrint2DCoords[1]),list(quadPrint2DCoords[2])])
        quadPrint2DEastEdge = shapely.LineString([list(quadPrint2DCoords[2]),list(quadPrint2DCoords[3])])
        
        # sort every lines into buckets based on if the quad edge contains them
        intersection_edge_buckets = { 
                                        'N': [],
                                        'W': [],
                                        'S': [],
                                        'E': [],
                                        'other': [],}
        for be in flat_intersection_borderEdges:
            bucket_key = sort_line_segment_based_contains(line_segment=be, north=quadPrint2DNorthEdge, west=quadPrint2DWestEdge, south=quadPrint2DSouthEdge, east=quadPrint2DEastEdge)
            
            # mark line segment as generating a wall if it is not along a quad edge
            if bucket_key[1] == False:
                be.make_wall = True
            
            if bucket_key[0] not in intersection_edge_buckets:
                print(f'Unknown bucket key {bucket_key}')
            intersection_edge_buckets[bucket_key[0]].append(be)
            
        return (False, flat_intersection_geometries, intersection_edge_buckets)
    
    return (False, None, None)

def find_cell_and_clipping_poly_intersection(surface_raster_variant: RasterVariants, cellLocation: tuple[int, int], clippingPrint2DPoly: shapely.Polygon, quadPrint2DCoords: list[tuple[float, float]]):
    intersection_geometries_result = find_intersection_geometries(clippingPrint2DPoly=clippingPrint2DPoly, quadPrint2DCoords=quadPrint2DCoords)
                    
    # Should set cell values to NaN
    if intersection_geometries_result[0]:
        surface_raster_variant.set_location_in_variants(location=cellLocation, new_value=numpy.nan, set_edge_interpolation=False)
    
    # Set cell all intersection geometries flattened to polygons
    if intersection_geometries_result[1] is not None:
        surface_raster_variant.polygon_intersection_geometry[cellLocation[0]][cellLocation[1]] = intersection_geometries_result[1]
        
    # Set cell all intersection geometries flattened to single edges and sorted into buckets in a dict
    if intersection_geometries_result[2] is not None:
        surface_raster_variant.polygon_intersection_edge_buckets[cellLocation[0]][cellLocation[1]] = intersection_geometries_result[2]
    
def find_polygon_clipping_edges(config: TouchTerrainConfig, dem: gdal.Dataset, surface_raster_variant: RasterVariants, print3D_resolution_mm: float):
    """Find the intersection polygon between each raster cell and the clipping polygon. Sort all individual edges of intersection polygons into buckets stored in RasterVariants based on if the edge lies on a cardinal direction edge of the cell quad. Marks all interior edges as needing walls created. 
    """
    if config.edge_fit_polygon_file == None:
        print('find_polygon_clipping_edges: config.edge_fit_polygon_file not defined!')
        return
    if config.tileScale == None:
        print('find_polygon_clipping_edges: config.tileScale not defined!')
        return
    
    # Read the GeoPackage into a GeoDataFrame
    polygon_boundary_gdf = geopandas.read_file(config.edge_fit_polygon_file)

    # reproject vector boundary to same projected CRS as raster
    polygon_boundary_gdf = polygon_boundary_gdf.to_crs(dem.GetProjectionRef())

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
        print(f"First polygon's area: {shapely_polygons[0].area}")
    else:
        print("No polygons found in the GeoPackage or the specified layer.")
        
    ulx, pixelwidthx, xskew, uly, yskew, pixelheighty = dem.GetGeoTransform()
    ncol = dem.RasterXSize
    nrow = dem.RasterYSize
    # Calculate lower-right corner coordinates
    lrx = ulx + (ncol * pixelwidthx) + (nrow * xskew)
    lry = uly + (ncol * yskew) + (nrow * pixelheighty)
        
    # Create clipping_intersection_geometry and polygon_intersection_lines_buckets for the first time
    if surface_raster_variant.original is None:
        print('find_polygon_clipping_edges: original variant is None')
        return
    surface_raster_variant.polygon_intersection_geometry = numpy.empty(surface_raster_variant.original.shape, dtype=object)
    surface_raster_variant.polygon_intersection_edge_buckets = numpy.empty(surface_raster_variant.original.shape, dtype=object)
        
    # determine intersection for polygon(s) in boundary and each cell quad
    for clippingGeoPoly in shapely_polygons:
        clippingPrint2DPoly = geoCoordToPrint2DCoord(geoCoord2D=clippingGeoPoly, scale=config.tileScale, geoXMin=ulx, geoYMin=lry)
        for j in range(0, surface_raster_variant.original.shape[0]): # Y
            for i in range(0, surface_raster_variant.original.shape[1]): # X
                #arrayCellCoordToGeoCoord(array_coord_2D=(i,j), geo_transform=dem.GetGeoTransform())
                quadPrint2DCoords = arrayCellCoordToQuadPrint2DCoords(array_coord_2D=(i,j), cell_size=print3D_resolution_mm, tile_y_shape=surface_raster_variant.original.shape[0])
                # TODO: use shapely.box for optimization?
                #quadPrint2DPoly = shapely.Polygon(quadPrint2DCoords)
                
                if isinstance(clippingPrint2DPoly, shapely.Polygon):
                    #print(f'{j} {i}') # debug print the Y X of the cell
                    
                    find_cell_and_clipping_poly_intersection(surface_raster_variant=surface_raster_variant, cellLocation=(j,i), clippingPrint2DPoly=clippingPrint2DPoly, quadPrint2DCoords=quadPrint2DCoords)
                    
                    # Debug plot of a clipping and cell polygon intersection
                    if i==97 and j==45:
                        quadPrint2DPoly = shapely.Polygon(quadPrint2DCoords)
                        
                        plot_intersection_of_shapely_polygons([clippingPrint2DPoly, quadPrint2DPoly])
                        pass
                else:
                    print("clippingPrint2DPoly is not a shapely Polygon")
                    break

def mark_overlapping_edges_for_walls(cell_1_edges: list[BorderEdge], cell_2_edges: list[BorderEdge]):
    """Mark overlapping edges between a cell and neighbor cell to make a wall. Sets the make_wall property of only the target cell. 

    :param cell_1_edges: The target cell
    :type cell_1_edges: list[BorderEdge]
    :param cell_2_edges: The neighbor cell
    :type cell_2_edges: list[BorderEdge]
    """

    # check if cell 1 edge contains cell 2 edge or if cell 2 edge contains cell 1 edge
    
    # split the containing edge by the conatined edge
    
    # mark the contained edge and matching split containing edge sub-edge as skip_future_eval_for_walls to skip in future loops. Check if wall is needed based on if matched edge from a cell is a polygon_line and matched edge from other cell is NOT a polygon_line. L<>PL = make wall. L<>L or PL<>PL = no wall. Mark whichever of these 2 edges is on the cell 1 side as make_wall.
    
    # delete the containing edge from the list, add the new split edges to the list end
    
    # if containing edge was on cell 1, do not increment iterator
    
    # if cell 1 edge is same as cell 2 edge, make wall on cell 1 side, mark the edges as skip
    
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
            
            containingEdgeList: list[BorderEdge] = []
            containingEdgeIdx: int = -1
            splitter: BorderEdge | None = None

            if c1e.geometry.equals(c2e.geometry):
                c1e.make_wall = make_wall
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
                splitter.make_wall = containingEdgeList is not cell_1_edges
                for segment in sub_edges.geoms:
                    is_matching_splitter = segment.equals(splitter.geometry)
                    segment_make_wall = is_matching_splitter and containingEdgeList is cell_1_edges and make_wall
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

def mark_shared_edges_of_cell_for_walls(polygon_intersection_edge_buckets: numpy.ndarray, cell_location: tuple[int, int], direction: tuple[int, int]):
    """Mark shared edges of a cell and the neighbor cell in the specified direction to have a wall if the edges overlap.

    :param polygon_intersection_edge_buckets: polygon_intersection_edge_buckets of type ndarray with dtype=object dict[str,list[BorderEdge]]. Should be the ndarray from RasterVariants.
    :type polygon_intersection_edge_buckets: numpy.ndarray
    :param cell_location: Target cell location in Y,X order
    :type cell_location: tuple[int, int]
    :param direction: Direction of neighboring cell in Y,X order
    :type direction: tuple[int, int]
    """
    cell_1_edge_buckets = polygon_intersection_edge_buckets[cell_location[0],cell_location[1]]
    # Get 2 separate cell "2"s, one in vertical direction, one in horizontal direction
    cell_2_location_y = cell_location[0]+direction[0]
    cell_2_location_x = cell_location[1]+direction[1]
    
    if isinstance(cell_1_edge_buckets, dict) and isinstance(cell_1_edge_buckets, dict):
        if cell_2_location_y >= 0 and cell_2_location_y < polygon_intersection_edge_buckets.shape[0]:
            cell_2_y_edge_buckets = polygon_intersection_edge_buckets[cell_2_location_y,cell_location[1]]
            if direction[0] == -1: #N
                mark_overlapping_edges_for_walls(cell_1_edges=cell_1_edge_buckets['N'], cell_2_edges=cell_2_y_edge_buckets['S'])
            elif direction[0] == 1: #S
                mark_overlapping_edges_for_walls(cell_1_edges=cell_1_edge_buckets['S'], cell_2_edges=cell_2_y_edge_buckets['N'])
            elif direction[0] != 0:
                print(f'mark_shared_edges_of_cell_for_walls: unsupported direction of {direction[0]}')
            
        if cell_2_location_x >= 0 and cell_2_location_x < polygon_intersection_edge_buckets.shape[1]:
            cell_2_x_edge_buckets = polygon_intersection_edge_buckets[cell_location[0],cell_2_location_x]
            if direction[1] == -1: #W
                mark_overlapping_edges_for_walls(cell_1_edges=cell_1_edge_buckets['W'], cell_2_edges=cell_2_x_edge_buckets['E'])
            elif direction[1] == 1: #E
                mark_overlapping_edges_for_walls(cell_1_edges=cell_1_edge_buckets['E'], cell_2_edges=cell_2_x_edge_buckets['W'])
            elif direction[1] != 0:
                print(f'mark_shared_edges_of_cell_for_walls: unsupported direction of {direction[1]}')
        
    else:
        print('mark_shared_edges_of_cell_for_walls: cell 1 or 2 edge buckets is not dict')
    
    pass

def mark_shared_edges_for_walls(polygon_intersection_edge_buckets: numpy.ndarray, direction: tuple[int, int]):
    """Mark shared edges of all cells in an ndarray and the neighbor cell in the specified direction to have a wall if the edges overlap.
    """
    for j in range(0, polygon_intersection_edge_buckets.shape[0]): # Y
        for i in range(0, polygon_intersection_edge_buckets.shape[1]): # X
            mark_shared_edges_of_cell_for_walls(polygon_intersection_edge_buckets, cell_location=(j,i), direction=direction)
