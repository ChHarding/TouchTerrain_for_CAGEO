"""Generate launch meshes and validate serialized STL topology."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _absolute_file(value: Any, cwd: Path) -> Any:
    """Resolve config file paths relative to the launch cwd."""
    if not isinstance(value, str) or not value:
        return value
    if re.match(r"^[a-zA-Z]+://", value):
        return value
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((cwd / path).resolve())


def _load_config(
    launch_item: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Load one launch config with paths resolved for generation."""
    cwd = Path(launch_item["cwd"])
    config_path = Path(launch_item["config_path"])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["config_path"] = str(config_path)
    config["CPU_cores_to_use"] = 1
    config["temp_folder"] = str(output_dir)
    config["zip_file_name"] = f"{config_path.stem}-topology-validation"

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


def _filtered_launch_items(
    validator: Any,
    mode: str,
    config_filters: list[str] | None,
) -> list[dict[str, Any]]:
    """Return launch configs selected by nudge mode and optional names."""
    launch_items = validator._launch_configs()
    if mode == "nudge":
        launch_items = [
            item
            for item in launch_items
            if Path(item["config_path"]).stem.endswith("-nudge")
        ]
    elif mode == "off":
        launch_items = [
            item
            for item in launch_items
            if not Path(item["config_path"]).stem.endswith("-nudge")
        ]

    if config_filters:
        filters = set(config_filters)
        launch_items = [
            item
            for item in launch_items
            if Path(item["config_path"]).name in filters
            or Path(item["config_path"]).stem in filters
        ]

    return launch_items


def _stl_xy_vertices_and_edges(
    validator: Any,
    stl_bytes: bytes,
) -> tuple[set[tuple[float, float]], set[tuple[tuple[float, float], ...]]]:
    """Return serialized XY vertices and triangle edges from one STL."""
    vertex_xy: set[tuple[float, float]] = set()
    edge_xy: set[tuple[tuple[float, float], ...]] = set()
    for triangle in validator._iter_binary_stl_triangles(stl_bytes):
        for index, coord0 in enumerate(triangle):
            vertex_xy.add(coord0[:2])
            coord1 = triangle[(index + 1) % 3]
            edge_xy.add(tuple(sorted((coord0[:2], coord1[:2]))))
    return vertex_xy, edge_xy


def _pa_pair_nudge_pair_checks(
    validator: Any,
    normal_stl_bytes: bytes,
    difference_stl_bytes: bytes,
) -> list[dict[str, Any]]:
    """Return PA pair-nudge normal/difference alignment checks."""
    normal_vertex_xy, normal_edge_xy = _stl_xy_vertices_and_edges(
        validator,
        normal_stl_bytes,
    )
    difference_vertex_xy, difference_edge_xy = _stl_xy_vertices_and_edges(
        validator,
        difference_stl_bytes,
    )

    def vertex_present_check(
        name: str,
        xy: tuple[float, float],
    ) -> dict[str, Any]:
        normal_present = xy in normal_vertex_xy
        difference_present = xy in difference_vertex_xy
        return {
            "name": name,
            "xy": xy,
            "normal_present": normal_present,
            "difference_present": difference_present,
            "passed": normal_present and difference_present,
        }

    def vertex_aligned_check(
        name: str,
        xy: tuple[float, float],
    ) -> dict[str, Any]:
        normal_present = xy in normal_vertex_xy
        difference_present = xy in difference_vertex_xy
        return {
            "name": name,
            "xy": xy,
            "normal_present": normal_present,
            "difference_present": difference_present,
            "passed": normal_present == difference_present,
        }

    def edge_present_check(
        name: str,
        xy0: tuple[float, float],
        xy1: tuple[float, float],
    ) -> dict[str, Any]:
        xy_edge = tuple(sorted((xy0, xy1)))
        normal_present = xy_edge in normal_edge_xy
        difference_present = xy_edge in difference_edge_xy
        return {
            "name": name,
            "xy_edge": xy_edge,
            "normal_present": normal_present,
            "difference_present": difference_present,
            "passed": normal_present and difference_present,
        }

    def edge_aligned_check(
        name: str,
        xy0: tuple[float, float],
        xy1: tuple[float, float],
    ) -> dict[str, Any]:
        xy_edge = tuple(sorted((xy0, xy1)))
        normal_present = xy_edge in normal_edge_xy
        difference_present = xy_edge in difference_edge_xy
        return {
            "name": name,
            "xy_edge": xy_edge,
            "normal_present": normal_present,
            "difference_present": difference_present,
            "passed": normal_present == difference_present,
        }

    checks = [
        vertex_present_check(
            "gap_vertex_present_in_pair",
            (50.200001, 50.299999),
        ),
        edge_aligned_check(
            "legacy_gap_edge_pair_aligned",
            (50.200001, 50.299999),
            (50.200001, 50.25),
        ),
        edge_present_check(
            "reported_gap_edge_present_in_pair",
            (50.200001, 50.299999),
            (50.099998, 50.200001),
        ),
        vertex_aligned_check(
            "three_corner_sw_pair_aligned",
            (49.400002, 37.200001),
        ),
        vertex_aligned_check(
            "three_corner_ne_pair_aligned",
            (49.5, 37.299999),
        ),
    ]
    return checks


def _generated_zip_path(config_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{config_path.stem}-topology-validation.zip"


def _load_or_generate_mesh(
    launch_item: dict[str, Any],
    output_dir: Path,
    reuse_dir: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return generation config and generated/reused zip metadata."""
    config_path = Path(launch_item["config_path"])
    config = _load_config(launch_item, output_dir)
    if reuse_dir is not None:
        zip_path = _generated_zip_path(config_path, reuse_dir)
        if not zip_path.exists():
            raise RuntimeError(f"Missing generated zip {zip_path}.")
        generation_log = reuse_dir / f"{config_path.stem}.generation.log"
        return config, {
            "zip": str(zip_path),
            "size_mb": zip_path.stat().st_size / 1024 / 1024,
            "generation_log": str(generation_log),
            "reused_generation": True,
        }

    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain

    generation_log = output_dir / f"{config_path.stem}.generation.log"
    with generation_log.open("w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(log_file):
            with contextlib.redirect_stderr(log_file):
                size_mb, zip_path = TouchTerrain.get_zipped_tiles(config)
    return config, {
        "zip": str(Path(zip_path)),
        "size_mb": size_mb,
        "generation_log": str(generation_log),
        "reused_generation": False,
    }


def _mesh_error_result(
    entry_name: str,
    output_path: Path | None,
    error: str,
) -> dict[str, Any]:
    return {
        "entry": entry_name,
        "mesh": str(output_path) if output_path is not None else None,
        "status": "failed",
        "error": error,
    }


def _log_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _config_progress_label(
    config_index: int,
    config_total: int,
    config_name: str,
) -> str:
    return f"[config {config_index}/{config_total}] {config_name}"


def _mesh_progress_label(
    config_label: str,
    mesh_index: int,
    mesh_total: int,
    entry_name: str,
) -> str:
    return f"{config_label} [mesh {mesh_index}/{mesh_total}] {entry_name}"


def _mesh_progress_callback(
    mesh_label: str,
) -> Callable[[int, int, float], None]:
    last_completed = 0

    def report(
        completed_triangles: int,
        total_triangles: int,
        elapsed_seconds: float,
    ) -> None:
        nonlocal last_completed
        if total_triangles <= 0 or completed_triangles <= last_completed:
            return
        last_completed = completed_triangles
        percent_complete = completed_triangles / total_triangles * 100
        _log_progress(
            f"{mesh_label}: validated "
            f"{completed_triangles:,}/{total_triangles:,} triangles "
            f"({percent_complete:.1f}%) in {elapsed_seconds:.1f}s"
        )

    return report


def _add_pa_pair_geometry_checks(
    validator: Any,
    result: dict[str, Any],
    pa_pair_stl_bytes: dict[str, bytes],
    pa_difference_mesh_result: dict[str, Any] | None,
) -> bool:
    """Attach PA-pair geometry checks and return whether any failed."""
    if {"normal", "difference"}.issubset(pa_pair_stl_bytes):
        checks = _pa_pair_nudge_pair_checks(
            validator,
            pa_pair_stl_bytes["normal"],
            pa_pair_stl_bytes["difference"],
        )
    else:
        checks = [
            {
                "name": "pa_pair_entries_present",
                "normal_present": "normal" in pa_pair_stl_bytes,
                "difference_present": "difference" in pa_pair_stl_bytes,
                "passed": False,
            }
        ]

    if pa_difference_mesh_result is not None:
        pa_difference_mesh_result["geometry_checks"] = checks
    else:
        result["geometry_checks"] = checks
    return any(not check["passed"] for check in checks)


def _set_topology_result_status(
    result: dict[str, Any],
    geometry_check_failed: bool,
    validator: Any,
) -> None:
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
        if meshes
        and result["total_boundary_edges"] == 0
        and result["total_overused_edges"] == 0
        and result["total_bad_oriented_edges"] == 0
        and not geometry_check_failed
        and not any(mesh.get("error") for mesh in meshes)
        and all(
            validator._mesh_stats_are_clean(mesh)
            for mesh in meshes
            if "triangles" in mesh
        )
        else "failed"
    )


def _validate_launch_item(
    validator: Any,
    launch_item: dict[str, Any],
    output_dir: Path,
    extract_dir: Path,
    reuse_dir: Path | None,
    mesh_workers: int,
    mesh_timeout_seconds: float | None,
    config_index: int,
    config_total: int,
) -> tuple[dict[str, Any], int]:
    """Generate and validate one launch config."""
    config_path = Path(launch_item["config_path"])
    generation_log = output_dir / f"{config_path.stem}.generation.log"
    config_label = _config_progress_label(
        config_index,
        config_total,
        config_path.name,
    )
    result: dict[str, Any] = {
        "config": config_path.name,
        "launch_name": launch_item["name"],
        "generation_log": str(generation_log),
    }
    failures = 0

    try:
        generation_started_at = time.monotonic()
        generation_action = (
            "reusing generated mesh" if reuse_dir else "generating mesh"
        )
        _log_progress(f"{config_label}: {generation_action}")
        config, generated = _load_or_generate_mesh(
            launch_item,
            output_dir,
            reuse_dir,
        )
        _log_progress(
            f"{config_label}: {generation_action} finished in "
            f"{time.monotonic() - generation_started_at:.1f}s"
        )
        zip_path = Path(generated["zip"])
        entries = validator._stl_entries(zip_path)
        config_extract_dir = extract_dir / config_path.stem
        config_extract_dir.mkdir(parents=True, exist_ok=True)
        result.update(
            {
                **generated,
                "pair_mode": bool(config.get("interlocking_mesh_pair")),
                "nudge": bool(config.get("nudge_in_overused_edges_vertex")),
                "extracted_meshes": str(config_extract_dir),
                "meshes": [],
            },
        )
        if not entries:
            result["meshes"].append(
                _mesh_error_result(
                    "<none>",
                    None,
                    "Generated zip contains no STL meshes.",
                )
            )

        is_pa_pair_nudge = config_path.stem == "PA-pair-nudge"
        pa_pair_stl_bytes: dict[str, bytes] = {}
        pa_difference_mesh_result: dict[str, Any] | None = None
        mesh_entries = list(entries.items())
        mesh_total = len(mesh_entries)
        for mesh_index, (entry_name, stl_bytes) in enumerate(mesh_entries, 1):
            output_path = config_extract_dir / Path(entry_name).name
            output_path.write_bytes(stl_bytes)
            mesh_label = _mesh_progress_label(
                config_label,
                mesh_index,
                mesh_total,
                entry_name,
            )
            mesh_result = {
                "entry": entry_name,
                "mesh": str(output_path),
            }
            mesh_started_at = time.monotonic()
            try:
                triangle_count = validator._binary_stl_triangle_count(
                    stl_bytes,
                )
                triangle_text = f"{triangle_count:,} triangles"
            except ValueError as exc:
                triangle_text = f"invalid triangle count: {exc}"
            _log_progress(
                f"{mesh_label}: validating {len(stl_bytes) / 1024 / 1024:.2f} "
                f"MB STL ({triangle_text})"
            )
            try:
                stats = validator._mesh_stats(
                    stl_bytes,
                    mesh_workers,
                    mesh_timeout_seconds,
                    progress_callback=_mesh_progress_callback(mesh_label),
                )
                mesh_result.update(stats)
            except validator.MeshValidationTimeoutError as exc:
                mesh_result.update(
                    _mesh_error_result(entry_name, output_path, str(exc))
                )
                result["meshes"].append(mesh_result)
                _log_progress(
                    f"{mesh_label}: validation timed out after "
                    f"{time.monotonic() - mesh_started_at:.1f}s"
                )
                continue
            if stats["triangles"] == 0:
                mesh_result["status"] = "failed"
                mesh_result["error"] = "STL mesh has no triangles."
            if is_pa_pair_nudge:
                entry_name_lower = entry_name.lower()
                if "normal" in entry_name_lower:
                    pa_pair_stl_bytes["normal"] = stl_bytes
                if "difference" in entry_name_lower:
                    pa_pair_stl_bytes["difference"] = stl_bytes
                    pa_difference_mesh_result = mesh_result
            result["meshes"].append(mesh_result)
            mesh_clean = validator._mesh_stats_are_clean(mesh_result)
            _log_progress(
                f"{mesh_label}: validation {'passed' if mesh_clean else 'failed'} "
                f"in {time.monotonic() - mesh_started_at:.1f}s "
                f"(boundary={mesh_result.get('boundary_edges', 0)}, "
                f"overused={mesh_result.get('overused_edges', 0)}, "
                f"bad_oriented={mesh_result.get('bad_oriented_edges', 0)})"
            )

        geometry_check_failed = (
            _add_pa_pair_geometry_checks(
                validator,
                result,
                pa_pair_stl_bytes,
                pa_difference_mesh_result,
            )
            if is_pa_pair_nudge
            else False
        )
        _set_topology_result_status(result, geometry_check_failed, validator)
        _log_progress(
            f"{config_label}: finished with status={result['status']} "
            f"(boundary={result.get('total_boundary_edges', 0)}, "
            f"overused={result.get('total_overused_edges', 0)}, "
            f"bad_oriented={result.get('total_bad_oriented_edges', 0)})"
        )
        if result["status"] != "ok":
            failures += 1
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        failures += 1
        _log_progress(f"{config_label}: failed: {exc}")

    return result, failures


def main() -> int:
    """Validate selected launch meshes for boundary and overused edges."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate launch meshes and validate serialized STL topology."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["all", "nudge", "off"],
        default="all",
        help="Select all launch configs, only *-nudge configs, or non-nudge.",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        help="Optional config file names or stems to validate.",
    )
    parser.add_argument(
        "--mesh-workers",
        type=int,
        default=1,
        help=(
            "Number of worker processes to use while validating each STL "
            "mesh. Use 0 for all available CPUs minus one."
        ),
    )
    parser.add_argument(
        "--mesh-timeout-seconds",
        type=float,
        default=0,
        help=(
            "Timeout for validating each emitted STL mesh. Use 0 to disable "
            "the per-mesh timeout."
        ),
    )
    parser.add_argument(
        "--reuse-dir",
        type=Path,
        help=(
            "Skip mesh generation and validate existing "
            "*-topology-validation.zip files from this output directory."
        ),
    )
    args = parser.parse_args()

    try:
        from tools import validate_launch_mesh_comparison as validator
    except Exception as exc:
        print(json.dumps({"error": f"import failed: {exc}"}))
        return 1

    run_id = str(int(time.time()))
    output_dir = ROOT / "tmp" / f"launch_topology_{args.mode}_{run_id}"
    extract_dir = (
        ROOT / "tmp" / f"launch_meshes_topology_{args.mode}_{run_id}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        launch_items = _filtered_launch_items(
            validator,
            args.mode,
            args.configs,
        )
    except Exception as exc:
        print(json.dumps({"error": f"setup failed: {exc}"}))
        return 1

    results: list[dict[str, Any]] = []
    failures = 0
    config_total = len(launch_items)
    for config_index, launch_item in enumerate(launch_items, 1):
        result, item_failures = _validate_launch_item(
            validator,
            launch_item,
            output_dir,
            extract_dir,
            args.reuse_dir.resolve() if args.reuse_dir is not None else None,
            args.mesh_workers,
            (
                args.mesh_timeout_seconds
                if args.mesh_timeout_seconds > 0
                else None
            ),
            config_index,
            config_total,
        )
        results.append(result)
        failures += item_failures

    report_path = output_dir / "validation_report.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    summary = {
        "report": str(report_path),
        "extracted_meshes": str(extract_dir),
        "configs": len(results),
        "mesh_workers": args.mesh_workers,
        "mesh_timeout_seconds": args.mesh_timeout_seconds,
        "reuse_dir": (
            str(args.reuse_dir.resolve())
            if args.reuse_dir is not None
            else None
        ),
        "failed_configs": sum(
            1 for item in results if item["status"] != "ok"
        ),
        "total_boundary_edges": sum(
            item.get("total_boundary_edges", 0) for item in results
        ),
        "total_overused_edges": sum(
            item.get("total_overused_edges", 0) for item in results
        ),
        "total_bad_oriented_edges": sum(
            item.get("total_bad_oriented_edges", 0) for item in results
        ),
        "failures": [
            {
                "config": item["config"],
                "boundary": item.get("total_boundary_edges", 0),
                "overused": item.get("total_overused_edges", 0),
                "bad_oriented": item.get("total_bad_oriented_edges", 0),
                "error": item.get("error"),
                "mesh_errors": [
                    {
                        "entry": mesh["entry"],
                        "mesh": mesh.get("mesh"),
                        "error": mesh.get("error"),
                    }
                    for mesh in item.get("meshes", [])
                    if mesh.get("error")
                ],
            }
            for item in results
            if item["status"] != "ok"
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
