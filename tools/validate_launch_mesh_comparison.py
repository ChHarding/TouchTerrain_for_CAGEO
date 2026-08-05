"""Validate current launch meshes against the previous launch mesh baseline."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import multiprocessing
import os
import re
import struct
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from multiprocessing import shared_memory
from pathlib import Path
from typing import Any
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "tmp" / "wall_split_mesh_validation_1780346335"
BASELINE_REPORT = BASELINE_DIR / "validation_report.json"
RUN_ID = str(int(time.time()))
OUTPUT_DIR = ROOT / "tmp" / f"positive_z_launch_validation_{RUN_ID}"
EXTRACT_DIR = ROOT / "tmp" / f"launch_meshes_positive_z_validation_{RUN_ID}"
SERIALIZATION_DECIMALS = 6
SERIALIZATION_SCALE = 10**SERIALIZATION_DECIMALS
MIN_TRIANGLES_PER_MESH_WORKER = 100_000

Coordinate = tuple[float, float, float]
Edge = tuple[Coordinate, Coordinate]
CoordinateKey = tuple[int, int, int]
EdgeKey = tuple[CoordinateKey, CoordinateKey]
ProgressCallback = Callable[[int, int, float], None]


@dataclass
class EdgeUsage:
    """Edge-use counters collected from one STL triangle range."""

    triangle_count: int
    edge_counts: Counter[EdgeKey]
    edge_orientation_balance: Counter[EdgeKey]


class MeshValidationTimeoutError(TimeoutError):
    """Raised when validating one STL mesh exceeds its timeout."""


def _read_launch_json() -> dict[str, Any]:
    """Read VS Code launch.json with comments and trailing commas."""
    text = (ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8")
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        output.append(char)
        index += 1

    text = "".join(output)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def _resolve_workspace_path(raw_path: str, cwd: Path | None = None) -> Path:
    path_text = raw_path.replace("${workspaceFolder}", str(ROOT))
    path = Path(path_text)
    if path.is_absolute():
        return path.resolve()
    if cwd is None:
        cwd = ROOT
    return (cwd / path).resolve()


def _launch_configs() -> list[dict[str, Any]]:
    launch = _read_launch_json()
    configs: list[dict[str, Any]] = []
    for item in launch["configurations"]:
        raw_args = item.get("args")
        if isinstance(raw_args, str):
            config_arg = raw_args
        elif isinstance(raw_args, list) and raw_args:
            config_arg = raw_args[0]
        else:
            continue
        cwd = _resolve_workspace_path(item["cwd"])
        configs.append(
            {
                "name": item["name"],
                "cwd": str(cwd),
                "config_path": str(_resolve_workspace_path(config_arg, cwd)),
            }
        )
    return configs


def _absolute_file(value: Any, cwd: Path) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if re.match(r"^[a-zA-Z]+://", value):
        return value
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((cwd / path).resolve())


def _load_generation_config(
    launch_item: dict[str, Any],
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    cwd = Path(launch_item["cwd"])
    config_path = Path(launch_item["config_path"])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["config_path"] = str(config_path)
    config["CPU_cores_to_use"] = 1
    config["nudge_in_overused_edges_vertex"] = True
    if (
        config.get("bottom_elevation") is not None
        and not config.get("bottom_thru_base")
    ):
        config["interlocking_mesh_pair"] = True
        config["top_elevation_hint"] = None
    config["temp_folder"] = str(output_dir)
    config["zip_file_name"] = f"{config_path.stem}-positive-z-validation"

    for key in (
        "importedDEM",
        "importedDEM_interp",
        "bottom_elevation",
        "top_elevation_hint",
        "edge_clipping_polygon",
        "poly_file",
    ):
        config[key] = _absolute_file(config.get(key), cwd)

    if config.get("offset_masks_lower"):
        for offset_pair in config["offset_masks_lower"]:
            offset_pair[0] = _absolute_file(offset_pair[0], cwd)

    return config


def _normalized_coord(coord: tuple[float, float, float]) -> Coordinate:
    return tuple(round(float(value), SERIALIZATION_DECIMALS) for value in coord)


def _normalized_coord_key(coord: tuple[float, float, float]) -> CoordinateKey:
    return tuple(
        int(round(float(value) * SERIALIZATION_SCALE)) for value in coord
    )


def _coord_from_key(coord: CoordinateKey) -> Coordinate:
    return tuple(value / SERIALIZATION_SCALE for value in coord)


def _edge_from_key(edge: EdgeKey) -> Edge:
    return (_coord_from_key(edge[0]), _coord_from_key(edge[1]))


def _edge_key(coord0: CoordinateKey, coord1: CoordinateKey) -> EdgeKey:
    return tuple(sorted((coord0, coord1)))


def _edge_orientation_balance(
    edge: EdgeKey,
    coord0: CoordinateKey,
    coord1: CoordinateKey,
) -> int:
    """Return +1 for canonical edge direction and -1 for reverse."""
    return 1 if (coord0, coord1) == edge else -1


def _edge_z_class(edge: EdgeKey) -> str:
    z0 = edge[0][2]
    z1 = edge[1][2]
    if z0 == 0 and z1 == 0:
        return "z0"
    if z0 > 0 and z1 > 0:
        return "positive_z"
    return "mixed_z"


def _binary_stl_triangle_count(stl_bytes: bytes) -> int:
    if len(stl_bytes) < 84:
        raise ValueError("Binary STL is shorter than its header.")
    triangle_count = struct.unpack_from("<I", stl_bytes, 80)[0]
    expected_length = 84 + triangle_count * 50
    if len(stl_bytes) < expected_length:
        raise ValueError("Binary STL is truncated.")
    return triangle_count


def _iter_binary_stl_triangle_range(
    stl_buffer: bytes | memoryview,
    start_triangle: int,
    stop_triangle: int,
) -> Iterator[tuple[Coordinate, ...]]:
    offset = 84 + start_triangle * 50
    for _ in range(start_triangle, stop_triangle):
        values = struct.unpack_from("<12fH", stl_buffer, offset)
        yield (
            _normalized_coord((values[3], values[4], values[5])),
            _normalized_coord((values[6], values[7], values[8])),
            _normalized_coord((values[9], values[10], values[11])),
        )
        offset += 50


def _iter_binary_stl_triangles(
    stl_bytes: bytes,
) -> Iterator[tuple[Coordinate, ...]]:
    triangle_count = _binary_stl_triangle_count(stl_bytes)
    yield from _iter_binary_stl_triangle_range(
        stl_bytes,
        0,
        triangle_count,
    )


def _count_stl_edge_usage_range(
    stl_buffer: bytes | memoryview,
    start_triangle: int,
    stop_triangle: int,
    deadline: float | None = None,
    progress_interval_triangles: int = 0,
    progress_callback: Callable[[int], None] | None = None,
) -> EdgeUsage:
    edge_counts: Counter[EdgeKey] = Counter()
    edge_orientation_balance: Counter[EdgeKey] = Counter()
    triangle_count = 0
    last_progress_triangle = 0
    offset = 84 + start_triangle * 50
    for triangle_index in range(start_triangle, stop_triangle):
        if (
            deadline is not None
            and triangle_index % 10_000 == 0
        ):
            _raise_if_deadline_expired(deadline)
        values = struct.unpack_from("<12fH", stl_buffer, offset)
        triangle = (
            _normalized_coord_key((values[3], values[4], values[5])),
            _normalized_coord_key((values[6], values[7], values[8])),
            _normalized_coord_key((values[9], values[10], values[11])),
        )
        triangle_count += 1
        for index, coord0 in enumerate(triangle):
            coord1 = triangle[(index + 1) % 3]
            edge = _edge_key(coord0, coord1)
            edge_counts[edge] += 1
            edge_orientation_balance[edge] += _edge_orientation_balance(
                edge,
                coord0,
                coord1,
            )
        offset += 50
        if (
            progress_callback is not None
            and progress_interval_triangles > 0
            and triangle_count % progress_interval_triangles == 0
        ):
            progress_callback(triangle_count)
            last_progress_triangle = triangle_count
    if (
        progress_callback is not None
        and triangle_count
        and triangle_count != last_progress_triangle
    ):
        progress_callback(triangle_count)
    return EdgeUsage(
        triangle_count,
        edge_counts,
        edge_orientation_balance,
    )


def _count_stl_edge_usage_shared(
    args: tuple[str, int, int, float | None],
) -> EdgeUsage:
    shared_memory_name, start_triangle, stop_triangle, deadline = args
    stl_memory = shared_memory.SharedMemory(name=shared_memory_name)
    stl_buffer = stl_memory.buf
    try:
        return _count_stl_edge_usage_range(
            stl_buffer,
            start_triangle,
            stop_triangle,
            deadline,
        )
    finally:
        del stl_buffer
        stl_memory.close()


def _deadline_from_timeout(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None or timeout_seconds <= 0:
        return None
    return time.monotonic() + timeout_seconds


def _raise_if_deadline_expired(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise MeshValidationTimeoutError("Mesh validation timed out.")


def _mesh_worker_count(
    requested_workers: int,
    triangle_count: int,
) -> int:
    if triangle_count <= 0 or requested_workers == 1:
        return 1
    if triangle_count < MIN_TRIANGLES_PER_MESH_WORKER:
        return 1
    if requested_workers == 0:
        requested_workers = max((os.cpu_count() or 1) - 1, 1)
    requested_workers = max(requested_workers, 1)
    useful_workers = max(
        triangle_count // MIN_TRIANGLES_PER_MESH_WORKER,
        1,
    )
    return min(requested_workers, useful_workers, triangle_count)


def _triangle_ranges(
    triangle_count: int,
    workers: int,
) -> list[tuple[int, int]]:
    chunk_count = max(
        workers,
        (triangle_count + MIN_TRIANGLES_PER_MESH_WORKER - 1)
        // MIN_TRIANGLES_PER_MESH_WORKER,
    )
    chunk_count = min(chunk_count, triangle_count)
    base_count = triangle_count // chunk_count
    remainder = triangle_count % chunk_count
    ranges: list[tuple[int, int]] = []
    start = 0
    for chunk_index in range(chunk_count):
        count = base_count + (1 if chunk_index < remainder else 0)
        stop = start + count
        if start < stop:
            ranges.append((start, stop))
        start = stop
    return ranges


def _merge_edge_usage_into(
    target: EdgeUsage,
    source: EdgeUsage,
) -> EdgeUsage:
    target.triangle_count += source.triangle_count
    target.edge_counts.update(source.edge_counts)
    for edge, balance in source.edge_orientation_balance.items():
        target.edge_orientation_balance[edge] += balance
    return target


def _next_edge_usage_chunk(
    iterator: Any,
    pool: multiprocessing.pool.Pool,
    deadline: float | None,
) -> EdgeUsage:
    if deadline is None:
        return next(iterator)

    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds <= 0:
        pool.terminate()
        raise MeshValidationTimeoutError("Mesh validation timed out.")
    try:
        return iterator.next(remaining_seconds)
    except multiprocessing.TimeoutError as exc:
        pool.terminate()
        raise MeshValidationTimeoutError("Mesh validation timed out.") from exc


def _report_mesh_progress(
    progress_callback: ProgressCallback | None,
    completed_triangles: int,
    total_triangles: int,
    started_at: float,
) -> None:
    if progress_callback is not None:
        progress_callback(
            completed_triangles,
            total_triangles,
            time.monotonic() - started_at,
        )


def _count_stl_edge_usage(
    stl_bytes: bytes,
    mesh_workers: int = 1,
    timeout_seconds: float | None = None,
    progress_callback: ProgressCallback | None = None,
) -> EdgeUsage:
    deadline = _deadline_from_timeout(timeout_seconds)
    triangle_count = _binary_stl_triangle_count(stl_bytes)
    started_at = time.monotonic()
    workers = _mesh_worker_count(mesh_workers, triangle_count)
    if workers == 1:
        def report_single_worker_progress(completed: int) -> None:
            _report_mesh_progress(
                progress_callback,
                completed,
                triangle_count,
                started_at,
            )

        return _count_stl_edge_usage_range(
            stl_bytes,
            0,
            triangle_count,
            deadline,
            MIN_TRIANGLES_PER_MESH_WORKER,
            report_single_worker_progress,
        )

    stl_memory = shared_memory.SharedMemory(
        create=True,
        size=len(stl_bytes),
    )
    try:
        stl_memory.buf[: len(stl_bytes)] = stl_bytes
        ranges = _triangle_ranges(triangle_count, workers)
        worker_args = [
            (stl_memory.name, start_triangle, stop_triangle, deadline)
            for start_triangle, stop_triangle in ranges
        ]
        context = multiprocessing.get_context("spawn")
        with context.Pool(processes=workers) as pool:
            usage = EdgeUsage(0, Counter(), Counter())
            iterator = pool.imap_unordered(
                _count_stl_edge_usage_shared,
                worker_args,
            )
            while usage.triangle_count < triangle_count:
                chunk_usage = _next_edge_usage_chunk(
                    iterator,
                    pool,
                    deadline,
                )
                usage = _merge_edge_usage_into(usage, chunk_usage)
                _report_mesh_progress(
                    progress_callback,
                    usage.triangle_count,
                    triangle_count,
                    started_at,
                )
            return usage
    finally:
        stl_memory.close()
        stl_memory.unlink()


def _mesh_stats(
    stl_bytes: bytes,
    mesh_workers: int = 1,
    timeout_seconds: float | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    usage = _count_stl_edge_usage(
        stl_bytes,
        mesh_workers,
        timeout_seconds,
        progress_callback,
    )

    boundary_by_z_class: Counter[str] = Counter()
    overused_by_z_class: Counter[str] = Counter()
    first_overused_edges: list[EdgeKey] = []
    first_bad_oriented_edges: list[EdgeKey] = []
    boundary_edges = 0
    overused_edges = 0
    bad_oriented_edges = 0
    max_edge_use = 0
    for edge, count in usage.edge_counts.items():
        max_edge_use = max(max_edge_use, count)
        if count == 1:
            boundary_edges += 1
            boundary_by_z_class[_edge_z_class(edge)] += 1
        elif count > 2:
            overused_edges += 1
            overused_by_z_class[_edge_z_class(edge)] += 1
            if len(first_overused_edges) < 5:
                first_overused_edges.append(edge)
        elif count == 2:
            if usage.edge_orientation_balance[edge] != 0:
                bad_oriented_edges += 1
                if len(first_bad_oriented_edges) < 5:
                    first_bad_oriented_edges.append(edge)

    return {
        "triangles": usage.triangle_count,
        "boundary_edges": boundary_edges,
        "boundary_by_z_class": dict(boundary_by_z_class),
        "overused_edges": overused_edges,
        "overused_by_z_class": dict(overused_by_z_class),
        "bad_oriented_edges": bad_oriented_edges,
        "max_edge_use": max_edge_use,
        "first_overused_edges": [
            _edge_from_key(edge) for edge in first_overused_edges
        ],
        "first_bad_oriented_edges": [
            _edge_from_key(edge) for edge in first_bad_oriented_edges
        ],
    }


def _mesh_stats_are_clean(stats: dict[str, Any]) -> bool:
    return (
        stats.get("triangles", 0) > 0
        and stats.get("boundary_edges", 0) == 0
        and stats.get("overused_edges", 0) == 0
        and stats.get("bad_oriented_edges", 0) == 0
    )


def _mesh_failure_result(
    entry_name: str,
    comparison_status: str,
    error: str,
    baseline_entry: str | None = None,
) -> dict[str, Any]:
    return {
        "entry": entry_name,
        "baseline_entry": baseline_entry,
        "comparison_status": comparison_status,
        "comparison_ok": False,
        "error": error,
    }


def _mesh_timeout_result(
    entry_name: str,
    exc: MeshValidationTimeoutError,
    baseline_entry: str | None = None,
) -> dict[str, Any]:
    return _mesh_failure_result(
        entry_name,
        "mesh_timeout",
        str(exc),
        baseline_entry,
    )


def _stl_entries(zip_path: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    with ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            if name.lower().endswith(".stl"):
                entries[name] = archive.read(name)
    return entries


def _baseline_by_config() -> dict[str, dict[str, Any]]:
    report = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    return {Path(item["config"]).name: item for item in report}


def _generate_mesh(
    launch_item: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain

    config_path = Path(launch_item["config_path"])
    config_name = config_path.name
    generation_log = output_dir / f"{config_path.stem}.generation.log"
    config = _load_generation_config(launch_item, output_dir)
    with generation_log.open("w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(
            log_file,
        ):
            size_mb, zip_path = TouchTerrain.get_zipped_tiles(config)
    return {
        "config": config_name,
        "zip": str(Path(zip_path)),
        "size_mb": size_mb,
        "generation_log": str(generation_log),
        "pair_mode": bool(config.get("interlocking_mesh_pair")),
    }


def _reuse_mesh(launch_item: dict[str, Any], reuse_dir: Path) -> dict[str, Any]:
    config_path = Path(launch_item["config_path"])
    zip_path = reuse_dir / f"{config_path.stem}-positive-z-validation.zip"
    if not zip_path.exists():
        raise RuntimeError(f"Missing generated zip {zip_path}.")
    return {
        "config": config_path.name,
        "zip": str(zip_path),
        "size_mb": zip_path.stat().st_size / 1024 / 1024,
        "generation_log": str(reuse_dir / f"{config_path.stem}.generation.log"),
        "pair_mode": bool(
            _load_generation_config(launch_item, reuse_dir).get(
                "interlocking_mesh_pair",
            ),
        ),
    }


def _extract_current_meshes(
    config_stem: str,
    entries: dict[str, bytes],
    extract_dir: Path,
) -> None:
    for entry_name, stl_bytes in entries.items():
        output_name = (
            f"{config_stem}-positive-z-validation__"
            f"{Path(entry_name).name}"
        )
        (extract_dir / output_name).write_bytes(stl_bytes)


def _paired_entry_names(
    current_entries: dict[str, bytes],
    baseline_entries: dict[str, bytes],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    if set(current_entries) == set(baseline_entries):
        return [(entry, entry) for entry in sorted(current_entries)], []
    if len(current_entries) == 1 and len(baseline_entries) == 1:
        return [
            (
                next(iter(current_entries)),
                next(iter(baseline_entries)),
            )
        ], []

    pairs: list[tuple[str, str]] = []
    failures: list[dict[str, Any]] = []
    for entry in sorted(set(current_entries) - set(baseline_entries)):
        failures.append(
            {
                "entry": entry,
                "comparison_status": "missing_baseline",
                "comparison_ok": False,
            }
        )
    for entry in sorted(set(baseline_entries) - set(current_entries)):
        failures.append(
            {
                "entry": entry,
                "comparison_status": "missing_current",
                "comparison_ok": False,
            }
        )
    for entry in sorted(set(current_entries) & set(baseline_entries)):
        pairs.append((entry, entry))
    return pairs, failures


def _compare_mesh(
    current_bytes: bytes,
    baseline_bytes: bytes,
    baseline_stats: dict[str, Any],
    mesh_workers: int = 1,
    mesh_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    current_stats = _mesh_stats(
        current_bytes,
        mesh_workers,
        mesh_timeout_seconds,
    )
    baseline_positive_overused = baseline_stats.get(
        "overused_by_z_class",
        {},
    ).get("positive_z", 0)
    byte_equal = (
        hashlib.sha256(current_bytes).hexdigest()
        == hashlib.sha256(baseline_bytes).hexdigest()
    )
    changed_expected = baseline_positive_overused > 0

    if changed_expected:
        ok = _mesh_stats_are_clean(current_stats)
        status = "changed_allowed" if ok and not byte_equal else "failed"
    else:
        ok = byte_equal and _mesh_stats_are_clean(current_stats)
        status = "unchanged" if ok else "unexpected_changed"

    return {
        **current_stats,
        "baseline_triangles": baseline_stats["triangles"],
        "triangle_delta": current_stats["triangles"]
        - baseline_stats["triangles"],
        "baseline_positive_overused_edges": baseline_positive_overused,
        "byte_equal_to_baseline": byte_equal,
        "comparison_status": status,
        "comparison_ok": ok,
    }


def _set_result_status(result: dict[str, Any]) -> None:
    meshes = result.get("meshes", [])
    result["total_boundary_edges"] = sum(
        mesh.get("boundary_edges", 0) for mesh in meshes
    )
    result["total_overused_edges"] = sum(
        mesh.get("overused_edges", 0) for mesh in meshes
    )
    result["total_bad_oriented_edges"] = sum(
        mesh.get("bad_oriented_edges", 0) for mesh in meshes
    )
    result["status"] = (
        "ok"
        if meshes and all(mesh["comparison_ok"] for mesh in meshes)
        else "failed"
    )


def _validate_launch_item(
    launch_item: dict[str, Any],
    baseline: dict[str, Any] | None,
    reuse_dir: Path | None,
    output_dir: Path,
    extract_dir: Path,
    mesh_workers: int,
    mesh_timeout_seconds: float | None,
) -> tuple[dict[str, Any], int]:
    """Validate one launch config and return its result plus failure count."""
    config_name = Path(launch_item["config_path"]).name
    result: dict[str, Any] = {
        "config": config_name,
        "launch_name": launch_item["name"],
    }
    failures = 0

    try:
        if baseline is None:
            raise RuntimeError(f"Missing baseline for {config_name}.")

        generated = (
            _reuse_mesh(launch_item, reuse_dir)
            if reuse_dir is not None
            else _generate_mesh(launch_item, output_dir)
        )
        result.update(generated)
        current_zip = Path(generated["zip"])
        current_entries = _stl_entries(current_zip)
        _extract_current_meshes(current_zip.stem, current_entries, extract_dir)

        result["meshes"] = []
        if not current_entries:
            result["meshes"].append(
                _mesh_failure_result(
                    "<none>",
                    "missing_current",
                    "Generated zip contains no STL meshes.",
                )
            )
            failures += 1
            _set_result_status(result)
            return result, failures

        if generated.get("pair_mode"):
            for current_entry, current_bytes in sorted(
                current_entries.items(),
            ):
                mesh_result: dict[str, Any] = {
                    "entry": current_entry,
                    "baseline_entry": None,
                }
                try:
                    current_stats = _mesh_stats(
                        current_bytes,
                        mesh_workers,
                        mesh_timeout_seconds,
                    )
                except MeshValidationTimeoutError as exc:
                    mesh_result.update(_mesh_timeout_result(current_entry, exc))
                    failures += 1
                    result["meshes"].append(mesh_result)
                    continue
                ok = _mesh_stats_are_clean(current_stats)
                mesh_result.update(
                    {
                        **current_stats,
                        "comparison_status": (
                            "pair_topology_ok" if ok else "failed"
                        ),
                        "comparison_ok": ok,
                    }
                )
                if not ok:
                    failures += 1
                result["meshes"].append(mesh_result)

            _set_result_status(result)
            return result, failures

        baseline_entries = _stl_entries(Path(baseline["zip"]))
        baseline_stats_by_entry = {
            mesh["entry"]: mesh for mesh in baseline["meshes"]
        }
        entry_pairs, entry_failures = _paired_entry_names(
            current_entries,
            baseline_entries,
        )
        for entry_failure in entry_failures:
            result["meshes"].append(entry_failure)
            failures += 1
        for current_entry, baseline_entry in entry_pairs:
            mesh_result = {
                "entry": current_entry,
                "baseline_entry": baseline_entry,
            }
            try:
                mesh_result.update(
                    _compare_mesh(
                        current_entries[current_entry],
                        baseline_entries[baseline_entry],
                        baseline_stats_by_entry[baseline_entry],
                        mesh_workers,
                        mesh_timeout_seconds,
                    )
                )
            except MeshValidationTimeoutError as exc:
                mesh_result.update(
                    _mesh_timeout_result(current_entry, exc, baseline_entry)
                )
            if not mesh_result["comparison_ok"]:
                failures += 1
            result["meshes"].append(mesh_result)

        _set_result_status(result)
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        failures += 1

    return result, failures


def run_validation(
    reuse_dir: Path | None = None,
    config_filter: set[str] | None = None,
    mesh_workers: int = 1,
    mesh_timeout_seconds: float | None = None,
    output_dir: Path = OUTPUT_DIR,
    extract_dir: Path = EXTRACT_DIR,
) -> tuple[list[dict[str, Any]], int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    baseline_items = _baseline_by_config()

    launch_items = [
        item
        for item in _launch_configs()
        if config_filter is None
        or Path(item["config_path"]).name in config_filter
    ]

    results: list[dict[str, Any]] = []
    failures = 0
    for launch_item in launch_items:
        result, item_failures = _validate_launch_item(
            launch_item,
            baseline_items.get(Path(launch_item["config_path"]).name),
            reuse_dir,
            output_dir,
            extract_dir,
            mesh_workers,
            mesh_timeout_seconds,
        )
        results.append(result)
        failures += item_failures

    return results, failures


def main() -> int:
    try:
        parser = argparse.ArgumentParser(
            description=(
                "Generate launch meshes and compare them with the previous "
                "launch validation baseline."
            ),
        )
        parser.add_argument(
            "reuse_dir",
            nargs="?",
            type=Path,
            help="Reuse an existing validation output directory instead of generating.",
        )
        parser.add_argument(
            "--configs",
            nargs="+",
            help="Optional config file names to validate, such as IP-water.json.",
        )
        parser.add_argument(
            "--mesh-workers",
            type=int,
            default=1,
            help=(
                "Number of worker processes to use while validating each "
                "STL mesh. Use 0 for all available CPUs minus one."
            ),
        )
        parser.add_argument(
            "--mesh-timeout-seconds",
            type=float,
            default=0,
            help=(
                "Timeout for validating each STL mesh. Use 0 to disable the "
                "per-mesh timeout."
            ),
        )
        args = parser.parse_args()
        results, failures = run_validation(
            args.reuse_dir.resolve() if args.reuse_dir is not None else None,
            set(args.configs) if args.configs else None,
            args.mesh_workers,
            (
                args.mesh_timeout_seconds
                if args.mesh_timeout_seconds > 0
                else None
            ),
        )
    except Exception as exc:
        print(f"validation setup failed: {exc}")
        return 1

    report_path = OUTPUT_DIR / "validation_report.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    summary = {
        "report": str(report_path),
        "extracted_meshes": str(EXTRACT_DIR),
        "configs": len(results),
        "mesh_workers": args.mesh_workers,
        "mesh_timeout_seconds": args.mesh_timeout_seconds,
        "failed_configs": sum(1 for item in results if item["status"] != "ok"),
        "comparison_failures": failures,
        "total_boundary_edges": sum(
            item.get("total_boundary_edges", 0) for item in results
        ),
        "total_overused_edges": sum(
            item.get("total_overused_edges", 0) for item in results
        ),
        "total_bad_oriented_edges": sum(
            item.get("total_bad_oriented_edges", 0) for item in results
        ),
        "changed_allowed": [
            {
                "config": item["config"],
                "entry": mesh["entry"],
                "triangle_delta": mesh["triangle_delta"],
                "baseline_positive_overused_edges": (
                    mesh["baseline_positive_overused_edges"]
                ),
            }
            for item in results
            for mesh in item.get("meshes", [])
            if mesh.get("comparison_status") == "changed_allowed"
        ],
        "unexpected_changes": [
            {
                "config": item["config"],
                "entry": mesh["entry"],
                "status": mesh.get("comparison_status", "failed"),
                "boundary": mesh.get("boundary_edges", 0),
                "overused": mesh.get("overused_edges", 0),
                "bad_oriented": mesh.get("bad_oriented_edges", 0),
            }
            for item in results
            for mesh in item.get("meshes", [])
            if mesh.get("comparison_status") not in (
                "unchanged",
                "changed_allowed",
                "pair_topology_ok",
            )
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
