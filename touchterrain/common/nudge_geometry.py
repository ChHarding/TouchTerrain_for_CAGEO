# nudge_geometry.py
# footprint and midpoint geometry shared by Z=0 and positive-Z nudging

"""Cell footprint geometry used by both nudge modes.

A nudge cuts affected corners off a cell footprint and inserts midpoints on the
sides it crosses. That footprint arithmetic is identical for the Z=0 and
positive-Z cases -- only the ownership and the inserted Z values differ -- so it
lives here and both modes call it.

See ``spec/shared_z0_edge_corner_nudge.md`` for the keep-footprint definitions
and ``spec/positive_z_overused_edge_nudge.md`` for the role swap that reuses
them.
"""

from collections.abc import Sequence

import shapely

from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.mesh_vocabulary import (
    CARDINAL_DIRECTIONS,
    NUDGE_MIDPOINT_CORNERS_BY_NAME,
    NUDGE_SIDE_ENDPOINT_NAMES,
    NUDGE_SIDE_MIDPOINT_NAME,
    NUDGE_SIDE_SEGMENT_NAMES,
    XYEdge,
)
from touchterrain.common.mesh_serialization import (
    normalize_coordinate_to_match_mesh_serialization,
    normalize_vertex_to_match_mesh_serialization,
    surface_polygon_normalized_to_match_mesh_serialization,
)
from touchterrain.common.surface_geometry import (
    _geometry_boundary_linework,
    _iter_polygon_parts,
    _linework_covers_footprint,
    _rebuild_matching_surface_polygon_borders,
    _surface_wall_requested_lines,
)


def cell_corner_points(
    W: float,
    E: float,
    N: float,
    S: float,
) -> dict[str, tuple[float, float]]:
    mid_x = (W + E) / 2
    mid_y = (N + S) / 2
    return {
        "SW": (W, S),
        "SE": (E, S),
        "NE": (E, N),
        "NW": (W, N),
        "Smid": (mid_x, S),
        "Emid": (E, mid_y),
        "Nmid": (mid_x, N),
        "Wmid": (W, mid_y),
    }


def cell_bounds_for_location(
    cell_j: int,
    cell_i: int,
    cell_size: float,
    offsetx: float,
    offsety: float,
) -> tuple[float, float, float, float]:
    """Return W, E, N, S bounds for a padded raster cell location."""
    cell_w = (cell_i - 1) * cell_size - offsetx
    cell_e = cell_w + cell_size
    cell_n = -((cell_j - 1) * cell_size) + offsety
    cell_s = cell_n - cell_size
    return cell_w, cell_e, cell_n, cell_s


def cell_side_values(
    cell_j: int,
    cell_i: int,
    cell_size: float,
    offsetx: float,
    offsety: float,
    output_fileformat: str,
) -> dict[str, float]:
    """Return serialized side coordinates for a padded raster cell."""
    cell_w, cell_e, cell_n, cell_s = cell_bounds_for_location(
        cell_j,
        cell_i,
        cell_size,
        offsetx,
        offsety,
    )
    return side_values_from_bounds(
        cell_w,
        cell_e,
        cell_n,
        cell_s,
        output_fileformat,
    )


def side_values_from_bounds(
    W: float,
    E: float,
    N: float,
    S: float,
    output_fileformat: str,
) -> dict[str, float]:
    """Return serialized side coordinates from W/E/N/S bounds."""
    return {
        "N": normalize_coordinate_to_match_mesh_serialization(
            N,
            output_fileformat,
        ),
        "S": normalize_coordinate_to_match_mesh_serialization(
            S,
            output_fileformat,
        ),
        "E": normalize_coordinate_to_match_mesh_serialization(
            E,
            output_fileformat,
        ),
        "W": normalize_coordinate_to_match_mesh_serialization(
            W,
            output_fileformat,
        ),
    }


def edge_cardinal_side(
    footprint: XYEdge,
    side_values: dict[str, float],
) -> str | None:
    """Return the cardinal side occupied by a serialized XY edge."""
    (x0, y0), (x1, y1) = footprint
    if y0 == side_values["N"] and y1 == side_values["N"]:
        return "N"
    if y0 == side_values["S"] and y1 == side_values["S"]:
        return "S"
    if x0 == side_values["E"] and x1 == side_values["E"]:
        return "E"
    if x0 == side_values["W"] and x1 == side_values["W"]:
        return "W"
    return None


def full_cell_footprint(
    W: float,
    E: float,
    N: float,
    S: float,
) -> shapely.Polygon:
    points = cell_corner_points(W, E, N, S)
    return shapely.Polygon(
        [
            points["SW"],
            points["SE"],
            points["NE"],
            points["NW"],
            points["SW"],
        ]
    )


def nudge_keep_footprint(
    affected_corners: Sequence[IntermediateCorner],
    W: float,
    E: float,
    N: float,
    S: float,
) -> shapely.Polygon | None:
    """Return the shared nudge keep footprint for an affected-corner set."""
    vertex_names = _nudge_keep_vertex_names(affected_corners)
    if vertex_names is None:
        return None
    points = cell_corner_points(W, E, N, S)
    return shapely.Polygon([points[name] for name in vertex_names])


def _nudge_keep_vertex_names(
    affected_corners: Sequence[IntermediateCorner],
) -> list[str] | None:
    """Return vertex names for the shared nudge keep footprint."""
    affected = frozenset(affected_corners)
    c = IntermediateCorner
    footprints = {
        frozenset([c.SW]): ["Smid", "SE", "NE", "NW", "Wmid"],
        frozenset([c.SE]): ["SW", "Smid", "Emid", "NE", "NW"],
        frozenset([c.NE]): ["SW", "SE", "Emid", "Nmid", "NW"],
        frozenset([c.NW]): ["SW", "SE", "NE", "Nmid", "Wmid"],
        frozenset([c.SW, c.SE]): ["Wmid", "Emid", "NE", "NW"],
        frozenset([c.SE, c.NE]): ["SW", "Smid", "Nmid", "NW"],
        frozenset([c.NW, c.NE]): ["SW", "SE", "Emid", "Wmid"],
        frozenset([c.SW, c.NW]): ["Smid", "SE", "NE", "Nmid"],
        frozenset([c.SW, c.NE]): [
            "Smid",
            "SE",
            "Emid",
            "Nmid",
            "NW",
            "Wmid",
        ],
        frozenset([c.SE, c.NW]): [
            "SW",
            "Smid",
            "Emid",
            "NE",
            "Nmid",
            "Wmid",
        ],
        frozenset([c.SW, c.NW, c.NE]): ["Smid", "SE", "Emid"],
        frozenset([c.NW, c.SW, c.SE]): ["Nmid", "Emid", "NE"],
        frozenset([c.SW, c.SE, c.NE]): ["Wmid", "Nmid", "NW"],
        frozenset([c.SE, c.NE, c.NW]): ["SW", "Smid", "Wmid"],
    }
    return footprints.get(affected)


def _nudge_keep_footprint_splits_side(
    affected_corners: Sequence[IntermediateCorner],
    side: str,
) -> bool:
    """Return whether a nudge keep footprint inserts a midpoint on a side."""
    vertex_names = _nudge_keep_vertex_names(affected_corners)
    return (
        vertex_names is not None
        and NUDGE_SIDE_MIDPOINT_NAME[side] in vertex_names
    )


def _nudge_keep_footprint_split_sides(
    affected_corners: Sequence[IntermediateCorner],
) -> set[str]:
    """Return sides split by the nudge keep footprint."""
    return {
        side
        for side in CARDINAL_DIRECTIONS
        if _nudge_keep_footprint_splits_side(affected_corners, side)
    }


def _nudge_split_side_endpoint_xy(
    split_sides: set[str],
    W: float,
    E: float,
    N: float,
    S: float,
    output_fileformat: str,
) -> set[tuple[float, float]]:
    """Return serialized XY endpoints for split-only side preservation."""
    points = cell_corner_points(W, E, N, S)
    endpoints: set[tuple[float, float]] = set()
    for side in split_sides:
        for point_name in NUDGE_SIDE_ENDPOINT_NAMES[side]:
            endpoints.add(
                normalize_vertex_to_match_mesh_serialization(
                    (*points[point_name], 0.0),
                    output_fileformat,
                )[:2]
            )
    return endpoints


def _nudge_split_side_endpoint_edges(
    split_sides: set[str],
    W: float,
    E: float,
    N: float,
    S: float,
    output_fileformat: str,
) -> set[XYEdge]:
    """Return serialized XY half-edges for split-only side preservation."""
    points = cell_corner_points(W, E, N, S)
    edges: set[XYEdge] = set()
    for side in split_sides:
        for start_name, end_name in NUDGE_SIDE_SEGMENT_NAMES[side]:
            start_xy = normalize_vertex_to_match_mesh_serialization(
                (*points[start_name], 0.0),
                output_fileformat,
            )[:2]
            end_xy = normalize_vertex_to_match_mesh_serialization(
                (*points[end_name], 0.0),
                output_fileformat,
            )[:2]
            edges.add(tuple(sorted((start_xy, end_xy))))
    return edges


def _nudge_adjusted_keep_surface_planes(
    affected_corners: Sequence[IntermediateCorner],
    corner_vertices: dict[IntermediateCorner, vertex],
    W: float,
    E: float,
    N: float,
    S: float,
    forced_midpoint_z: float | None = None,
    midpoint_corner_vertices: dict[IntermediateCorner, vertex] | None = None,
) -> list[shapely.Polygon]:
    """Return full-precision nudge-adjusted keep-footprint triangles."""
    vertex_names = _nudge_keep_vertex_names(affected_corners)
    if vertex_names is None:
        return []

    footprint_2d = shapely.Polygon(
        [cell_corner_points(W, E, N, S)[name] for name in vertex_names]
    )
    return _nudge_adjusted_surface_planes(
        footprint_2d,
        corner_vertices,
        W,
        E,
        N,
        S,
        forced_midpoint_z=forced_midpoint_z,
        midpoint_corner_vertices=midpoint_corner_vertices,
    )


def _nudge_adjusted_surface_planes(
    geometry: shapely.Geometry,
    corner_vertices: dict[IntermediateCorner, vertex | None],
    W: float,
    E: float,
    N: float,
    S: float,
    forced_midpoint_z: float | None = None,
    midpoint_corner_vertices: dict[IntermediateCorner, vertex] | None = None,
) -> list[shapely.Polygon]:
    """Return nudge surface planes with optional alternate midpoint Z."""
    points = cell_corner_points(W, E, N, S)
    name_by_point = {point: name for name, point in points.items()}
    corner_by_name = {
        "NW": IntermediateCorner.NW,
        "NE": IntermediateCorner.NE,
        "SW": IntermediateCorner.SW,
        "SE": IntermediateCorner.SE,
    }
    midpoint_source = midpoint_corner_vertices or corner_vertices

    def z_for_name(name: str) -> float | None:
        if name in corner_by_name:
            corner_vertex = corner_vertices.get(corner_by_name[name])
            return None if corner_vertex is None else corner_vertex.coords[2]
        if name in NUDGE_MIDPOINT_CORNERS_BY_NAME:
            if forced_midpoint_z is not None:
                return forced_midpoint_z
            midpoint_vertices = [
                midpoint_source.get(corner)
                for corner in NUDGE_MIDPOINT_CORNERS_BY_NAME[name]
            ]
            if any(corner_vertex is None for corner_vertex in midpoint_vertices):
                return None
            return (
                midpoint_vertices[0].coords[2]
                + midpoint_vertices[1].coords[2]
            ) / 2
        return None

    planes: list[shapely.Polygon] = []
    for polygon in _iter_polygon_parts(geometry):
        triangles = shapely.constrained_delaunay_triangles(polygon)
        for triangle in _iter_polygon_parts(triangles):
            coords_3d = []
            coords = triangle.exterior.coords
            for index in range(len(coords) - 1):
                x, y = coords[index]
                point_name = name_by_point.get((x, y))
                if point_name is None:
                    raise ValueError(
                        "Nudge adjusted plane includes an unexpected vertex."
                    )
                z = z_for_name(point_name)
                if z is None:
                    return []
                coords_3d.append((x, y, z))
            coords_3d.append(coords_3d[0])
            planes.append(shapely.Polygon(coords_3d))
    return planes


def _nudge_midpoint_z_by_xy(
    W: float,
    E: float,
    N: float,
    S: float,
    midpoint_corner_vertices: dict[IntermediateCorner, vertex] | None,
    output_fileformat: str,
    midpoint_z_by_name: dict[str, float] | None = None,
) -> dict[tuple[float, float], float]:
    """Return serialized midpoint XY keys mapped to their requested Z."""
    points = cell_corner_points(W, E, N, S)
    z_by_xy: dict[tuple[float, float], float] = {}
    for midpoint_name, midpoint_corners in NUDGE_MIDPOINT_CORNERS_BY_NAME.items():
        midpoint_z = None
        if midpoint_z_by_name and midpoint_name in midpoint_z_by_name:
            midpoint_z = midpoint_z_by_name[midpoint_name]
        elif midpoint_corner_vertices is not None:
            midpoint_vertices = [
                midpoint_corner_vertices.get(corner)
                for corner in midpoint_corners
            ]
            if any(corner_vertex is None for corner_vertex in midpoint_vertices):
                continue
            midpoint_z = (
                midpoint_vertices[0].coords[2]
                + midpoint_vertices[1].coords[2]
            ) / 2
        else:
            continue
        midpoint_xy = normalize_vertex_to_match_mesh_serialization(
            (*points[midpoint_name], 0.0),
            output_fileformat,
        )[:2]
        z_by_xy[midpoint_xy] = normalize_coordinate_to_match_mesh_serialization(
            midpoint_z,
            output_fileformat,
        )

    return z_by_xy


def _surface_polygons_with_midpoint_z(
    surface_polygons: list[shapely.Polygon],
    W: float,
    E: float,
    N: float,
    S: float,
    midpoint_corner_vertices: dict[IntermediateCorner, vertex] | None,
    output_fileformat: str,
    midpoint_z_by_name: dict[str, float] | None = None,
) -> list[shapely.Polygon]:
    """Return surfaces with nudge midpoint vertices set from a source surface."""
    z_by_xy = _nudge_midpoint_z_by_xy(
        W,
        E,
        N,
        S,
        midpoint_corner_vertices,
        output_fileformat,
        midpoint_z_by_name,
    )
    if not z_by_xy:
        return surface_polygons

    return _surface_polygons_with_z_overrides(
        surface_polygons,
        z_by_xy,
        output_fileformat,
    )


def _surface_polygons_with_z_overrides(
    surface_polygons: list[shapely.Polygon],
    z_by_xy: dict[tuple[float, float], float],
    output_fileformat: str,
) -> list[shapely.Polygon]:
    """Return surfaces with vertices at matching serialized XY set to Z."""
    if not z_by_xy:
        return surface_polygons

    def adjusted_ring(ring: shapely.LinearRing) -> list[tuple[float, ...]]:
        coords = []
        for coord in ring.coords:
            normalized_xy = normalize_vertex_to_match_mesh_serialization(
                coord,
                output_fileformat,
            )[:2]
            coords.append(
                (coord[0], coord[1], z_by_xy.get(normalized_xy, coord[2]))
            )
        return coords

    adjusted_polygons = []
    for surface_polygon in surface_polygons:
        interiors = [
            adjusted_ring(interior)
            for interior in surface_polygon.interiors
        ]
        adjusted_polygon = shapely.Polygon(
            adjusted_ring(surface_polygon.exterior),
            interiors,
        )
        normalized_polygon = (
            surface_polygon_normalized_to_match_mesh_serialization(
                adjusted_polygon,
                output_fileformat,
            )
        )
        if normalized_polygon is not None:
            adjusted_polygons.append(normalized_polygon)
    return adjusted_polygons


def _surface_vertex_z_overrides_by_xy(
    surface_polygons: list[shapely.Polygon] | None,
    output_fileformat: str,
) -> dict[tuple[float, float], float]:
    """Return serialized Z values for vertices already on a surface."""
    z_by_xy: dict[tuple[float, float], float] = {}
    for surface_polygon in surface_polygons or []:
        for coord in surface_polygon.exterior.coords[:-1]:
            normalized = normalize_vertex_to_match_mesh_serialization(
                coord,
                output_fileformat,
            )
            z_by_xy.setdefault(normalized[:2], normalized[2])
    return z_by_xy


def _z0_adjusted_keep_surface_planes(
    affected_corners: Sequence[IntermediateCorner],
    corner_vertices: dict[IntermediateCorner, vertex],
    W: float,
    E: float,
    N: float,
    S: float,
) -> list[shapely.Polygon]:
    """Return full-precision nudge-adjusted triangles with Z0 midpoints."""
    return _nudge_adjusted_keep_surface_planes(
        affected_corners,
        corner_vertices,
        W,
        E,
        N,
        S,
        forced_midpoint_z=0.0,
    )


def quad_corner_vertices_by_xy(
    surface_quad: quad,
    W: float,
    E: float,
    N: float,
    S: float,
) -> dict[IntermediateCorner, vertex | None]:
    """Return cell corner vertices by XY, independent of quad vertex order."""
    corner_xy = {
        IntermediateCorner.NW: (W, N),
        IntermediateCorner.NE: (E, N),
        IntermediateCorner.SW: (W, S),
        IntermediateCorner.SE: (E, S),
    }
    corner_vertices: dict[IntermediateCorner, vertex | None] = {
        corner: None for corner in IntermediateCorner
    }
    for quad_vertex in surface_quad.vl:
        if quad_vertex is None:
            continue
        for corner, xy in corner_xy.items():
            if (
                abs(quad_vertex.coords[0] - xy[0]) <= 1e-9
                and abs(quad_vertex.coords[1] - xy[1]) <= 1e-9
            ):
                corner_vertices[corner] = quad_vertex
                break
    return corner_vertices


def rebuild_nudged_surface_polygon_borders(
    top_surfaces: list[shapely.Polygon],
    bottom_surfaces: list[shapely.Polygon],
    borders: dict[str, quad],
    previous_surface_polygon_borders: list[quad] | None,
    full_footprint: shapely.Geometry,
    include_normal_cut_edges: bool,
    W: float,
    E: float,
    N: float,
    S: float,
    output_fileformat: str,
    side_cut_wall_sides: set[str] | None = None,
) -> list[quad]:
    """Build current-cell walls requested by existing borders after nudging."""
    requested_clipped_lines = _surface_wall_requested_lines(
        previous_surface_polygon_borders,
        output_fileformat=output_fileformat,
    )
    footprint_boundary = _geometry_boundary_linework(
        full_footprint,
        output_fileformat,
    )

    side_values = side_values_from_bounds(
        W,
        E,
        N,
        S,
        output_fileformat,
    )

    def footprint_is_requested(footprint: XYEdge) -> bool:
        line = shapely.LineString(footprint)
        side = edge_cardinal_side(footprint, side_values)
        on_footprint_boundary = _linework_covers_footprint(
            footprint_boundary,
            footprint,
        )
        if side is not None and side in borders:
            return True
        if (
            requested_clipped_lines is not None
            and requested_clipped_lines.covers(line)
        ):
            return True
        if side is None and on_footprint_boundary:
            return True
        if (
            include_normal_cut_edges
            and side is None
            and not on_footprint_boundary
        ):
            return True
        if (
            side_cut_wall_sides is not None
            and side in side_cut_wall_sides
        ):
            return True
        return False

    return _rebuild_matching_surface_polygon_borders(
        top_surfaces,
        bottom_surfaces,
        footprint_is_requested,
        output_fileformat,
    )
