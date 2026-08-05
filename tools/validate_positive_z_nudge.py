"""Generate the WV positive-Z fixture and validate STL edge topology."""

from __future__ import annotations

import contextlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "test" / "data" / "wv_new_river_nonmanifold_20mm"
CONFIG_PATH = FIXTURE_DIR / "WV-new-river-20mm-nudge.json"
OUTPUT_DIR = ROOT / "tmp" / "positive_z_validation"


Coordinate = tuple[float, float, float]
Edge = tuple[Coordinate, Coordinate]
TARGET_SHARED_XY = (8.0, 18.15)
TARGET_CELLS = {
    "initial": {
        "bounds": (8.1, 8.2, 18.2, 18.3),
        "expected_diagonal": "NW-SE",
    },
    "gap": {
        "bounds": (8.2, 8.3, 17.7, 17.8),
        "expected_diagonal": "SW-NE",
    },
}
CELL_TOLERANCE = 0.0002


def normalized_coord(coord: tuple[float, float, float]) -> Coordinate:
    """Return the serialized-coordinate key used for STL topology checks."""
    return tuple(round(float(value), 6) for value in coord)


def edge_key(coord0: Coordinate, coord1: Coordinate) -> Edge:
    """Return an orientation-independent 3D edge key."""
    return tuple(sorted((coord0, coord1)))


def binary_stl_triangles(stl_bytes: bytes) -> list[tuple[Coordinate, ...]]:
    """Parse triangles from a binary STL byte buffer."""
    if len(stl_bytes) < 84:
        raise ValueError("Binary STL is shorter than its header.")

    triangle_count = struct.unpack_from("<I", stl_bytes, 80)[0]
    expected_length = 84 + triangle_count * 50
    if len(stl_bytes) < expected_length:
        raise ValueError("Binary STL is truncated.")

    triangles: list[tuple[Coordinate, ...]] = []
    offset = 84
    for _ in range(triangle_count):
        values = struct.unpack_from("<12fH", stl_bytes, offset)
        triangles.append(
            (
                normalized_coord((values[3], values[4], values[5])),
                normalized_coord((values[6], values[7], values[8])),
                normalized_coord((values[9], values[10], values[11])),
            )
        )
        offset += 50
    return triangles


def count_edges(triangles: list[tuple[Coordinate, ...]]) -> Counter[Edge]:
    """Count all serialized 3D triangle edges."""
    edge_counts: Counter[Edge] = Counter()
    for triangle in triangles:
        for index, coord0 in enumerate(triangle):
            coord1 = triangle[(index + 1) % 3]
            edge_counts[edge_key(coord0, coord1)] += 1
    return edge_counts


def vertices_by_xy(
    triangles: list[tuple[Coordinate, ...]],
) -> dict[tuple[float, float], set[float]]:
    """Return serialized vertex Z values keyed by XY."""
    vertices: dict[tuple[float, float], set[float]] = {}
    for triangle in triangles:
        for coord in triangle:
            vertices.setdefault(coord[:2], set()).add(coord[2])
    return vertices


def triangle_xy_area(triangle: tuple[Coordinate, ...]) -> float:
    """Return XY footprint area for a triangle."""
    (x0, y0, _), (x1, y1, _), (x2, y2, _) = triangle
    return abs(
        (x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1)) / 2.0
    )


def coord_in_cell(coord: Coordinate, bounds: tuple[float, ...]) -> bool:
    """Return whether a coordinate is inside a cell footprint."""
    west, east, south, north = bounds
    return (
        west - CELL_TOLERANCE <= coord[0] <= east + CELL_TOLERANCE
        and south - CELL_TOLERANCE <= coord[1] <= north + CELL_TOLERANCE
    )


def snap_cell_xy(
    coord: Coordinate,
    bounds: tuple[float, ...],
) -> tuple[float, float]:
    """Snap serialized XY near a cell side to the exact side coordinate."""
    west, east, south, north = bounds
    x, y = coord[:2]
    snapped_x = (
        west
        if abs(x - west) < CELL_TOLERANCE
        else east
        if abs(x - east) < CELL_TOLERANCE
        else x
    )
    snapped_y = (
        south
        if abs(y - south) < CELL_TOLERANCE
        else north
        if abs(y - north) < CELL_TOLERANCE
        else y
    )
    return (round(snapped_x, 6), round(snapped_y, 6))


def diagonal_name(
    coord0: Coordinate,
    coord1: Coordinate,
    bounds: tuple[float, ...],
) -> str | None:
    """Return the named full-cell diagonal for an edge, if it is one."""
    west, east, south, north = bounds
    edge = tuple(
        sorted((snap_cell_xy(coord0, bounds), snap_cell_xy(coord1, bounds)))
    )
    if edge == tuple(sorted(((west, north), (east, south)))):
        return "NW-SE"
    if edge == tuple(sorted(((west, south), (east, north)))):
        return "SW-NE"
    return None


def target_cell_diagonals(
    triangles: list[tuple[Coordinate, ...]],
    bounds: tuple[float, ...],
    role: str,
) -> list[str]:
    """Return unique full-cell diagonals emitted for a target cell surface."""
    cell_triangles = [
        triangle
        for triangle in triangles
        if all(coord_in_cell(coord, bounds) for coord in triangle)
        and triangle_xy_area(triangle) > 1e-8
    ]
    if role == "normal":
        cell_triangles = [
            triangle
            for triangle in cell_triangles
            if max(coord[2] for coord in triangle) > 0.001
        ]

    diagonals: list[str] = []
    for triangle in cell_triangles:
        for index, coord0 in enumerate(triangle):
            coord1 = triangle[(index + 1) % len(triangle)]
            diagonal = diagonal_name(coord0, coord1, bounds)
            if diagonal is not None and diagonal not in diagonals:
                diagonals.append(diagonal)
    return diagonals


def target_cell_checks(
    triangles_by_role: dict[str, list[tuple[Coordinate, ...]]],
) -> list[dict[str, object]]:
    """Return pass/fail records for WV regression-cell diagonals."""
    checks: list[dict[str, object]] = []
    for name, target in TARGET_CELLS.items():
        bounds = target["bounds"]
        expected = target["expected_diagonal"]
        observed = {
            role: target_cell_diagonals(triangles, bounds, role)
            for role, triangles in triangles_by_role.items()
        }
        checks.append(
            {
                "name": name,
                "bounds": bounds,
                "expected_diagonal": expected,
                "observed_diagonals": observed,
                "passed": all(
                    observed.get(role) == [expected]
                    for role in ("normal", "difference")
                ),
            }
        )
    return checks


def load_config() -> dict:
    """Load the fixture config and make file paths absolute."""
    config = json.loads(CONFIG_PATH.read_text())
    config["CPU_cores_to_use"] = 1
    config["nudge_in_overused_edges_vertex"] = True
    config["split_rotation"] = 2
    config["interlocking_mesh_pair"] = True
    config["top_elevation_hint"] = None
    config["temp_folder"] = str(OUTPUT_DIR)
    config["zip_file_name"] = "WV-new-river-20mm-positive-z-validation"
    config["importedDEM"] = str(FIXTURE_DIR / config["importedDEM"])
    config["bottom_elevation"] = str(FIXTURE_DIR / config["bottom_elevation"])
    return config


def generate_zip(config: dict) -> Path:
    """Generate the fixture zip while capturing TouchTerrain output."""
    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generation_log = OUTPUT_DIR / "generation_output.log"
    with generation_log.open("w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(
            log_file,
        ):
            _, zip_path = TouchTerrain.get_zipped_tiles(config)
    return Path(zip_path)


def stls_from_zip(zip_path: Path) -> dict[str, bytes]:
    """Return all STL entries and extract them for manual inspection."""
    entries: dict[str, bytes] = {}
    with ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            if name.lower().endswith(".stl"):
                stl_bytes = archive.read(name)
                entries[name] = stl_bytes
                (OUTPUT_DIR / Path(name).name).write_bytes(stl_bytes)
    if not entries:
        raise ValueError(f"No STL file found in {zip_path}.")
    return entries


def main() -> int:
    try:
        config = load_config()
        zip_path = generate_zip(config)
        stl_entries = stls_from_zip(zip_path)
    except Exception as exc:
        print(f"validation failed: {exc}")
        print(f"captured generation log: {OUTPUT_DIR / 'generation_output.log'}")
        return 1

    meshes = []
    triangles_by_role: dict[str, list[tuple[Coordinate, ...]]] = {}
    vertices_by_role: dict[str, dict[tuple[float, float], set[float]]] = {}
    failed = False
    for stl_name, stl_bytes in sorted(stl_entries.items()):
        triangles = binary_stl_triangles(stl_bytes)
        lower_name = stl_name.lower()
        if "_normal" in lower_name:
            triangles_by_role["normal"] = triangles
            vertices_by_role["normal"] = vertices_by_xy(triangles)
        elif "_difference" in lower_name:
            triangles_by_role["difference"] = triangles
            vertices_by_role["difference"] = vertices_by_xy(triangles)
        edge_counts = count_edges(triangles)
        boundary_edges = [
            edge for edge, count in edge_counts.items() if count == 1
        ]
        overused_edges = {
            edge: count
            for edge, count in edge_counts.items()
            if count > 2
        }
        positive_overused_edges = {
            edge: count
            for edge, count in overused_edges.items()
            if edge[0][2] > 0 and edge[1][2] > 0
        }
        meshes.append(
            {
                "stl": stl_name,
                "triangles": len(triangles),
                "boundary_edges": len(boundary_edges),
                "overused_edges": len(overused_edges),
                "positive_overused_edges": len(positive_overused_edges),
            }
        )
        failed = failed or bool(boundary_edges or positive_overused_edges)

    normal_target_z = vertices_by_role.get("normal", {}).get(
        TARGET_SHARED_XY,
        set(),
    )
    difference_target_z = vertices_by_role.get("difference", {}).get(
        TARGET_SHARED_XY,
        set(),
    )
    target_shared_z = sorted(normal_target_z & difference_target_z)
    shared_vertex_check = {
        "xy": TARGET_SHARED_XY,
        "normal_z": sorted(normal_target_z),
        "difference_z": sorted(difference_target_z),
        "shared_z": target_shared_z,
        "passed": bool(target_shared_z),
    }
    cell_checks = target_cell_checks(triangles_by_role)
    failed = failed or any(not check["passed"] for check in cell_checks)

    report = {
        "zip": str(zip_path),
        "split_rotation": config.get("split_rotation"),
        "meshes": meshes,
        "target_cell_diagonals": cell_checks,
        "target_shared_vertex_info": shared_vertex_check,
    }
    report_path = OUTPUT_DIR / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if failed:
        print(f"validation report: {report_path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
