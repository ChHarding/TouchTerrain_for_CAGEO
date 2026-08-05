import struct
from zipfile import ZipFile

import pytest

import tools.validate_launch_mesh_comparison as validator
from tools.validate_launch_mesh_comparison import (
    MeshValidationTimeoutError,
    _count_stl_edge_usage_range,
    _count_stl_edge_usage,
    _mesh_stats,
    _mesh_stats_are_clean,
    _validate_launch_item,
)


def _binary_stl(triangles):
    stl_bytes = bytearray(b"\0" * 80)
    stl_bytes.extend(struct.pack("<I", len(triangles)))
    for triangle in triangles:
        coords = [value for vertex in triangle for value in vertex]
        stl_bytes.extend(
            struct.pack(
                "<12fH",
                0.0,
                0.0,
                0.0,
                *coords,
                0,
            )
        )
    return bytes(stl_bytes)


def test_mesh_stats_counts_same_direction_shared_edges():
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    d = (1.0, 1.0, 0.0)

    stats = _mesh_stats(_binary_stl([(a, b, c), (a, b, d)]))

    assert stats["bad_oriented_edges"] == 1
    assert stats["first_bad_oriented_edges"] == [tuple(sorted((a, b)))]


def test_mesh_stats_accepts_opposite_direction_shared_edges():
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    d = (1.0, 1.0, 0.0)

    stats = _mesh_stats(_binary_stl([(a, b, c), (b, a, d)]))

    assert stats["bad_oriented_edges"] == 0


def test_mesh_stats_are_clean_rejects_empty_mesh():
    stats = _mesh_stats(_binary_stl([]))

    assert stats["triangles"] == 0
    assert not _mesh_stats_are_clean(stats)


def test_mesh_stats_range_honors_timeout_deadline():
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)

    with pytest.raises(MeshValidationTimeoutError):
        _count_stl_edge_usage_range(
            _binary_stl([(a, b, c)]),
            0,
            1,
            deadline=0,
        )


def test_mesh_stats_range_reports_progress_once_at_completion():
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    progress: list[int] = []

    _count_stl_edge_usage_range(
        _binary_stl([(a, b, c), (b, a, c)]),
        0,
        2,
        progress_interval_triangles=1,
        progress_callback=progress.append,
    )

    assert progress == [1, 2]


def test_mesh_stats_parallel_matches_single_worker(monkeypatch):
    monkeypatch.setattr(validator, "MIN_TRIANGLES_PER_MESH_WORKER", 1)
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    d = (0.0, 0.0, 1.0)
    stl_bytes = _binary_stl(
        [
            (a, c, b),
            (a, b, d),
            (b, c, d),
            (c, a, d),
        ]
    )

    assert _mesh_stats(stl_bytes, mesh_workers=2) == _mesh_stats(stl_bytes)


def test_mesh_stats_parallel_reports_progress_to_completion(monkeypatch):
    monkeypatch.setattr(validator, "MIN_TRIANGLES_PER_MESH_WORKER", 1)
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    d = (0.0, 0.0, 1.0)
    stl_bytes = _binary_stl(
        [
            (a, c, b),
            (a, b, d),
            (b, c, d),
            (c, a, d),
        ]
    )
    progress: list[tuple[int, int]] = []

    _count_stl_edge_usage(
        stl_bytes,
        mesh_workers=2,
        progress_callback=lambda completed, total, elapsed: progress.append(
            (completed, total)
        ),
    )

    assert progress
    assert progress[-1] == (4, 4)


def test_pair_mode_empty_zip_fails_validation(tmp_path, monkeypatch):
    zip_path = tmp_path / "empty.zip"
    with ZipFile(zip_path, "w"):
        pass

    def reuse_empty_zip(launch_item, reuse_dir):
        return {
            "config": "empty-pair.json",
            "zip": str(zip_path),
            "size_mb": 0,
            "generation_log": str(tmp_path / "empty-pair.generation.log"),
            "pair_mode": True,
        }

    monkeypatch.setattr(validator, "_reuse_mesh", reuse_empty_zip)

    result, failures = _validate_launch_item(
        {
            "name": "empty pair",
            "cwd": str(tmp_path),
            "config_path": str(tmp_path / "empty-pair.json"),
        },
        {"zip": str(zip_path), "meshes": []},
        tmp_path,
        tmp_path,
        tmp_path,
        1,
        None,
    )

    assert failures == 1
    assert result["status"] == "failed"
    assert result["meshes"] == [
        {
            "entry": "<none>",
            "baseline_entry": None,
            "comparison_status": "missing_current",
            "comparison_ok": False,
            "error": "Generated zip contains no STL meshes.",
        }
    ]
