# mesh_serialization.py
# compare geometry the way the emitted mesh file will actually contain it

"""Serialized-coordinate identity for emitted mesh geometry.

Geometry is built at full in-memory precision and only normalized here, when
the code is asking a final-output question: does this edge match that edge, is
this edge overused, does this triangle collapse once written? See
``spec/precision_serialization_conventions.md``.

For ``STLb`` a coordinate round-trips through binary STL float32 before being
rounded; for ``STLa`` it is only rounded to ASCII STL text precision. Both
normalize negative zero to positive zero.
"""

import struct

from collections.abc import Iterable, Sequence

import shapely

from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.mesh_vocabulary import (
    Coordinate,
    DirectedEdge3D,
    Edge3D,
    MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    SerializedVertexCache,
    SurfaceMesh,
    XYEdge,
)


BINARY_FLOAT = struct.Struct("<f")


def edge_xy_signature(coord0: Coordinate, coord1: Coordinate) -> XYEdge:
    """Return an orientation-independent XY signature for an edge."""
    return tuple(
        sorted(
            (
                (coord0[0], coord0[1]),
                (coord1[0], coord1[1]),
            )
        )
    )


def edge_3d_signature(coord0: Coordinate, coord1: Coordinate) -> Edge3D:
    """Return an orientation-independent 3D signature for an edge."""
    coord0_key = (
        coord0
        if isinstance(coord0, tuple) and len(coord0) == 3
        else tuple(coord0[:3])
    )
    coord1_key = (
        coord1
        if isinstance(coord1, tuple) and len(coord1) == 3
        else tuple(coord1[:3])
    )
    return tuple(sorted((coord0_key, coord1_key)))


def boundary_edge_map_from_meshes(
    meshes: Iterable[SurfaceMesh] | None,
    output_fileformat: str | None = None,
    serialized_vertices: SerializedVertexCache | None = None,
) -> dict[XYEdge, Edge3D]:
    """Return emitted boundary edges for quads and triangulated polygons."""
    edge_counts: dict[XYEdge, int] = {}
    edge_coords: dict[XYEdge, Edge3D] = {}
    if serialized_vertices is None:
        serialized_vertices = {}
    if meshes is None:
        return {}

    def add_edge(coord0: Coordinate, coord1: Coordinate) -> None:
        output_coord0 = _serialized_vertex_from_cache(
            coord0,
            output_fileformat,
            serialized_vertices,
        )
        output_coord1 = _serialized_vertex_from_cache(
            coord1,
            output_fileformat,
            serialized_vertices,
        )
        footprint = edge_xy_signature(output_coord0, output_coord1)
        edge_counts[footprint] = edge_counts.get(footprint, 0) + 1
        edge_coords[footprint] = (output_coord0, output_coord1)

    for mesh in meshes:
        if isinstance(mesh, quad):
            coords = [v.coords for v in mesh.vl if v is not None]
            for ci in range(len(coords)):
                add_edge(coords[ci], coords[(ci + 1) % len(coords)])
        elif isinstance(mesh, shapely.Polygon):
            rings = [mesh.exterior, *mesh.interiors]
            for ring in rings:
                coords = ring.coords
                for ci in range(len(coords) - 1):
                    add_edge(coords[ci], coords[ci + 1])

    return {
        footprint: coords
        for footprint, coords in edge_coords.items()
        if edge_counts[footprint] == 1
    }


def normalize_coordinate_to_match_mesh_serialization(
    value: float,
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
) -> float:
    """Return a coordinate as it will be serialized in mesh output."""
    if fileformat == "STLb":
        return _normalize_stlb_coordinate(value, decimals)
    return _normalize_decimal_coordinate(value, decimals)


def _normalize_decimal_coordinate(value: float, decimals: int) -> float:
    """Return a rounded text-format coordinate value."""
    return round(value, decimals) + 0.0


def _normalize_stlb_coordinate(value: float, decimals: int) -> float:
    """Return a rounded binary-STL coordinate value."""
    return (
        round(
            BINARY_FLOAT.unpack(BINARY_FLOAT.pack(value))[0] + 0.0,
            decimals,
        )
        + 0.0
    )


def normalize_vertex_to_match_mesh_serialization(
    coord: Coordinate,
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
) -> tuple[float, ...]:
    """Return a vertex as it will be serialized in mesh output."""
    if len(coord) < 3:
        normalize = (
            _normalize_stlb_coordinate
            if fileformat == "STLb"
            else _normalize_decimal_coordinate
        )
        return tuple(
            normalize(value, decimals)
            for value in coord
        )

    if fileformat == "STLb":
        pack_float = BINARY_FLOAT.pack
        unpack_float = BINARY_FLOAT.unpack
        return (
            round(
                unpack_float(pack_float(coord[0]))[0] + 0.0,
                decimals,
            )
            + 0.0,
            round(
                unpack_float(pack_float(coord[1]))[0] + 0.0,
                decimals,
            )
            + 0.0,
            round(
                unpack_float(pack_float(coord[2]))[0] + 0.0,
                decimals,
            )
            + 0.0,
        )

    return (
        round(coord[0], decimals) + 0.0,
        round(coord[1], decimals) + 0.0,
        round(coord[2], decimals) + 0.0,
    )


def _serialized_vertex_from_cache(
    coord: Coordinate,
    output_fileformat: str | None,
    serialized_vertices: SerializedVertexCache,
) -> tuple[float, ...]:
    """Return a cached coordinate normalized to emitted mesh precision."""
    coord_key = coord if isinstance(coord, tuple) else tuple(coord)
    output_coord = serialized_vertices.get(coord_key)
    if output_coord is not None:
        return output_coord

    if output_fileformat is None:
        output_coord = coord_key[:3]
    else:
        output_coord = normalize_vertex_to_match_mesh_serialization(
            coord_key,
            output_fileformat,
        )
    serialized_vertices[coord_key] = output_coord
    return output_coord


def surface_mesh_edge_counts(
    meshes: Iterable[SurfaceMesh | None],
    split_rotation: int,
    output_fileformat: str,
    serialized_vertices: SerializedVertexCache | None = None,
) -> dict[Edge3D, int]:
    """Count serialized triangle edges emitted by surface meshes."""
    edge_counts, _directed_edge_counts = surface_mesh_edge_usage(
        meshes,
        split_rotation,
        output_fileformat,
        serialized_vertices,
        include_directed=False,
    )
    return edge_counts


def surface_mesh_edge_usage(
    meshes: Iterable[SurfaceMesh | None],
    split_rotation: int,
    output_fileformat: str,
    serialized_vertices: SerializedVertexCache | None = None,
    include_directed: bool = True,
) -> tuple[dict[Edge3D, int], dict[DirectedEdge3D, int]]:
    """Count unordered and directed serialized triangle edges."""
    edge_counts: dict[Edge3D, int] = {}
    directed_edge_counts: dict[DirectedEdge3D, int] = {}
    if serialized_vertices is None:
        serialized_vertices = {}

    def add_triangle_edge(coord0: Coordinate, coord1: Coordinate) -> None:
        output_coord0 = _serialized_vertex_from_cache(
            coord0,
            output_fileformat,
            serialized_vertices,
        )
        output_coord1 = _serialized_vertex_from_cache(
            coord1,
            output_fileformat,
            serialized_vertices,
        )
        edge_key = edge_3d_signature(output_coord0, output_coord1)
        edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1
        if not include_directed:
            return
        directed_edge = (output_coord0, output_coord1)
        directed_edge_counts[directed_edge] = (
            directed_edge_counts.get(directed_edge, 0) + 1
        )

    for mesh in meshes:
        if mesh is None:
            continue
        if isinstance(mesh, quad):
            for triangle in mesh.get_triangles(split_rotation):
                for index, triangle_vertex in enumerate(triangle):
                    add_triangle_edge(
                        triangle_vertex.coords,
                        triangle[(index + 1) % len(triangle)].coords,
                    )
        elif isinstance(mesh, shapely.Polygon):
            coords = mesh.exterior.coords
            for index in range(len(coords) - 1):
                add_triangle_edge(coords[index], coords[index + 1])
    return edge_counts, directed_edge_counts


def directed_edges_are_balanced(
    edge_counts: dict[Edge3D, int],
    directed_edge_counts: dict[DirectedEdge3D, int],
    edges_to_check: set[Edge3D] | None = None,
) -> bool:
    """Return whether every checked manifold edge has opposite directions."""
    check_edges = edges_to_check if edges_to_check is not None else set(edge_counts)
    for edge_key in check_edges:
        if edge_counts.get(edge_key, 0) != 2:
            continue
        forward = directed_edge_counts.get((edge_key[0], edge_key[1]), 0)
        reverse = directed_edge_counts.get((edge_key[1], edge_key[0]), 0)
        if forward != 1 or reverse != 1:
            return False
    return True


def triangle_collapses_after_mesh_serialization(
    triangle: Sequence[Coordinate],
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    serialized_vertices: SerializedVertexCache | None = None,
) -> bool:
    """Return whether a triangle is degenerate after mesh serialization."""
    if (
        serialized_vertices is None
        or decimals != MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION
    ):
        p0, p1, p2 = [
            normalize_vertex_to_match_mesh_serialization(
                coord=coord,
                fileformat=fileformat,
                decimals=decimals,
            )
            for coord in triangle
        ]
    else:
        p0, p1, p2 = [
            _serialized_vertex_from_cache(
                coord,
                fileformat,
                serialized_vertices,
            )
            for coord in triangle
        ]
    return _serialized_triangle_collapses((p0, p1, p2))


def _serialized_triangle_collapses(
    triangle: Sequence[Coordinate],
) -> bool:
    """Return whether already-serialized 3D triangle coordinates collapse."""
    p0, p1, p2 = triangle
    p0_xyz = tuple(p0[:3])
    p1_xyz = tuple(p1[:3])
    p2_xyz = tuple(p2[:3])
    if p0_xyz == p1_xyz or p0_xyz == p2_xyz or p1_xyz == p2_xyz:
        return True

    a = (
        p1[0] - p0[0],
        p1[1] - p0[1],
        p1[2] - p0[2],
    )
    b = (
        p2[0] - p0[0],
        p2[1] - p0[1],
        p2[2] - p0[2],
    )
    cross = (
        round(a[1] * b[2] - a[2] * b[1], 12),
        round(a[2] * b[0] - a[0] * b[2], 12),
        round(a[0] * b[1] - a[1] * b[0], 12),
    )
    return cross == (0.0, 0.0, 0.0)


def triangle_xy_collapses_after_mesh_serialization(
    triangle: Sequence[Coordinate],
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    serialized_vertices: SerializedVertexCache | None = None,
) -> bool:
    """Return whether a surface triangle has no serialized XY area."""
    if (
        serialized_vertices is None
        or decimals != MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION
    ):
        p0, p1, p2 = [
            normalize_vertex_to_match_mesh_serialization(
                coord=coord,
                fileformat=fileformat,
                decimals=decimals,
            )[:2]
            for coord in triangle
        ]
    else:
        p0, p1, p2 = [
            _serialized_vertex_from_cache(
                coord,
                fileformat,
                serialized_vertices,
            )[:2]
            for coord in triangle
        ]
    return _serialized_triangle_xy_collapses((p0, p1, p2))


def _serialized_triangle_xy_collapses(
    triangle: Sequence[Coordinate],
) -> bool:
    """Return whether already-serialized triangle XY coordinates collapse."""
    p0, p1, p2 = triangle
    p0_xy = tuple(p0[:2])
    p1_xy = tuple(p1[:2])
    p2_xy = tuple(p2[:2])
    if p0_xy == p1_xy or p0_xy == p2_xy or p1_xy == p2_xy:
        return True

    a = (
        p1_xy[0] - p0_xy[0],
        p1_xy[1] - p0_xy[1],
    )
    b = (
        p2_xy[0] - p0_xy[0],
        p2_xy[1] - p0_xy[1],
    )
    cross = round(a[0] * b[1] - a[1] * b[0], 12)
    return cross == 0.0


def _serialized_xy_key(
    coord: Coordinate,
    output_fileformat: str,
) -> tuple[float, float]:
    """Return the XY coordinate key that mesh serialization will emit."""
    return normalize_vertex_to_match_mesh_serialization(
        (coord[0], coord[1], 0.0),
        output_fileformat,
    )[:2]


def _line_serialized_xy_signature(
    line: shapely.LineString,
    output_fileformat: str,
) -> XYEdge | None:
    """Return an orientation-independent serialized XY line signature."""
    coords = list(line.coords)
    if len(coords) < 2:
        return None

    start_xy = _serialized_xy_key(coords[0], output_fileformat)
    end_xy = _serialized_xy_key(coords[-1], output_fileformat)
    if start_xy == end_xy:
        return None
    return tuple(sorted((start_xy, end_xy)))


def _line_with_serialized_xy(
    line: shapely.LineString,
    output_fileformat: str,
) -> shapely.LineString | None:
    """Return a 2D line with endpoints at serialized XY coordinates."""
    coords = list(line.coords)
    if len(coords) < 2:
        return None

    start_xy = _serialized_xy_key(coords[0], output_fileformat)
    end_xy = _serialized_xy_key(coords[-1], output_fileformat)
    if start_xy == end_xy:
        return None
    return shapely.LineString([start_xy, end_xy])


def _boundary_line_map_by_serialized_xy(
    edges: Sequence[shapely.LineString],
    output_fileformat: str,
) -> dict[XYEdge, list[shapely.LineString]]:
    """Return serialized XY edge map for edges used exactly once."""
    edge_map: dict[XYEdge, list[shapely.LineString]] = {}
    for edge in edges:
        edge_key = _line_serialized_xy_signature(
            edge,
            output_fileformat,
        )
        if edge_key is None:
            continue
        edge_map.setdefault(edge_key, []).append(edge)
    return {
        edge_key: edge_matches
        for edge_key, edge_matches in edge_map.items()
        if len(edge_matches) == 1
    }


def _canonicalize_clipped_triangles_by_serialized_xy(
    triangles: Sequence[shapely.Polygon],
    output_fileformat: str,
) -> list[shapely.Polygon]:
    """Merge local clipped triangle vertices that will serialize to one XY."""
    canonical_xy_by_key: dict[tuple[float, float], tuple[float, float]] = {}
    duplicate_keys: set[tuple[float, float]] = set()

    for triangle in triangles:
        for coord in triangle.exterior.coords[:-1]:
            key = _serialized_xy_key(coord, output_fileformat)
            xy = (coord[0], coord[1])
            if key not in canonical_xy_by_key:
                canonical_xy_by_key[key] = xy
            elif canonical_xy_by_key[key] != xy:
                duplicate_keys.add(key)

    canonicalized: list[shapely.Polygon] = []
    for triangle in triangles:
        coords_2d: list[tuple[float, float]] = []
        for coord in triangle.exterior.coords[:-1]:
            key = _serialized_xy_key(coord, output_fileformat)
            if key in duplicate_keys:
                coords_2d.append(canonical_xy_by_key[key])
            else:
                coords_2d.append((coord[0], coord[1]))

        if len(coords_2d) != 3 or len(set(coords_2d)) < 3:
            continue
        coords_3d = [(coord[0], coord[1], 0.0) for coord in coords_2d]
        if triangle_xy_collapses_after_mesh_serialization(
            coords_3d,
            output_fileformat,
        ):
            continue

        canonical_triangle = shapely.Polygon([*coords_2d, coords_2d[0]])
        if canonical_triangle.is_empty or canonical_triangle.area <= 0:
            continue
        canonicalized.append(canonical_triangle)

    return canonicalized


def polygon_normalized_to_match_mesh_serialization(
    polygon: shapely.Polygon,
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    serialized_vertices: SerializedVertexCache | None = None,
) -> shapely.Polygon | None:
    """Return a serialized-coordinate polygon, or None if it collapses."""
    coords = polygon.exterior.coords
    if len(coords) != 4 or coords[0] != coords[-1]:
        raise ValueError("Expected a closed triangular Polygon.")

    def normalized_coord(coord: Coordinate) -> tuple[float, ...]:
        if (
            serialized_vertices is not None
            and decimals == MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION
        ):
            return _serialized_vertex_from_cache(
                coord,
                fileformat,
                serialized_vertices,
            )
        return normalize_vertex_to_match_mesh_serialization(
            coord=coord,
            fileformat=fileformat,
            decimals=decimals,
        )

    exterior = [
        normalized_coord(coord)
        for coord in coords[:3]
    ]
    exterior.append(exterior[0])
    interiors = [
        [
            normalized_coord(coord)
            for coord in ring.coords
        ]
        for ring in polygon.interiors
    ]
    if _serialized_triangle_collapses(
        (exterior[0], exterior[1], exterior[2]),
    ):
        return None
    return shapely.Polygon(exterior, interiors)


def surface_polygon_normalized_to_match_mesh_serialization(
    polygon: shapely.Polygon,
    fileformat: str,
    decimals: int = MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION,
    serialized_vertices: SerializedVertexCache | None = None,
) -> shapely.Polygon | None:
    """Return a serialized surface triangle, or None if it has no area."""
    normalized_polygon = polygon_normalized_to_match_mesh_serialization(
        polygon,
        fileformat,
        decimals,
        serialized_vertices,
    )
    if normalized_polygon is None:
        return None

    exterior = normalized_polygon.exterior.coords
    if _serialized_triangle_xy_collapses(
        triangle=(exterior[0], exterior[1], exterior[2]),
    ):
        return None
    return normalized_polygon


def quad_normalized_to_match_mesh_serialization(
    mesh: quad,
    fileformat: str,
    split_rotation: int,
    serialized_vertices: SerializedVertexCache | None = None,
) -> quad | None:
    """Return a serialized-coordinate quad, or None if it collapses."""
    if serialized_vertices is None:
        serialized_vertices = {}

    unique_vertices: list[vertex] = []
    unique_coords: set[tuple[float, ...]] = set()
    for mesh_vertex in mesh.vl:
        if mesh_vertex is None:
            continue

        output_coords = _serialized_vertex_from_cache(
            mesh_vertex.coords,
            fileformat,
            serialized_vertices,
        )
        if output_coords not in unique_coords:
            output_vertex = vertex(*output_coords)
            unique_vertices.append(output_vertex)
            unique_coords.add(output_coords)

    if len(unique_vertices) < 3:
        return None

    if len(unique_vertices) == 3:
        if _serialized_triangle_collapses(
            triangle=[v.coords for v in unique_vertices],
        ):
            return None
        return quad(unique_vertices[0], unique_vertices[1], unique_vertices[2])

    output_quad = quad(
        unique_vertices[0],
        unique_vertices[1],
        unique_vertices[2],
        unique_vertices[3],
        forced_split_edge=mesh.forced_split_edge,
    )
    valid_triangles: list[tuple[vertex, ...]] = []
    for triangle in output_quad.get_triangles(split_rotation=split_rotation):
        if not _serialized_triangle_collapses(
            triangle=[v.coords for v in triangle],
        ):
            valid_triangles.append(triangle)

    if len(valid_triangles) == 2:
        return output_quad
    if len(valid_triangles) == 1:
        triangle = valid_triangles[0]
        return quad(triangle[0], triangle[1], triangle[2])
    return None
