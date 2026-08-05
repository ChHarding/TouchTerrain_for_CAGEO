# mesh_vocabulary.py
# shared type aliases, cell geometry constants, and row-parallel helpers

"""Vocabulary shared by every mesh module.

This is the lowest layer of the mesh package. It holds the type aliases,
cardinal/nudge corner tables, and row-chunking helpers that cell creation,
serialization, and nudging all need, so those modules never have to import
each other just to name a coordinate or a cell side.
"""

import os

from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeAlias, Union

import shapely

from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.nudge_corner import IntermediateCorner


Coordinate: TypeAlias = Sequence[float]
XYEdge: TypeAlias = tuple[tuple[float, float], tuple[float, float]]
Edge3D: TypeAlias = tuple[tuple[float, ...], tuple[float, ...]]
DirectedEdge3D: TypeAlias = tuple[tuple[float, ...], tuple[float, ...]]
SurfaceMesh: TypeAlias = Union[quad, shapely.Polygon]
CornerElevations: TypeAlias = tuple[float, float, float, float]
EmittedBottomSurface: TypeAlias = tuple[
    quad | None,
    list[shapely.Polygon] | None,
]
BottomSurfaceProvider: TypeAlias = list[list[EmittedBottomSurface]]
TopFootprintSource: TypeAlias = shapely.Geometry
TopFootprintProvider: TypeAlias = list[list[TopFootprintSource | None]]
PositiveZNudgeRecord: TypeAlias = dict[str, Any]
PositiveZNudgePlan: TypeAlias = dict[tuple[int, int], PositiveZNudgeRecord]
PositiveZSurfaceValues: TypeAlias = tuple[
    dict[IntermediateCorner, float],
    dict[IntermediateCorner, float],
]
SerializedVertexCache: TypeAlias = dict[tuple[float, ...], tuple[float, ...]]
CardinalWallMap: TypeAlias = dict[str, quad]
CellBottomGeometry: TypeAlias = tuple[
    quad,
    dict[IntermediateCorner, vertex] | None,
]

MESH_OUTPUT_SERIALIZATION_DECIMAL_PRECISION = 6

CARDINAL_DIRECTIONS = ("N", "S", "E", "W")
NUDGE_SIDE_MIDPOINT_NAME = {
    "N": "Nmid",
    "S": "Smid",
    "E": "Emid",
    "W": "Wmid",
}
NUDGE_SIDE_ENDPOINT_NAMES = {
    "N": ("NW", "NE"),
    "S": ("SW", "SE"),
    "E": ("SE", "NE"),
    "W": ("SW", "NW"),
}
NUDGE_SIDE_SEGMENT_NAMES = {
    "N": (("NW", "Nmid"), ("Nmid", "NE")),
    "S": (("SW", "Smid"), ("Smid", "SE")),
    "E": (("SE", "Emid"), ("Emid", "NE")),
    "W": (("SW", "Wmid"), ("Wmid", "NW")),
}
NUDGE_MIDPOINT_CORNERS_BY_NAME = {
    "Nmid": (IntermediateCorner.NW, IntermediateCorner.NE),
    "Smid": (IntermediateCorner.SW, IntermediateCorner.SE),
    "Emid": (IntermediateCorner.NE, IntermediateCorner.SE),
    "Wmid": (IntermediateCorner.NW, IntermediateCorner.SW),
}
CELL_NEIGHBOR_SIDES = (
    ("N", (-1, 0), "S"),
    ("S", (1, 0), "N"),
    ("W", (0, -1), "E"),
    ("E", (0, 1), "W"),
)
POSITIVE_Z_SIDE_CONTACT_CHECKS = (
    (
        frozenset((IntermediateCorner.NW, IntermediateCorner.NE)),
        "N",
        (-1, 0),
        "S",
        frozenset((IntermediateCorner.SW, IntermediateCorner.SE)),
    ),
    (
        frozenset((IntermediateCorner.SW, IntermediateCorner.SE)),
        "S",
        (1, 0),
        "N",
        frozenset((IntermediateCorner.NW, IntermediateCorner.NE)),
    ),
    (
        frozenset((IntermediateCorner.NW, IntermediateCorner.SW)),
        "W",
        (0, -1),
        "E",
        frozenset((IntermediateCorner.NE, IntermediateCorner.SE)),
    ),
    (
        frozenset((IntermediateCorner.NE, IntermediateCorner.SE)),
        "E",
        (0, 1),
        "W",
        frozenset((IntermediateCorner.NW, IntermediateCorner.SW)),
    ),
)
POSITIVE_Z_SW_NE_DIAGONAL = frozenset({
    IntermediateCorner.SW,
    IntermediateCorner.NE,
})
POSITIVE_Z_SE_NW_DIAGONAL = frozenset({
    IntermediateCorner.SE,
    IntermediateCorner.NW,
})
POSITIVE_Z_OPPOSITE_CORNER_PAIRS = (
    POSITIVE_Z_SW_NE_DIAGONAL,
    POSITIVE_Z_SE_NW_DIAGONAL,
)


def _empty_borders() -> CardinalWallMap:
    """Return a fresh sparse cardinal-wall map."""
    return {}


def _empty_side_edge_sets() -> dict[str, set[Edge3D]]:
    """Return a fresh N/S/E/W positive-Z edge map."""
    return {direction: set() for direction in CARDINAL_DIRECTIONS}


def single_job_parallel_workers(config: Any, task_count: int) -> int:
    """Return worker count for independent work inside one mesh job."""
    requested = getattr(config, "CPU_cores_to_use", None)
    if getattr(config, "fileformat", None) == "obj":
        return 1
    if task_count <= 1 or requested in (None, 1):
        return 1
    requested_cores = os.cpu_count() if requested == 0 else requested
    if requested_cores is None:
        return 1
    return max(1, min(task_count, requested_cores))


def _parallel_row_ranges(
    row_start: int,
    row_end: int,
    worker_count: int,
) -> list[tuple[int, int]]:
    """Split a half-open row range into deterministic worker chunks."""
    row_count = max(0, row_end - row_start)
    if row_count == 0:
        return []
    bounded_workers = max(1, worker_count)
    rows_per_worker = (
        row_count + bounded_workers - 1
    ) // bounded_workers
    return [
        (start, min(row_end, start + rows_per_worker))
        for start in range(row_start, row_end, rows_per_worker)
    ]


def _should_parallelize_rows(row_count: int, worker_count: int) -> bool:
    """Return whether row chunking has enough work to pay for threading."""
    return (
        worker_count > 1
        and row_count >= max(384, worker_count * 16)
    )


def _parallel_range_results(
    range_start: int,
    range_end: int,
    worker_count: int,
    range_function: Callable[[int, int], Any],
) -> Iterator[Any]:
    """Yield results from applying range_function to split row ranges."""
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        yield from executor.map(
            lambda row_range: range_function(*row_range),
            _parallel_row_ranges(range_start, range_end, worker_count),
        )


def _merge_count_map(target: dict[Any, int], source: dict[Any, int]) -> None:
    """Add source counts into target in place."""
    for key, count in source.items():
        target[key] = target.get(key, 0) + count
