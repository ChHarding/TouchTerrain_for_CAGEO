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


from shapely.geometry import Polygon, LineString
from shapely.ops import split, unary_union
#poly1 contains poly2
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 contains part of poly2
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, 1), (3, 1), (3, 3), (1, 3), (-1, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 intersections poly2 to create 2 connected vertices
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, -1), (-1, 6), (0, 6), (0, -1), (-1, -1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))
print(poly2.intersection(poly1))
poly2_coords = [(5, -1), (5, 6), (6, 6), (6, -1), (-5, -1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))
print(poly2.intersection(poly1))

#poly1 intersections poly2 to create 2 closed, disconnected polygons
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, 1), (-1, 6), (5, 6), (-0.5, 3), (5, -1), (-1, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 intersections poly2 to create 2 closed polygons sharing a single vertex
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, 1), (-1, 6), (5, 6), (0, 3), (5, -1), (-1, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 intersections poly2 to create 2 closed polygons sharing 2 connected vertices
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, 1), (-1, 6), (5, 6),(0, 4), (0, 3), (5, -1), (-1, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 intersections poly2 to create 2 closed polygons sharing 4 connected vertices, 2 of those vertices are in a line segment
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(0, 1), (0, 6), (5, 6),(0, 4), (0, 3), (5, -1), (0, 1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 is contained by poly2 sharing 2 connected vertices
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, -1), (-1, 6), (6, 6),(5, 5), (6, 4), (5, 3), (6, -1), (-1,-1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#poly1 is contained by poly2 sharing 2 connected vertices
poly1_coords = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
poly1 = Polygon(poly1_coords)
poly2_coords = [(-1, -1), (-1, 6), (6, 6),(5, 5), (6, 4), (4, 3), (6, -1), (-1,-1)]
poly2 = Polygon(poly2_coords)
print(poly1.intersection(poly2))

#line1 is same as line2
line1_coords= [(0,0), (5,0)]
line1 = LineString(line1_coords)
line2_coords= [(0,0), (5,0)]
line2 = LineString(line2_coords)
line2rev_coords= [(5,0), (0,0)]
line2rev = LineString(line2rev_coords)
line2.contains(line1) #true
line2rev.contains(line1) #true
line2.contains_properly(line1) #false
line1.overlaps(line2) #false
line2.overlaps(line1) #false
line2rev.overlaps(line1) #false
line1.equals(line2) #true
line1.equals(line2rev) #true
line1.equals_exact(line2) #true
line1.equals_exact(line2rev) #false

line1_coords= [(0,0,1), (5,0,2)]
line2rev_coords= [(5,0,0), (0,0,-1)]


#line1 is contained by line2 but not contains_properly
line1_coords= [(0,0), (5,0)]
line1 = LineString(line1_coords)
line2_coords= [(0,0), (10,0)]
line2 = LineString(line2_coords)
line2.contains(line1) #true
line2.contains_properly(line1) #false
line1.overlaps(line2) #false
line2.overlaps(line1) #false

# get split sub edges
merged_lines = unary_union([line1, line2])
for segment in merged_lines.geoms:
    print(segment)
# result = split(line2, line1)
# result = split(line1, line2)
# for segment in result.geoms:
#     print(segment)

#line1 is contains_properly by line2
line1_coords= [(1,0), (5,0)]
line1 = LineString(line1_coords)
line2_coords= [(0,0), (10,0)]
line2 = LineString(line2_coords)
line2.contains(line1) #true
line2.contains_properly(line1) #true
line2.overlaps(line1) #false

#line1 and line2 share 1 point
line1_coords= [(1,0), (5,0)]
line1 = LineString(line1_coords)
line2_coords= [(5,0), (10,0)]
line2 = LineString(line2_coords)
line2.contains(line1) #false
line2.contains_properly(line1) #false
line2.overlaps(line1) #false

#line1 and line2 each overlap some of each other but not all
line1_coords= [(1,0), (6,0)]
line1 = LineString(line1_coords)
line2_coords= [(5,0), (10,0)]
line2 = LineString(line2_coords)
line2.contains(line1) #false
line2.contains_properly(line1) #false
line1.overlaps(line2) #true
line2.overlaps(line1) #true


from shapely.plotting import plot_polygon, plot_line, plot_points
import shapely.geometry as sg
import shapely.ops as so
import matplotlib.pyplot as plt

def plot_geom(geom, axs):
    if geom.geom_type.startswith('Polygon'):
        plot_polygon(geom, ax=axs, add_points=False, color='red', linestyle=':')
    elif geom.geom_type.startswith('Line'):
        plot_line(geom, ax=axs, add_points=True, color='yellow', linestyle='--')
    else:
        plot_points(geom, ax=axs, color='brown')


polyStart = [poly1, poly2]
fig, axs = plt.subplots()
axs.set_aspect('equal', 'datalim')

for geom in polyStart:
    plot_polygon(geom, ax=axs, add_points=False, color='blue', linestyle='-.')

polyEnd = poly2.intersection(poly1)
if polyEnd.geom_type.startswith('Multi') or polyEnd.geom_type.startswith('GeometryCollection'):
    print(polyEnd)
    for sub_geom in polyEnd.geoms:
        print(sub_geom)
        plot_geom(sub_geom, axs)
else:
    print(polyEnd)
    plot_geom(polyEnd, axs)

plt.show()


