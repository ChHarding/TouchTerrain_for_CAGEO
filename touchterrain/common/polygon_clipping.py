import geopandas
import numpy
import shapely

# try to import gdal from multiple sources
try:
    import gdal
except ImportError as err:
    from osgeo import gdal

from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.user_config import TouchTerrainConfig
from touchterrain.common.utils import geoCoordToPrint2DCoord, arrayCellCoordToQuadPrint2DCoords
from touchterrain.common.shapely_utils import flatten_geometries, flatten_geometries_borderEdge, sort_line_segment_based_contains

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
    gdf = geopandas.read_file(config.edge_fit_polygon_file)

    # reproject vector boundary to same projected CRS as raster
    gdf = gdf.to_crs(dem.GetProjectionRef())

    # Initialize an empty list to store Shapely Polygon objects
    shapely_polygons = []

    # Iterate through the GeoDataFrame and extract polygon geometries
    for index, row in gdf.iterrows():
        geometry = row.geometry
        # Check if the geometry is a Polygon or MultiPolygon
        if isinstance(geometry, shapely.Polygon):
            shapely_polygons.append(geometry)
        elif geometry.geom_type == 'MultiPolygon':
            # If it's a MultiPolygon, iterate through its individual polygons
            for poly in geometry.geoms:
                shapely_polygons.append(poly)

    # Now, 'shapely_polygons' contains a list of Shapely Polygon objects
    # You can access them and perform further operations
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
    if surface_raster_variant.original == None:
        print('find_polygon_clipping_edges: original variant is None')
        return
    surface_raster_variant.polygon_intersection_geometry = numpy.empty(surface_raster_variant.original.shape, dtype=object)
    surface_raster_variant.polygon_intersection_lines_buckets = numpy.empty(surface_raster_variant.original.shape, dtype=object)
        
    # determine intersection for polygon(s) in boundary and each cell quad
    for clippingGeoPoly in shapely_polygons:
        clippingPrint2DPoly = geoCoordToPrint2DCoord(geoCoord2D=clippingGeoPoly, scale=config.tileScale, geoXMin=ulx, geoYMin=lry)
        for j in range(0, surface_raster_variant.original.shape[0]): # Y
            for i in range(0, surface_raster_variant.original.shape[1]): # X
                #arrayCellCoordToGeoCoord(array_coord_2D=(i,j), geo_transform=dem.GetGeoTransform())
                quadPrint2DCoords = arrayCellCoordToQuadPrint2DCoords(array_coord_2D=(i,j), cell_size=print3D_resolution_mm, tile_y_shape=surface_raster_variant.original.shape[0])
                # TODO: use shapely.box for optimization?
                quadPrint2DPoly = shapely.Polygon(quadPrint2DCoords)
                
                if isinstance(clippingPrint2DPoly, shapely.Polygon):
                    if clippingPrint2DPoly.disjoint(quadPrint2DPoly): # quad is entirely not in polygon
                        # set the all variants to NaN in that location
                        surface_raster_variant.set_location_in_variants(location=(j,i), new_value=numpy.nan, set_edge_interpolation=False)
                    elif clippingPrint2DPoly.contains_properly(quadPrint2DPoly): # quad is entirely inside polygon
                        # We check if quad is entirely inside border poly with `contains_properly` instead using `contains` due to possible shared edges and points between quad and poly because a shared edge could have a neighboring cell with a partial intersection that does NOT contain the shared edge. i.e. There is a gap between the neighbor cell's intersection polygon and the shared edge. This neighboring cell will have a non-NaN value that does not work with our normal way of checking for wall existence on cells with full normal quads.
                        # leave the cell unchanged
                        pass
                    else: # quad is partly inside poly or shares an edge/point
                        intersection_geometry = clippingPrint2DPoly.intersection(quadPrint2DPoly)
                        
                        # Get flat list of all intersecting geometries excluding point geometries. Point geometries do not matter for wall generation. If an intersection only has points, we treat the cell like there were no intersections.
                        flat_intersection_geometries = flatten_geometries([intersection_geometry])
                        if len(flat_intersection_geometries) > 0:
                            surface_raster_variant.polygon_intersection_geometry[j][i] = flat_intersection_geometries
                            
                        #intersection geometry as a list of single line segments
                        flat_intersection_borderEdges = flatten_geometries_borderEdge([intersection_geometry])
                        
                        #qual 2D edges in CCW order N W S E
                        quadPrint2DNorthEdge = shapely.LineString([list(quadPrint2DCoords[3]),list(quadPrint2DCoords[0])])
                        quadPrint2DWestEdge = shapely.LineString([list(quadPrint2DCoords[0]),list(quadPrint2DCoords[1])])
                        quadPrint2DSouthEdge = shapely.LineString([list(quadPrint2DCoords[1]),list(quadPrint2DCoords[2])])
                        quadPrint2DEastEdge = shapely.LineString([list(quadPrint2DCoords[2]),list(quadPrint2DCoords[3])])
                        
                        # sort every lines into buckets based on if the quad edge contains them
                        intersection_lines_buckets = { 
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
                            
                            if bucket_key[0] not in intersection_lines_buckets:
                                print(f'Unknown bucket key {bucket_key}')
                            intersection_lines_buckets[bucket_key[0]].append(be)
                        
                else:
                    print("clippingPrint2DPoly is not a shapely Polygon")
                    break