# nudge_cell_ops.py
# rewrite one cell's surfaces to repair a nudged contact

"""Per-cell nudge operations.

Each function here takes one already-built cell and rewrites its top and bottom
surfaces plus the walls that close them. They are the geometry half of nudging;
deciding *which* cells to repair is ``nudge_plan``, and driving them over a grid
is ``nudge_apply``.

The normal and difference meshes swap roles between the two nudge modes. For a
positive-Z contact the normal mesh keeps full footprint coverage and the
difference mesh gives up the contact area; see
``spec/positive_z_overused_edge_nudge.md``.

These take the cell as an ordinary argument rather than living on ``cell``
itself, so the cell class stays below nudging in the import order and the nudge
plan can build a throwaway cell without a cycle.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

import shapely

from touchterrain.common.Vertex import vertex
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.mesh_vocabulary import (
    Edge3D,
    SerializedVertexCache,
    XYEdge,
    _empty_borders,
)
from touchterrain.common.mesh_serialization import (
    boundary_edge_map_from_meshes,
    edge_3d_signature,
    edge_xy_signature,
    normalize_vertex_to_match_mesh_serialization,
    surface_mesh_edge_counts,
    surface_polygon_normalized_to_match_mesh_serialization,
)
from touchterrain.common.surface_geometry import (
    _clip_3d_surface_polygons_to_2d_geometry,
    _current_surface_footprint,
    _geometry_boundary_linework,
    _polygonized_regions_with_shared_boundaries,
    _rebuild_matching_surface_polygon_borders,
    _split_surface_boundary_edges_for_wall_matches,
    _surface_planes_from_current_geometry,
    _triangulate_2d_geometry_to_3d_polygons,
)
from touchterrain.common.nudge_geometry import (
    _nudge_adjusted_surface_planes,
    _nudge_midpoint_z_by_xy,
    _surface_polygons_with_midpoint_z,
    _surface_polygons_with_z_overrides,
    _surface_vertex_z_overrides_by_xy,
    cell_corner_points,
    full_cell_footprint,
    nudge_keep_footprint,
    quad_corner_vertices_by_xy,
    rebuild_nudged_surface_polygon_borders,
)

if TYPE_CHECKING:
    from touchterrain.common.Cell import cell


def split_surface_boundary_midpoints(
    target: "cell",
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
    """Split a cell surface at requested side midpoints."""
    if not split_sides:
        return False

    full_footprint = full_cell_footprint(W, E, N, S)
    current_footprint = _current_surface_footprint(
        target.topSurfacePolygons,
        full_footprint,
        target.topquad,
    )
    if current_footprint.is_empty:
        return False
    bottom_footprint = _current_surface_footprint(
        target.bottomSurfacePolygons,
        full_footprint,
        target.bottomquad,
    )
    if (
        not target.bottomSurfacePolygons
        and bottom_footprint.equals(full_footprint)
        and not current_footprint.equals(full_footprint)
    ):
        bottom_footprint = current_footprint
    if bottom_footprint.is_empty:
        return False
    use_top_footprint_for_bottom = (
        bottom_midpoint_corner_vertices is None
        and bottom_midpoint_z_by_name is None
    )
    if use_top_footprint_for_bottom:
        bottom_footprint = current_footprint

    top_planes = _surface_planes_from_current_geometry(
        target.topquad,
        target.topSurfacePolygons,
        split_rotation,
    )
    bottom_planes = _surface_planes_from_current_geometry(
        target.bottomquad,
        target.bottomSurfacePolygons,
        split_rotation,
    )
    if not top_planes or not bottom_planes:
        return False
    top_existing_z_by_xy = _surface_vertex_z_overrides_by_xy(
        target.topSurfacePolygons,
        output_fileformat,
    )
    bottom_existing_z_by_xy = _surface_vertex_z_overrides_by_xy(
        target.bottomSurfacePolygons,
        output_fileformat,
    )

    points = cell_corner_points(W, E, N, S)
    midpoint_name_by_side = {
        "N": "Nmid",
        "S": "Smid",
        "E": "Emid",
        "W": "Wmid",
    }
    boundary_linework = _geometry_boundary_linework(
        current_footprint,
        output_fileformat,
    )
    bottom_boundary_linework = _geometry_boundary_linework(
        bottom_footprint,
        output_fileformat,
    )
    requested_split_xy: set[tuple[float, float]] = set()
    for side in split_sides:
        midpoint_name = midpoint_name_by_side[side]
        midpoint_xy = normalize_vertex_to_match_mesh_serialization(
            (*points[midpoint_name], 0.0),
            output_fileformat,
        )[:2]
        midpoint = shapely.Point(midpoint_xy)
        if (
            boundary_linework is not None
            and boundary_linework.covers(midpoint)
        ) or (
            bottom_boundary_linework is not None
            and bottom_boundary_linework.covers(midpoint)
        ):
            requested_split_xy.add(midpoint_xy)
    if not requested_split_xy:
        return False

    vertex_names = ["SW"]
    if "S" in split_sides:
        vertex_names.append("Smid")
    vertex_names.append("SE")
    if "E" in split_sides:
        vertex_names.append("Emid")
    vertex_names.append("NE")
    if "N" in split_sides:
        vertex_names.append("Nmid")
    vertex_names.append("NW")
    if "W" in split_sides:
        vertex_names.append("Wmid")
    base_split_footprint = shapely.Polygon(
        [points[name] for name in vertex_names],
    )
    top_split_footprint = (
        base_split_footprint
        if current_footprint.equals(full_footprint)
        else current_footprint
    )
    bottom_split_footprint = (
        base_split_footprint
        if bottom_footprint.equals(full_footprint)
        else bottom_footprint
    )

    if (
        top_midpoint_corner_vertices is not None
        and target.topquad is not None
        and current_footprint.equals(full_footprint)
    ):
        adjusted_top_planes = _nudge_adjusted_surface_planes(
            base_split_footprint,
            quad_corner_vertices_by_xy(target.topquad, W, E, N, S),
            W,
            E,
            N,
            S,
            midpoint_corner_vertices=top_midpoint_corner_vertices,
        )
        if adjusted_top_planes:
            top_planes = adjusted_top_planes
    if (
        bottom_midpoint_corner_vertices is not None
        and target.bottomquad is not None
        and bottom_footprint.equals(full_footprint)
    ):
        adjusted_bottom_planes = _nudge_adjusted_surface_planes(
            base_split_footprint,
            quad_corner_vertices_by_xy(target.bottomquad, W, E, N, S),
            W,
            E,
            N,
            S,
            midpoint_corner_vertices=bottom_midpoint_corner_vertices,
        )
        if adjusted_bottom_planes:
            bottom_planes = adjusted_bottom_planes

    top_fallback_z_by_xy = _nudge_midpoint_z_by_xy(
        W,
        E,
        N,
        S,
        top_midpoint_corner_vertices,
        output_fileformat,
        top_midpoint_z_by_name,
    )
    top_surfaces = _triangulate_2d_geometry_to_3d_polygons(
        top_split_footprint,
        top_planes,
        exterior_cw=False,
        output_fileformat=output_fileformat,
        fallback_z_by_xy=top_fallback_z_by_xy,
    )
    if top_midpoint_corner_vertices is not None or top_midpoint_z_by_name:
        top_surfaces = _surface_polygons_with_midpoint_z(
            top_surfaces,
            W,
            E,
            N,
            S,
            top_midpoint_corner_vertices,
            output_fileformat,
            top_midpoint_z_by_name,
        )
    bottom_fallback_z_by_xy = _nudge_midpoint_z_by_xy(
        W,
        E,
        N,
        S,
        bottom_midpoint_corner_vertices,
        output_fileformat,
        bottom_midpoint_z_by_name,
    )
    if (
        target.bottomSurfacePolygons
        and not bottom_fallback_z_by_xy
        and not use_top_footprint_for_bottom
    ):
        bottom_surfaces = _clip_3d_surface_polygons_to_2d_geometry(
            target.bottomSurfacePolygons,
            bottom_split_footprint,
            exterior_cw=True,
            output_fileformat=output_fileformat,
        )
    else:
        bottom_surfaces = _triangulate_2d_geometry_to_3d_polygons(
            bottom_split_footprint,
            bottom_planes,
            exterior_cw=True,
            output_fileformat=output_fileformat,
            fallback_z_by_xy=bottom_fallback_z_by_xy,
        )
    if not top_surfaces or not bottom_surfaces:
        return False

    def footprint_has_requested_split(footprint: XYEdge) -> bool:
        line = shapely.LineString(footprint)
        return any(
            line.covers(shapely.Point(split_xy))
            for split_xy in requested_split_xy
        )

    serialized_vertices: SerializedVertexCache = {}
    top_boundary_edges = boundary_edge_map_from_meshes(
        top_surfaces,
        output_fileformat=output_fileformat,
        serialized_vertices=serialized_vertices,
    )
    bottom_boundary_edges = boundary_edge_map_from_meshes(
        bottom_surfaces,
        output_fileformat=output_fileformat,
        serialized_vertices=serialized_vertices,
    )
    top_surfaces = _split_surface_boundary_edges_for_wall_matches(
        top_surfaces,
        top_boundary_edges,
        requested_split_xy,
        footprint_has_requested_split,
        output_fileformat,
    )
    bottom_surfaces = _split_surface_boundary_edges_for_wall_matches(
        bottom_surfaces,
        bottom_boundary_edges,
        requested_split_xy,
        footprint_has_requested_split,
        output_fileformat,
    )
    top_surfaces = _surface_polygons_with_z_overrides(
        top_surfaces,
        top_existing_z_by_xy,
        output_fileformat,
    )
    bottom_surfaces = _surface_polygons_with_z_overrides(
        bottom_surfaces,
        bottom_existing_z_by_xy,
        output_fileformat,
    )
    if top_midpoint_corner_vertices is not None or top_midpoint_z_by_name:
        top_surfaces = _surface_polygons_with_midpoint_z(
            top_surfaces,
            W,
            E,
            N,
            S,
            top_midpoint_corner_vertices,
            output_fileformat,
            top_midpoint_z_by_name,
        )
    if (
        bottom_midpoint_corner_vertices is not None
        or bottom_midpoint_z_by_name
    ):
        bottom_surfaces = _surface_polygons_with_midpoint_z(
            bottom_surfaces,
            W,
            E,
            N,
            S,
            bottom_midpoint_corner_vertices,
            output_fileformat,
            bottom_midpoint_z_by_name,
        )

    previous_borders = target.borders
    previous_surface_borders = target.surfacePolygonBorders
    target.topSurfacePolygons = top_surfaces
    target.bottomSurfacePolygons = bottom_surfaces
    exterior_walls = (
        rebuild_nudged_surface_polygon_borders(
            target.topSurfacePolygons,
            target.bottomSurfacePolygons,
            previous_borders,
            previous_surface_borders,
            top_split_footprint,
            include_normal_cut_edges=False,
            W=W,
            E=E,
            N=N,
            S=S,
            output_fileformat=output_fileformat,
            side_cut_wall_sides=side_cut_wall_sides,
        )
        or []
    )
    contact_corner_set = set(contact_corners)
    cut_segments = {
        ("W", IntermediateCorner.SW): ("SW", "Wmid"),
        ("W", IntermediateCorner.NW): ("Wmid", "NW"),
        ("E", IntermediateCorner.SE): ("SE", "Emid"),
        ("E", IntermediateCorner.NE): ("Emid", "NE"),
        ("S", IntermediateCorner.SW): ("SW", "Smid"),
        ("S", IntermediateCorner.SE): ("Smid", "SE"),
        ("N", IntermediateCorner.NW): ("Nmid", "NW"),
        ("N", IntermediateCorner.NE): ("NE", "Nmid"),
    }
    requested_cut_footprints: set[XYEdge] = set()
    def normalized_point_xy(
        point: tuple[float, float],
    ) -> tuple[float, float]:
        return normalize_vertex_to_match_mesh_serialization(
            (point[0], point[1], 0.0),
            output_fileformat,
        )[:2]

    for (side, corner), (start_name, end_name) in cut_segments.items():
        if side not in split_sides or corner not in contact_corner_set:
            continue
        requested_cut_footprints.add(
            edge_xy_signature(
                normalized_point_xy(points[start_name]),
                normalized_point_xy(points[end_name]),
            ),
        )

    cut_walls = (
        _rebuild_matching_surface_polygon_borders(
            target.topSurfacePolygons,
            target.bottomSurfacePolygons,
            lambda footprint: footprint in requested_cut_footprints,
            output_fileformat,
        )
        if include_contact_cut_walls and requested_cut_footprints
        else []
    )
    target.surfacePolygonBorders = (
        exterior_walls + (cut_walls or [])
    ) or None
    target.borders = _empty_borders()
    return True


def apply_positive_z_normal_nudge(
    target: "cell",
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
    """Split a normal cell into positive-Z keep and complement pieces."""
    if not affected_corners or len(affected_corners) == 4:
        return False

    keep_footprint = nudge_keep_footprint(
        affected_corners,
        W,
        E,
        N,
        S,
    )
    if keep_footprint is None:
        return False

    full_footprint = full_cell_footprint(W, E, N, S)
    current_footprint = _current_surface_footprint(
        target.topSurfacePolygons,
        full_footprint,
        target.topquad,
    )
    pieces = [
        current_footprint.intersection(keep_footprint),
        current_footprint.difference(keep_footprint),
    ]
    if difference_footprint is not None and not difference_footprint.is_empty:
        aligned_difference_footprint = current_footprint.intersection(
            difference_footprint,
        )
        if not aligned_difference_footprint.is_empty:
            shared_boundary_pieces = (
                _polygonized_regions_with_shared_boundaries(
                    current_footprint,
                    [
                        aligned_difference_footprint.intersection(
                            keep_footprint,
                        ),
                        aligned_difference_footprint.difference(
                            keep_footprint,
                        ),
                        current_footprint.difference(
                            aligned_difference_footprint,
                        ),
                        current_footprint.intersection(
                            keep_footprint,
                        ),
                        current_footprint.difference(
                            keep_footprint,
                        ),
                    ],
                )
            )
            if shared_boundary_pieces:
                pieces = shared_boundary_pieces
    top_planes = _surface_planes_from_current_geometry(
        target.topquad,
        target.topSurfacePolygons,
        split_rotation,
    )
    bottom_planes = _surface_planes_from_current_geometry(
        target.bottomquad,
        target.bottomSurfacePolygons,
        split_rotation,
    )
    if not top_planes or not bottom_planes:
        return False

    new_top_polygons: list[shapely.Polygon] = []
    new_bottom_polygons: list[shapely.Polygon] = []
    for piece in pieces:
        new_top_polygons.extend(
            _triangulate_2d_geometry_to_3d_polygons(
                piece,
                top_planes,
                exterior_cw=False,
                output_fileformat=output_fileformat,
            )
        )
        new_bottom_polygons.extend(
            _triangulate_2d_geometry_to_3d_polygons(
                piece,
                bottom_planes,
                exterior_cw=True,
                output_fileformat=output_fileformat,
            )
        )

    if top_midpoint_corner_vertices is not None or top_midpoint_z_by_name:
        new_top_polygons = _surface_polygons_with_midpoint_z(
            new_top_polygons,
            W,
            E,
            N,
            S,
            top_midpoint_corner_vertices,
            output_fileformat,
            top_midpoint_z_by_name,
        )

    if not new_top_polygons or not new_bottom_polygons:
        target.clear_geometry()
        return True

    previous_borders = target.borders
    previous_surface_borders = target.surfacePolygonBorders
    target.topSurfacePolygons = new_top_polygons
    target.bottomSurfacePolygons = new_bottom_polygons
    target.surfacePolygonBorders = (
        rebuild_nudged_surface_polygon_borders(
            target.topSurfacePolygons,
            target.bottomSurfacePolygons,
            previous_borders,
            previous_surface_borders,
            current_footprint,
            include_normal_cut_edges=False,
            W=W,
            E=E,
            N=N,
            S=S,
            output_fileformat=output_fileformat,
        )
        or None
    )
    target.borders = _empty_borders()
    return True


def apply_positive_z_difference_nudge(
    target: "cell",
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
    """Remove the positive-Z contact footprint from a difference cell."""
    if not affected_corners or len(affected_corners) == 4:
        return False

    keep_footprint = nudge_keep_footprint(
        affected_corners,
        W,
        E,
        N,
        S,
    )
    if keep_footprint is None:
        return False

    cell_footprint_2D = full_cell_footprint(W, E, N, S)
    current_footprint = _current_surface_footprint(
        target.topSurfacePolygons,
        cell_footprint_2D,
        target.topquad,
    )
    keep_geometry = current_footprint.intersection(keep_footprint)
    top_planes = _surface_planes_from_current_geometry(
        target.topquad,
        target.topSurfacePolygons,
        split_rotation,
    )
    bottom_planes = _surface_planes_from_current_geometry(
        target.bottomquad,
        target.bottomSurfacePolygons,
        split_rotation,
    )
    if not top_planes or not bottom_planes:
        return False

    new_top_surfaces = _triangulate_2d_geometry_to_3d_polygons(
        keep_geometry,
        top_planes,
        exterior_cw=False,
        output_fileformat=output_fileformat,
    )
    if (
        top_midpoint_corner_vertices is not None
        or top_midpoint_z_by_name
    ):
        new_top_surfaces = _surface_polygons_with_midpoint_z(
            new_top_surfaces,
            W,
            E,
            N,
            S,
            top_midpoint_corner_vertices,
            output_fileformat,
            top_midpoint_z_by_name,
        )
    if (
        target.bottomSurfacePolygons
        and bottom_midpoint_corner_vertices is None
        and not bottom_midpoint_z_by_name
    ):
        new_bottom_surfaces = _clip_3d_surface_polygons_to_2d_geometry(
            target.bottomSurfacePolygons,
            keep_geometry,
            exterior_cw=True,
            output_fileformat=output_fileformat,
        )
    else:
        bottom_fallback_z_by_xy = (
            _nudge_midpoint_z_by_xy(
                W,
                E,
                N,
                S,
                bottom_midpoint_corner_vertices,
                output_fileformat,
                bottom_midpoint_z_by_name,
            )
            if bottom_midpoint_corner_vertices is not None
            or bottom_midpoint_z_by_name
            else None
        )
        new_bottom_surfaces = _triangulate_2d_geometry_to_3d_polygons(
            keep_geometry,
            bottom_planes,
            exterior_cw=True,
            output_fileformat=output_fileformat,
            fallback_z_by_xy=bottom_fallback_z_by_xy,
        )
    if (
        bottom_midpoint_corner_vertices is not None
        or bottom_midpoint_z_by_name
    ):
        new_bottom_surfaces = _surface_polygons_with_midpoint_z(
            new_bottom_surfaces,
            W,
            E,
            N,
            S,
            bottom_midpoint_corner_vertices,
            output_fileformat,
            bottom_midpoint_z_by_name,
        )
    if not new_top_surfaces or not new_bottom_surfaces:
        target.clear_geometry()
        return True

    previous_borders = target.borders
    previous_surface_borders = target.surfacePolygonBorders
    target.topSurfacePolygons = new_top_surfaces
    target.bottomSurfacePolygons = new_bottom_surfaces
    target.surfacePolygonBorders = (
        rebuild_nudged_surface_polygon_borders(
            target.topSurfacePolygons,
            target.bottomSurfacePolygons,
            previous_borders,
            previous_surface_borders,
            current_footprint,
            include_normal_cut_edges=True,
            W=W,
            E=E,
            N=N,
            S=S,
            output_fileformat=output_fileformat,
            side_cut_wall_sides=side_cut_wall_sides,
        )
        or None
    )
    target.borders = _empty_borders()
    return True


def flip_bottom_positive_z_contact_edges(
    target: "cell",
    split_rotation: int,
    output_fileformat: str,
    allowed_edges: set[Edge3D] | None = None,
) -> bool:
    """Flip bottom triangulation for actual clipped positive-Z contacts."""
    if not target.bottomSurfacePolygons:
        return False

    top_edges = surface_mesh_edge_counts(
        target.top_surface_meshes(),
        split_rotation,
        output_fileformat,
    )
    bottom_edge_polygons: dict[Edge3D, list[int]] = {}
    normalized_bottom_coords: list[list[tuple[float, ...]]] = []
    for polygon_index, polygon in enumerate(target.bottomSurfacePolygons):
        coords = [
            normalize_vertex_to_match_mesh_serialization(
                coord,
                output_fileformat,
            )
            for coord in polygon.exterior.coords[:-1]
        ]
        normalized_bottom_coords.append(coords)
        for coord_index, coord0 in enumerate(coords):
            coord1 = coords[(coord_index + 1) % len(coords)]
            edge_key = edge_3d_signature(coord0, coord1)
            bottom_edge_polygons.setdefault(edge_key, []).append(
                polygon_index,
            )

    replacements: dict[int, list[shapely.Polygon]] = {}
    consumed_polygons: set[int] = set()
    for edge_key, polygon_indices in bottom_edge_polygons.items():
        if allowed_edges is not None and edge_key not in allowed_edges:
            continue
        if len(polygon_indices) != 2:
            continue
        if polygon_indices[0] in consumed_polygons:
            continue
        if polygon_indices[1] in consumed_polygons:
            continue
        if edge_key[0][2] <= 0 or edge_key[1][2] <= 0:
            continue
        if top_edges.get(edge_key, 0) + len(polygon_indices) <= 2:
            continue

        edge_vertices = {edge_key[0], edge_key[1]}
        opposite_vertices: list[tuple[float, ...]] = []
        for polygon_index in polygon_indices:
            for coord in normalized_bottom_coords[polygon_index]:
                if coord not in edge_vertices and coord not in opposite_vertices:
                    opposite_vertices.append(coord)
        if len(opposite_vertices) != 2:
            continue

        a, b = edge_key
        c, d = opposite_vertices
        new_polygons: list[shapely.Polygon] = []
        for triangle_coords in (
            [c, d, a, c],
            [d, c, b, d],
        ):
            triangle = shapely.orient_polygons(
                shapely.Polygon(triangle_coords),
                exterior_cw=True,
            )
            normalized_triangle = (
                surface_polygon_normalized_to_match_mesh_serialization(
                    triangle,
                    output_fileformat,
                )
            )
            if normalized_triangle is not None:
                new_polygons.append(normalized_triangle)
        if len(new_polygons) != 2:
            continue

        replacements[polygon_indices[0]] = new_polygons
        consumed_polygons.update(polygon_indices)

    if not replacements:
        return False

    new_bottom_polygons: list[shapely.Polygon] = []
    for polygon_index, polygon in enumerate(target.bottomSurfacePolygons):
        if polygon_index in replacements:
            new_bottom_polygons.extend(replacements[polygon_index])
        elif polygon_index not in consumed_polygons:
            new_bottom_polygons.append(polygon)
    target.bottomSurfacePolygons = new_bottom_polygons
    return True
