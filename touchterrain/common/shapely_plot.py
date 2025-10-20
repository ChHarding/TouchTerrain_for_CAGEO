import shapely
from shapely.plotting import plot_polygon, plot_line, plot_points
import matplotlib.pyplot as plt

def plot_shapely_geom(geom: shapely.Geometry, axs):
    if geom.geom_type.startswith('Polygon'):
        plot_polygon(geom, ax=axs, add_points=False, color='red', linestyle=':')
    elif geom.geom_type.startswith('Line'):
        plot_line(geom, ax=axs, add_points=True, color='yellow', linestyle='--')
    else:
        plot_points(geom, ax=axs, color='brown')
        
def plot_shapely_polygon_intersection(polys: list[shapely.Polygon]):
    "Plot 2 polygons and their intersection geometries."
    
    fig, axs = plt.subplots()
    axs.set_aspect('equal', 'datalim')
    
    for geom in polys:
        plot_polygon(geom, ax=axs, add_points=False, color='blue', linestyle='-.')

    polyEnd = polys[0].intersection(polys[1])
    if polyEnd.geom_type.startswith('Multi') or polyEnd.geom_type.startswith('GeometryCollection'):
        print(polyEnd)
        for sub_geom in polyEnd.geoms:
            print(sub_geom)
            plot_shapely_geom(sub_geom, axs)
    else:
        print(polyEnd)
        plot_shapely_geom(polyEnd, axs)
        
    plt.show()