import geopandas
from shapely.geometry import Polygon, Point
import shapely

# Read the GeoPackage into a GeoDataFrame
gdf = geopandas.read_file('fr.gpkg')

# Initialize an empty list to store Shapely Polygon objects
shapely_polygons = []

# Iterate through the GeoDataFrame and extract polygon geometries
for index, row in gdf.iterrows():
    geometry = row.geometry
    # Check if the geometry is a Polygon or MultiPolygon
    if isinstance(geometry, Polygon):
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
    
exterior_vertices = shapely.points(shapely_polygons.exterior.coords)

shapely.get_num_points(shapely_polygons[0].boundary)

print("\nInterior Rings Vertices:")
for i, interior_ring in enumerate(shapely_polygons[0].interiors):
    print(f"  Hole {i+1}:")
    print(f"    {list(interior_ring.coords)}")
    
#reproject
gdf_re = gdf.to_crs('PROJCS["USA_Contiguous_Lambert_Conformal_Conic",GEOGCS["NAD83",DATUM["North_American_Datum_1983",SPHEROID["GRS 1980",6378137,298.257222101004,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6269"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4269"]],PROJECTION["Lambert_Conformal_Conic_2SP"],PARAMETER["latitude_of_origin",39],PARAMETER["central_meridian",-96],PARAMETER["standard_parallel_1",33],PARAMETER["standard_parallel_2",45],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH]]')

shapely_polygons_re = []

# Iterate through the GeoDataFrame and extract polygon geometries
for index, row in gdf_re.iterrows():
    geometry = row.geometry
    # Check if the geometry is a Polygon or MultiPolygon
    if isinstance(geometry, Polygon):
        shapely_polygons_re.append(geometry)
    elif geometry.geom_type == 'MultiPolygon':
        # If it's a MultiPolygon, iterate through its individual polygons
        for poly in geometry.geoms:
            shapely_polygons_re.append(poly)

# Now, 'shapely_polygons_re' contains a list of Shapely Polygon objects
# You can access them and perform further operations
if shapely_polygons_re:
    print(f"Found {len(shapely_polygons_re)} polygons in the GeoPackage.")
    print(f"First polygon's area: {shapely_polygons_re[0].area}")
else:
    print("No polygons found in the GeoPackage or the specified layer.")
    
exterior_vertices = shapely.points(shapely_polygons_re.exterior.coords)

shapely.get_num_points(shapely_polygons_re[0].boundary)

print("\nInterior Rings Vertices:")
for i, interior_ring in enumerate(shapely_polygons_re[0].interiors):
    print(f"  Hole {i+1}:")
    print(f"    {list(interior_ring.coords)}")
    
import numpy
def geoToPrint3DCoordinates(shapelyPolygon, scale, geoXMin, geoYMin):
    
    def transform(x: numpy.ndarray):
        return (x - [geoXMin, geoYMin]) / scale
    
    import shapely
    shapely.transform(shapelyPolygon, transformation=transform)
    
geoToPrint3DCoordinates(shapely_polygons_re, 1000, 1000, 1000) 