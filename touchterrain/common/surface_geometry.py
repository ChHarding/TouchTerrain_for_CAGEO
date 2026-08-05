# surface_geometry.py
# build cell top/bottom surfaces and the walls that close them

"""Surface and wall geometry shared by cell creation and nudging.

These helpers turn 2D footprints into oriented 3D surface triangles, clip
existing surfaces against new footprints, and rebuild the walls that close a
clipped cell. They know about surfaces and walls but not about cells, nudge
plans, or rasters, so both ordinary cell creation and the nudge repair passes
can use them.
"""

from collections.abc import Collection, Sequence
from typing import Callable

import shapely

from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.interpolate_Z import interpolate_z_planar
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.vectors import Vector, Point
from touchterrain.common.mesh_vocabulary import (
    CARDINAL_DIRECTIONS,
    CardinalWallMap,
    CellBottomGeometry,
    Edge3D,
    SerializedVertexCache,
    XYEdge,
    _empty_borders,
)
from touchterrain.common.mesh_serialization import (
    _canonicalize_clipped_triangles_by_serialized_xy,
    boundary_edge_map_from_meshes,
    edge_xy_signature,
    normalize_coordinate_to_match_mesh_serialization,
    normalize_vertex_to_match_mesh_serialization,
    polygon_normalized_to_match_mesh_serialization,
    triangle_xy_collapses_after_mesh_serialization,
)


def _create_cell_bottom_geometry(
    W: float,
    E: float,
    N: float,
    S: float,
    NEelev: float,
    NWelev: float,
    SEelev: float,
    SWelev: float,
    nudge_enabled: bool,
) -> CellBottomGeometry:
    """Create bottom vertices, bottom quad, and optional nudge corner map."""
    NEb = vertex(E, N, NEelev)
    NWb = vertex(W, N, NWelev)
    SEb = vertex(E, S, SEelev)
    SWb = vertex(W, S, SWelev)
    botq = quad(NWb, NEb, SEb, SWb)
    bottom_corner_vertices = None
    if nudge_enabled:
        bottom_corner_vertices = {
            IntermediateCorner.NW: NWb,
            IntermediateCorner.NE: NEb,
            IntermediateCorner.SW: SWb,
            IntermediateCorner.SE: SEb,
        }
    return botq, bottom_corner_vertices


def _iter_polygon_parts(geometry: shapely.Geometry) -> list[shapely.Polygon]:
    """Return non-empty polygon parts from a Shapely geometry."""
    if geometry.is_empty:
        return []
    if isinstance(geometry, shapely.Polygon):
        return [geometry] if geometry.area > 0 else []
    polygons: list[shapely.Polygon] = []
    if hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            polygons.extend(_iter_polygon_parts(child))
    return polygons


def _has_valid_z_plane(polygon: shapely.Polygon) -> bool:
    """Return whether a triangular polygon can interpolate Z values."""
    coords = polygon.exterior.coords
    if len(coords) != 4 or len(coords[0]) < 3:
        return False
    p1 = coords[0]
    p2 = coords[1]
    p3 = coords[2]
    xy_cross = (
        (p2[0] - p1[0]) * (p3[1] - p1[1])
        - (p2[1] - p1[1]) * (p3[0] - p1[0])
    )
    return abs(xy_cross) >= 1e-6


def _surface_planes_from_current_geometry(
    surface_quad: quad | None,
    surface_polygons: list[shapely.Polygon] | None,
    split_rotation: int,
) -> list[shapely.Polygon]:
    """Return interpolation planes for the current surface representation."""
    if surface_polygons:
        planes = [
            surface_polygon
            for surface_polygon in surface_polygons
            if _has_valid_z_plane(surface_polygon)
        ]
        if planes:
            return planes
    if surface_quad is None:
        return []
    return surface_quad.get_triangles_in_polygons(split_rotation)


def _current_surface_footprint(
    surface_polygons: list[shapely.Polygon] | None,
    fallback: shapely.Polygon,
    surface_quad: quad | None = None,
) -> shapely.Geometry:
    """Return the emitted XY footprint for the current surface."""
    if surface_polygons:
        return _union_polygon_footprint(surface_polygons, fallback)
    if surface_quad is not None:
        coords = [
            surface_vertex.coords[:2]
            for surface_vertex in surface_quad.vl
            if surface_vertex is not None
        ]
        if len(coords) >= 3:
            return shapely.Polygon(coords)
    return fallback


def _union_polygon_footprint(
    geometries: list[shapely.Geometry] | None,
    fallback: shapely.Polygon,
) -> shapely.Geometry:
    if not geometries:
        return fallback
    polygons: list[shapely.Polygon] = []
    for geometry in geometries:
        polygons.extend(_iter_polygon_parts(shapely.force_2d(geometry)))
    if not polygons:
        return shapely.GeometryCollection()
    return shapely.union_all(polygons)


def _triangulated_clipped_surface_triangles_2d(
    geometries: list[shapely.Geometry] | None,
    output_fileformat: str,
) -> list[shapely.Polygon]:
    """Return canonical 2D triangles for a clipped cell footprint."""
    clipped_triangles: list[shapely.Polygon] = []
    for polygon in geometries or []:
        if not isinstance(polygon, shapely.Polygon):
            continue
        clipped_triangles.extend(
            _iter_polygon_parts(
                shapely.constrained_delaunay_triangles(polygon),
            )
        )
    return _canonicalize_clipped_triangles_by_serialized_xy(
        clipped_triangles,
        output_fileformat,
    )


def _surface_polygons_from_2d_triangles(
    triangles_2d: Sequence[shapely.Polygon],
    planes_3d: list[shapely.Polygon],
    exterior_cw: bool,
    output_fileformat: str,
    keep_collapsed_placeholders: bool = False,
) -> list[shapely.Polygon | None]:
    """Interpolate 2D triangles onto 3D planes and normalize output."""
    surface_polygons: list[shapely.Polygon | None] = []
    for triangle in triangles_2d:
        oriented_triangle = shapely.orient_polygons(
            triangle,
            exterior_cw=exterior_cw,
        )
        triangle_3d = interpolate_z_planar(
            geometry_2d=oriented_triangle,
            planes_3d=planes_3d,
        )
        if not isinstance(triangle_3d, shapely.Polygon):
            raise TypeError(
                "Surface interpolation did not return a Polygon; got "
                f"{type(triangle_3d)}."
            )
        normalized_triangle = polygon_normalized_to_match_mesh_serialization(
            triangle_3d,
            output_fileformat,
        )
        if normalized_triangle is not None or keep_collapsed_placeholders:
            surface_polygons.append(normalized_triangle)
    return surface_polygons


def _clipped_cell_surface_polygons(
    geometries_2d: list[shapely.Geometry] | None,
    top_surface_quad: quad,
    bottom_surface_quad: quad,
    split_rotation: int,
    output_fileformat: str,
) -> tuple[
    list[shapely.Polygon] | None,
    list[shapely.Polygon] | None,
    bool,
]:
    """Build matching serialized top and bottom triangles for a clipped cell."""
    if geometries_2d is None:
        return None, None, False

    triangles_2d = _triangulated_clipped_surface_triangles_2d(
        geometries_2d,
        output_fileformat,
    )
    top_polygons = _surface_polygons_from_2d_triangles(
        triangles_2d,
        top_surface_quad.get_triangles_in_polygons(
            split_rotation=split_rotation,
        ),
        exterior_cw=False,
        output_fileformat=output_fileformat,
        keep_collapsed_placeholders=True,
    )
    bottom_polygons = _surface_polygons_from_2d_triangles(
        triangles_2d,
        bottom_surface_quad.get_triangles_in_polygons(
            split_rotation=split_rotation,
        ),
        exterior_cw=True,
        output_fileformat=output_fileformat,
        keep_collapsed_placeholders=True,
    )
    if len(top_polygons) != len(bottom_polygons):
        raise RuntimeError(
            "Top and bottom clipped surface triangle counts differ during "
            "output cleanup."
        )

    kept_top_polygons: list[shapely.Polygon] = []
    kept_bottom_polygons: list[shapely.Polygon] = []
    for top_polygon, bottom_polygon in zip(top_polygons, bottom_polygons):
        if top_polygon is None or bottom_polygon is None:
            continue
        kept_top_polygons.append(top_polygon)
        kept_bottom_polygons.append(bottom_polygon)

    all_surfaces_collapsed = bool(top_polygons and not kept_top_polygons)
    return (
        kept_top_polygons,
        kept_bottom_polygons,
        all_surfaces_collapsed,
    )


def _triangulate_2d_geometry_to_3d_polygons(
    geometry: shapely.Geometry,
    planes_3d: list[shapely.Polygon],
    exterior_cw: bool,
    output_fileformat: str,
    fallback_z_by_xy: dict[tuple[float, float], float] | None = None,
    canonicalize_serialized_xy: bool = False,
) -> list[shapely.Polygon]:
    output: list[shapely.Polygon] = []

    def interpolate_triangle(
        oriented_triangle: shapely.Polygon,
    ) -> shapely.Polygon:
        try:
            triangle_3d = interpolate_z_planar(
                geometry_2d=oriented_triangle,
                planes_3d=planes_3d,
            )
        except ValueError:
            if not fallback_z_by_xy:
                raise

            coords_3d = []
            for coord in oriented_triangle.exterior.coords[:-1]:
                normalized_xy = normalize_vertex_to_match_mesh_serialization(
                    (coord[0], coord[1], 0.0),
                    output_fileformat,
                )[:2]
                if normalized_xy in fallback_z_by_xy:
                    coords_3d.append(
                        (
                            coord[0],
                            coord[1],
                            fallback_z_by_xy[normalized_xy],
                        )
                    )
                    continue

                point_3d = interpolate_z_planar(
                    geometry_2d=shapely.Point(coord),
                    planes_3d=planes_3d,
                )
                if not isinstance(point_3d, shapely.Point):
                    raise TypeError(
                        "Fallback interpolation did not return a Point."
                    )
                coords_3d.append(point_3d.coords[0])
            coords_3d.append(coords_3d[0])
            triangle_3d = shapely.Polygon(coords_3d)

        if not isinstance(triangle_3d, shapely.Polygon):
            raise TypeError("Z0 nudge interpolation did not return a Polygon.")
        return triangle_3d

    triangles_2d: list[shapely.Polygon] = []
    for polygon in _iter_polygon_parts(geometry):
        triangles = shapely.constrained_delaunay_triangles(polygon)
        triangles_2d.extend(_iter_polygon_parts(triangles))
    if canonicalize_serialized_xy:
        triangles_2d = _canonicalize_clipped_triangles_by_serialized_xy(
            triangles_2d,
            output_fileformat,
        )

    for triangle in triangles_2d:
        oriented_triangle = shapely.orient_polygons(
            triangle,
            exterior_cw=exterior_cw,
        )
        triangle_3d = interpolate_triangle(oriented_triangle)
        normalized_triangle = polygon_normalized_to_match_mesh_serialization(
            triangle_3d,
            output_fileformat,
        )
        if normalized_triangle is not None:
            output.append(normalized_triangle)
    return output


def _polygonized_regions_with_shared_boundaries(
    base_footprint: shapely.Geometry,
    regions: Sequence[shapely.Geometry],
) -> list[shapely.Polygon]:
    """Return polygon regions noded at all shared boundary intersections."""
    linework: list[shapely.Geometry] = []
    for region in regions:
        for polygon in _iter_polygon_parts(region):
            if polygon.area > 0:
                linework.append(polygon.boundary)

    if not linework:
        return []

    noded_linework = shapely.union_all(linework)
    polygons = shapely.polygonize([noded_linework])
    output: list[shapely.Polygon] = []
    for polygon in _iter_polygon_parts(polygons):
        if polygon.area <= 0 or not base_footprint.covers(
            polygon.representative_point(),
        ):
            continue
        clipped = polygon.intersection(base_footprint)
        output.extend(
            part
            for part in _iter_polygon_parts(clipped)
            if part.area > 0
        )
    return output


def _clip_3d_surface_polygons_to_2d_geometry(
    surface_polygons: list[shapely.Polygon],
    geometry: shapely.Geometry,
    exterior_cw: bool,
    output_fileformat: str,
) -> list[shapely.Polygon]:
    """Clip existing 3D surface polygons and keep their clipped Z plane."""
    output: list[shapely.Polygon] = []
    geometry_2d = shapely.force_2d(geometry)
    for surface_polygon in surface_polygons:
        if not _has_valid_z_plane(surface_polygon):
            continue
        clipped = surface_polygon.intersection(geometry_2d)
        for clipped_part in _iter_polygon_parts(clipped):
            triangles = shapely.constrained_delaunay_triangles(
                shapely.force_2d(clipped_part),
            )
            for triangle in _iter_polygon_parts(triangles):
                oriented_triangle = shapely.orient_polygons(
                    triangle,
                    exterior_cw=exterior_cw,
                )
                triangle_3d = interpolate_z_planar(
                    geometry_2d=oriented_triangle,
                    planes_3d=[surface_polygon],
                )
                if not isinstance(triangle_3d, shapely.Polygon):
                    raise TypeError(
                        "Clipped surface interpolation did not return a "
                        "Polygon."
                    )
                normalized_triangle = (
                    polygon_normalized_to_match_mesh_serialization(
                        triangle_3d,
                        output_fileformat,
                    )
                )
                if normalized_triangle is not None:
                    output.append(normalized_triangle)
    return output


def _surface_wall_requested_lines(
    surface_polygon_borders: list[quad] | None,
    output_fileformat: str | None = None,
) -> shapely.Geometry | None:
    lines: list[shapely.LineString] = []
    if not surface_polygon_borders:
        return None
    for surface_border in surface_polygon_borders:
        xy_coords: list[tuple[float, float]] = []
        for border_vertex in surface_border.vl:
            if border_vertex is None:
                continue
            coords = border_vertex.coords
            if output_fileformat is not None:
                coords = normalize_vertex_to_match_mesh_serialization(
                    coords,
                    output_fileformat,
                )
            xy = (coords[0], coords[1])
            if xy not in xy_coords:
                xy_coords.append(xy)
        if len(xy_coords) == 2:
            lines.append(shapely.LineString(xy_coords))
    if not lines:
        return None
    return shapely.union_all(lines)


def _geometry_boundary_linework(
    geometry: shapely.Geometry,
    output_fileformat: str,
) -> shapely.Geometry | None:
    lines: list[shapely.LineString] = []
    for polygon in _iter_polygon_parts(shapely.force_2d(geometry)):
        for ring in (polygon.exterior, *polygon.interiors):
            coords = list(ring.coords)
            for index in range(len(coords) - 1):
                start = (
                    normalize_coordinate_to_match_mesh_serialization(
                        coords[index][0],
                        output_fileformat,
                    ),
                    normalize_coordinate_to_match_mesh_serialization(
                        coords[index][1],
                        output_fileformat,
                    ),
                )
                end = (
                    normalize_coordinate_to_match_mesh_serialization(
                        coords[index + 1][0],
                        output_fileformat,
                    ),
                    normalize_coordinate_to_match_mesh_serialization(
                        coords[index + 1][1],
                        output_fileformat,
                    ),
                )
                if start != end:
                    lines.append(shapely.LineString((start, end)))
    if not lines:
        return None
    return shapely.union_all(lines)


def _linework_covers_footprint(
    linework: shapely.Geometry | None,
    footprint: XYEdge,
) -> bool:
    return linework is not None and linework.covers(shapely.LineString(footprint))


def _split_surface_boundary_edges_for_wall_matches(
    surfaces: list[shapely.Polygon],
    boundary_edges: dict[XYEdge, Edge3D],
    split_vertices_xy: set[tuple[float, float]],
    footprint_is_requested: Callable[[XYEdge], bool],
    output_fileformat: str,
) -> list[shapely.Polygon]:
    split_surfaces: list[shapely.Polygon] = []

    for surface in surfaces:
        coords = list(surface.exterior.coords)
        if len(coords) < 4:
            continue
        if (
            len(coords) == 4
            and triangle_xy_collapses_after_mesh_serialization(
                coords[:-1],
                output_fileformat,
            )
        ):
            split_surfaces.append(surface)
            continue

        new_coords: list[tuple[float, ...]] = []
        inserted_point = False
        for index in range(len(coords) - 1):
            start = normalize_vertex_to_match_mesh_serialization(
                coords[index],
                output_fileformat,
            )
            end = normalize_vertex_to_match_mesh_serialization(
                coords[index + 1],
                output_fileformat,
            )
            footprint = edge_xy_signature(start, end)
            new_coords.append(start)
            if footprint not in boundary_edges or not footprint_is_requested(
                footprint,
            ):
                continue

            line = shapely.LineString((start[:2], end[:2]))
            line_length = line.length
            if line_length == 0:
                continue

            split_points: list[tuple[float, tuple[float, float]]] = []
            for split_xy in split_vertices_xy:
                if split_xy == start[:2] or split_xy == end[:2]:
                    continue
                point = shapely.Point(split_xy)
                if not line.covers(point):
                    continue
                distance = line.project(point)
                if distance <= 0 or distance >= line_length:
                    continue
                split_points.append((distance, split_xy))

            if not split_points:
                continue

            inserted_point = True
            for distance, split_xy in sorted(split_points):
                ratio = distance / line_length
                z = start[2] + (end[2] - start[2]) * ratio
                new_coords.append((split_xy[0], split_xy[1], z))

        if not inserted_point:
            split_surfaces.append(surface)
            continue

        new_coords.append(new_coords[0])
        split_footprint = shapely.Polygon([coord[:2] for coord in new_coords])
        exterior_cw = not shapely.is_ccw(shapely.LinearRing(new_coords))
        try:
            split_surfaces.extend(
                _triangulate_2d_geometry_to_3d_polygons(
                    split_footprint,
                    [surface],
                    exterior_cw=exterior_cw,
                    output_fileformat=output_fileformat,
                )
            )
        except ValueError as exc:
            if "near-vertical or collinear" not in str(exc):
                raise
            split_surfaces.append(surface)
            continue

    return split_surfaces


def _rebuild_matching_surface_polygon_borders(
    top_surfaces: list[shapely.Polygon],
    bottom_surfaces: list[shapely.Polygon],
    footprint_is_requested: Callable[[XYEdge], bool],
    output_fileformat: str,
) -> list[quad]:
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
    split_vertices_xy: set[tuple[float, float]] = set()
    for boundary_map in (top_boundary_edges, bottom_boundary_edges):
        for footprint in boundary_map:
            if footprint_is_requested(footprint):
                split_vertices_xy.update(footprint)

    if split_vertices_xy:
        top_surfaces[:] = _split_surface_boundary_edges_for_wall_matches(
            top_surfaces,
            top_boundary_edges,
            split_vertices_xy,
            footprint_is_requested,
            output_fileformat,
        )
        bottom_surfaces[:] = _split_surface_boundary_edges_for_wall_matches(
            bottom_surfaces,
            bottom_boundary_edges,
            split_vertices_xy,
            footprint_is_requested,
            output_fileformat,
        )
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

    rebuilt_borders: list[quad] = []
    for footprint, top_edge in top_boundary_edges.items():
        if not footprint_is_requested(footprint):
            continue
        if footprint not in bottom_boundary_edges:
            continue

        bottom_edge = bottom_boundary_edges[footprint]
        top_start_xy = (top_edge[0][0], top_edge[0][1])
        bottom_start_xy = (bottom_edge[0][0], bottom_edge[0][1])
        if top_start_xy == bottom_start_xy:
            bottom_edge = (bottom_edge[1], bottom_edge[0])

        wall = make_wall_without_exact_duplicate_vertices(
            vertex(*top_edge[1]),
            vertex(*top_edge[0]),
            vertex(*bottom_edge[1]),
            vertex(*bottom_edge[0]),
            output_fileformat=output_fileformat,
        )
        if wall is not None:
            rebuilt_borders.append(wall)
    return rebuilt_borders


# function to calculate the normal for a triangle
def get_normal(tri):
    "in: 3 verts, out normal (nx, ny,nz) with length 1"

    (v0, v1, v2) = tri
    p0 = Point.from_list(v0.get())
    p1 = Point.from_list(v1.get())
    p2 = Point.from_list(v2.get())
    a = Vector.from_points(p1, p0)
    b = Vector.from_points(p1, p2)
    c = a.cross(b)
    m = float(c.magnitude())
    if m == 0:
        normal = [0, 0, 0]
    else:
        normal = [c.x/m, c.y/m, c.z/m]
    return normal


def make_wall_without_exact_duplicate_vertices(
    v0: vertex,
    v1: vertex,
    v2: vertex,
    v3: vertex,
    output_fileformat: str = "STLb",
) -> quad | None:
    """Create a wall mesh, dropping duplicate vertices.

    Difference meshes can produce wall endpoints where top and bottom serialize
    to the same coordinate. In that case the wall should be a triangle, or
    omitted when the whole wall has zero height.
    """
    unique_vertices: list[vertex] = []
    unique_signatures: set[tuple[float, ...]] = set()

    for v in (v0, v1, v2, v3):
        signature = normalize_vertex_to_match_mesh_serialization(
            v.coords,
            output_fileformat,
        )
        if signature not in unique_signatures:
            unique_vertices.append(v)
            unique_signatures.add(signature)

    if len(unique_vertices) < 3:
        return None
    if len(unique_vertices) == 3:
        return quad(
            unique_vertices[0],
            unique_vertices[1],
            unique_vertices[2],
            None,
        )
    return quad(
        unique_vertices[0],
        unique_vertices[1],
        unique_vertices[2],
        unique_vertices[3],
    )


def _cardinal_wall_vertices(
    side: str,
    top_vertices: Sequence[vertex],
    bottom_vertices: Sequence[vertex],
) -> tuple[vertex, vertex, vertex, vertex]:
    """Return wall vertices for one side using cell quad vertex order."""
    if side == "N":
        return (
            bottom_vertices[0],
            top_vertices[0],
            top_vertices[3],
            bottom_vertices[1],
        )
    if side == "S":
        return (
            bottom_vertices[2],
            top_vertices[2],
            top_vertices[1],
            bottom_vertices[3],
        )
    if side == "E":
        return (
            top_vertices[3],
            top_vertices[2],
            bottom_vertices[2],
            bottom_vertices[1],
        )
    if side == "W":
        return (
            top_vertices[1],
            top_vertices[0],
            bottom_vertices[0],
            bottom_vertices[3],
        )
    raise ValueError(f"Unknown cardinal wall side: {side}")


def _build_cardinal_wall_borders(
    requested_sides: Collection[str],
    top_vertices: Sequence[vertex],
    bottom_vertices: Sequence[vertex],
    output_fileformat: str,
) -> CardinalWallMap:
    """Return requested N/S/E/W walls as wall quads."""
    borders = _empty_borders()
    for side in CARDINAL_DIRECTIONS:
        if side not in requested_sides:
            continue
        wall = make_wall_without_exact_duplicate_vertices(
            *_cardinal_wall_vertices(
                side,
                top_vertices,
                bottom_vertices,
            ),
            output_fileformat=output_fileformat,
        )
        if wall is not None:
            borders[side] = wall
    return borders
