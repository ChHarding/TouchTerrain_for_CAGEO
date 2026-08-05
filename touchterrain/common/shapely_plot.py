import shapely
from shapely.plotting import plot_polygon, plot_line, plot_points
from matplotlib import colormaps
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import matplotlib.typing as mt

from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.wall_visualization import BorderEdgePlotRecord

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
    
def _border_edge_plot_record(
    border_edge: BorderEdge | BorderEdgePlotRecord,
) -> BorderEdgePlotRecord:
    if isinstance(border_edge, BorderEdgePlotRecord):
        return border_edge
    return BorderEdgePlotRecord(edge=border_edge)


def border_edge_plot_style(
    border_edge: BorderEdge | BorderEdgePlotRecord,
) -> dict[str, float | str]:
    """Return line style for a visualized clipping border edge."""
    plot_record = _border_edge_plot_record(border_edge)

    # Clipped wall graph line styles:
    # - Stored clipped edge with make_wall=True: solid 6 pt. This is a real
    #   emitted wall owned by a partial clipped cell.
    # - Stored clipped edge with make_wall=False: dotted 3 pt. This is a
    #   non-wall ownership edge, drawn last and narrower so earlier feature
    #   lines remain visible when records overlap.
    # - Synthesized contained-cell cardinal wall: dash-dot 4 pt. This is a
    #   visual-only full-cell side added for a contained cell that stores no
    #   edge buckets but still emits a wall against outside or out-of-range
    #   raster cells.
    if plot_record.source == "contained_cardinal_wall":
        return {
            "linestyle": "-.",
            "linewidth": 4,
            "alpha": 0.8,
        }

    return {
        "linestyle": "-" if plot_record.edge.make_wall else ":",
        "linewidth": 6 if plot_record.edge.make_wall else 3,
        "alpha": 0.8,
    }


def border_edges_for_plot(
    edgeBuckets: list[list[BorderEdge | BorderEdgePlotRecord]],
) -> list[tuple[int, BorderEdgePlotRecord]]:
    """Return visualized edges with non-wall ownership edges drawn last."""
    border_edges = [
        (group_index, _border_edge_plot_record(border_edge))
        for group_index, edge_group in enumerate(edgeBuckets)
        for border_edge in edge_group
    ]
    border_edges.sort(key=lambda item: not item[1].edge.make_wall)
    return border_edges


def _line_type_legend_handles(
    base_polys: list[shapely.Polygon],
    intersection_polys: list[list[shapely.Geometry]],
    ordered_border_edges: list[tuple[int, BorderEdgePlotRecord]],
) -> list[Line2D]:
    """Return neutral-color legend handles for visible line categories."""
    handles: list[Line2D] = []
    if base_polys:
        handles.append(
            Line2D(
                [0],
                [0],
                color="black",
                linestyle="--",
                linewidth=2,
                alpha=0.5,
                label="Base polygon / cell boundary",
            )
        )
    if any(intersection_group for intersection_group in intersection_polys):
        handles.append(
            Line2D(
                [0],
                [0],
                color="black",
                linestyle="-.",
                label="Clipped intersection geometry",
            )
        )

    records_by_category: dict[str, BorderEdgePlotRecord] = {}
    for _group_index, plot_record in ordered_border_edges:
        if plot_record.source == "contained_cardinal_wall":
            category = "contained_wall"
        elif plot_record.edge.make_wall:
            category = "stored_wall"
        else:
            category = "non_wall"
        records_by_category.setdefault(category, plot_record)

    category_labels = (
        ("stored_wall", "Wall from partially clipped cell"),
        ("contained_wall", "Wall from fully contained cell"),
        ("non_wall", "Ownership edge (no wall)"),
    )
    for category, label in category_labels:
        plot_record = records_by_category.get(category)
        if plot_record is None:
            continue
        handles.append(
            Line2D(
                [0],
                [0],
                color="black",
                label=label,
                **border_edge_plot_style(plot_record),
            )
        )
    return handles


def plot_shapely_geometries_colormap(
    basePolys: list[shapely.Polygon] | None = None,
    intersectionPolys: list[list[shapely.Geometry]] | None = None,
    edgeBuckets: list[list[BorderEdge | BorderEdgePlotRecord]] | None = None,
    show: bool = True,
):
    "Plot N polygons and lines in a different color each time."
    basePolys = [] if basePolys is None else basePolys
    intersectionPolys = [] if intersectionPolys is None else intersectionPolys
    edgeBuckets = [] if edgeBuckets is None else edgeBuckets
    
    fig, axs = plt.subplots()
    axs.set_aspect('equal', 'datalim')
    
    # Choose a colormap (e.g., 'viridis', 'plasma', 'tab10')
    cmap = colormaps.get_cmap('gist_rainbow').resampled(
        max(1, len(basePolys) + len(intersectionPolys) + len(edgeBuckets))
    )
    
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
            
    # Draw wall edges first, then non-wall ownership edges, so dotted
    # ownership records remain inspectable when duplicate edges overlap.
    ordered_border_edges = border_edges_for_plot(edgeBuckets)
    for i, plot_record in ordered_border_edges:
        plot_shapely_geom(
            plot_record.edge.geometry,
            ax=axs,
            color=cmap(len(basePolys) + len(intersectionPolys) + i),
            **border_edge_plot_style(plot_record),
        )

    legend_handles = _line_type_legend_handles(
        basePolys,
        intersectionPolys,
        ordered_border_edges,
    )
    if legend_handles:
        axs.legend(handles=legend_handles, title="Line types")
        
    if show:
        plt.show()
    return fig, axs
