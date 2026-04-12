import shapely
from shapely.plotting import plot_polygon, plot_line, plot_points
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.typing as mt

from touchterrain.common.BorderEdge import BorderEdge

def plot_shapely_poly_or_line(geom: shapely.Geometry, ax):
    if geom.geom_type.startswith('Polygon'):
        plot_polygon(geom, ax=ax, add_points=False, color='red', linestyle=':')
    elif geom.geom_type.startswith('Line'):
        plot_line(geom, ax=ax, add_points=True, color='yellow', linestyle='--')
    else:
        plot_points(geom, ax=ax, color='brown')
        
def plot_shapely_geom(geom: shapely.Geometry, ax, color: mt.ColorType = 'red', linestyle: str = '-', **kwargs):
    if geom.geom_type.startswith('Polygon'):
        plot_polygon(geom, ax=ax, add_points=False, color=color, linestyle=linestyle, **kwargs)
    elif geom.geom_type.startswith('Line'):
        plot_line(geom, ax=ax, add_points=True, color=color, linestyle=linestyle, **kwargs)
    else:
        plot_points(geom, ax=ax, color='brown')
        
def plot_intersection_of_shapely_polygons(polys: list[shapely.Polygon]):
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
            plot_shapely_poly_or_line(sub_geom, axs)
    else:
        print(polyEnd)
        plot_shapely_poly_or_line(polyEnd, axs)
        
    plt.show()
    
def plot_shapely_geometries_colormap(basePolys: list[shapely.Polygon] = [], intersectionPolys: list[list[shapely.Geometry]] = [], edgeBuckets: list[list[BorderEdge]] = []):
    "Plot N polygons and lines in a different color each time."
    
    fig, axs = plt.subplots()
    axs.set_aspect('equal', 'datalim')
    
    # Choose a colormap (e.g., 'viridis', 'plasma', 'tab10')
    cmap = cm.get_cmap('gist_rainbow', len(basePolys)+len(intersectionPolys)+len(edgeBuckets))
    
    # -- dashed for base poly
    for i in range(0,len(basePolys)):
        plot_polygon(basePolys[i], ax=axs, add_points=False, color=cmap(i), linestyle='--', linewidth=2, alpha=0.5)

    # -. dash dot for intersections
    for i in range(0,len(intersectionPolys)):
        for ip in intersectionPolys[i]:
            if ip.geom_type.startswith('Multi') or ip.geom_type.startswith('GeometryCollection'):
                for sub_geom in ip.geoms:
                    plot_shapely_geom(sub_geom, ax=axs, color=cmap(len(intersectionPolys)+i), linestyle='-.')
            else:
                plot_shapely_geom(ip, ax=axs, color=cmap(len(intersectionPolys)+i), linestyle='-.')
            
    # solid or dot for wall/no wall edges
    for i in range(0, len(edgeBuckets)):
        for be in edgeBuckets[i]:
            plot_shapely_geom(be.geometry, ax=axs, color=cmap(len(basePolys)+len(intersectionPolys)+i), linestyle='-' if be.make_wall else ':', linewidth=(3 if be.make_wall else 1), alpha=(0.8 if be.make_wall else .8))
        
    plt.show()