# nudge_plan.py
# decide which cells have a positive-Z contact worth repairing

"""Positive-Z nudge planning: candidates, then confirmation.

Deciding to nudge happens in two stages, because an exact contact between the
two meshes is not by itself a defect.

``build_positive_z_nudge_plan`` proposes *candidates* from raster arithmetic
alone: cells where the difference-mesh top and the corrected normal top land on
the same positive Z at the same corner, once both are rounded the way the output
mesh will contain them.

``filter_positive_z_nudge_plan_to_actual_overused_edges`` then *confirms* them
against geometry that was actually emitted. A candidate survives only if its
contact edge really is used by more than two faces in the serialized mesh. An
isolated one-corner contact is confirmed only when its point is an endpoint of a
confirmed overused edge -- see the confirmation criteria in
``spec/positive_z_overused_edge_nudge.md``.

The plan is keyed by padded raster row/column so the normal and difference
meshes of an interlocking pair consume identical decisions while still building
their geometry locally.
"""

from collections.abc import Iterable, Sequence
from typing import Any, Callable

import numpy as np
import shapely

from touchterrain.common.Cell import cell
from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.interpolate_Z import interpolate_z_planar
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.mesh_vocabulary import (
    CELL_NEIGHBOR_SIDES,
    Edge3D,
    NUDGE_MIDPOINT_CORNERS_BY_NAME,
    NUDGE_SIDE_MIDPOINT_NAME,
    POSITIVE_Z_OPPOSITE_CORNER_PAIRS,
    POSITIVE_Z_SE_NW_DIAGONAL,
    POSITIVE_Z_SW_NE_DIAGONAL,
    POSITIVE_Z_SIDE_CONTACT_CHECKS,
    PositiveZNudgePlan,
    PositiveZNudgeRecord,
    PositiveZSurfaceValues,
    SerializedVertexCache,
    SurfaceMesh,
    _empty_borders,
    _empty_side_edge_sets,
    _merge_count_map,
    _parallel_range_results,
    _should_parallelize_rows,
)
from touchterrain.common.mesh_serialization import (
    _serialized_vertex_from_cache,
    edge_xy_signature,
    normalize_coordinate_to_match_mesh_serialization,
    normalize_vertex_to_match_mesh_serialization,
    surface_mesh_edge_counts,
)
from touchterrain.common.raster_interpolation import interpolate_with_NaN
from touchterrain.common.surface_geometry import (
    _surface_planes_from_current_geometry,
)
from touchterrain.common.nudge_geometry import (
    _nudge_keep_footprint_split_sides,
    _nudge_keep_footprint_splits_side,
    _nudge_keep_vertex_names,
    cell_bounds_for_location,
    cell_corner_points,
    cell_side_values,
    edge_cardinal_side,
    quad_corner_vertices_by_xy,
)


def positive_z_surface_contact_edge_record(
    top_meshes: list[SurfaceMesh | None],
    bottom_meshes: list[SurfaceMesh | None],
    split_rotation: int,
    output_fileformat: str,
    side_values: dict[str, float],
) -> dict[str, Any]:
    """Return actual positive top/bottom contact edges by cell side."""
    serialized_vertices: SerializedVertexCache = {}
    top_edges = surface_mesh_edge_counts(
        top_meshes,
        split_rotation,
        output_fileformat,
        serialized_vertices,
    )
    bottom_edges = surface_mesh_edge_counts(
        bottom_meshes,
        split_rotation,
        output_fileformat,
        serialized_vertices,
    )

    record = {
        "side_edges": _empty_side_edge_sets(),
        "diagonal_edges": set(),
        "has_diagonal": False,
    }
    for edge_key, top_count in top_edges.items():
        bottom_count = bottom_edges.get(edge_key, 0)
        if bottom_count == 0:
            continue
        if edge_key[0][2] <= 0 or edge_key[1][2] <= 0:
            continue
        side = edge_cardinal_side(
            edge_xy_signature(edge_key[0], edge_key[1]),
            side_values,
        )
        if side is None:
            if top_count + bottom_count > 2:
                record["has_diagonal"] = True
            record["diagonal_edges"].add(edge_key)
        else:
            record["side_edges"][side].add(edge_key)
    return record


def _positive_z_effective_difference_corners(
    record: PositiveZNudgeRecord,
) -> list[IntermediateCorner]:
    """Return local difference-removal corners implied by a plan record."""
    difference_corners = list(record.get("difference_corners", []))
    if difference_corners:
        return difference_corners

    corners = list(record.get("corners", []))
    if corners:
        return corners

    contact_corners = list(record.get("contact_corners", []))
    split_sides = set(record.get("split_sides", set()))
    if len(contact_corners) == 3:
        required_split_sides = _nudge_keep_footprint_split_sides(
            contact_corners,
        )
        if required_split_sides and required_split_sides.issubset(split_sides):
            return contact_corners
        return []

    if len(contact_corners) == 2:
        contact_set = frozenset(contact_corners)
        if contact_set not in POSITIVE_Z_OPPOSITE_CORNER_PAIRS:
            return []
        open_corner_by_split_sides = {
            frozenset({"S", "E"}): IntermediateCorner.SE,
            frozenset({"S", "W"}): IntermediateCorner.SW,
            frozenset({"N", "E"}): IntermediateCorner.NE,
            frozenset({"N", "W"}): IntermediateCorner.NW,
        }
        open_corner = open_corner_by_split_sides.get(frozenset(split_sides))
        if open_corner is None and len(split_sides) == 1:
            split_side = next(iter(split_sides))
            if contact_set == POSITIVE_Z_SW_NE_DIAGONAL:
                if split_side in {"S", "E"}:
                    open_corner = IntermediateCorner.SE
                elif split_side in {"N", "W"}:
                    open_corner = IntermediateCorner.NW
            elif contact_set == POSITIVE_Z_SE_NW_DIAGONAL:
                if split_side in {"S", "W"}:
                    open_corner = IntermediateCorner.SW
                elif split_side in {"N", "E"}:
                    open_corner = IntermediateCorner.NE
        if open_corner is None:
            return []
        promoted_corners = [
            corner
            for corner in [
                IntermediateCorner.NW,
                IntermediateCorner.NE,
                IntermediateCorner.SW,
                IntermediateCorner.SE,
            ]
            if corner is not open_corner
        ]
        if contact_set.issubset(set(promoted_corners)):
            return promoted_corners
    return []


def _positive_z_has_opposite_diagonal_corners(
    corners: Sequence[IntermediateCorner],
) -> bool:
    """Return whether corners include either positive-Z diagonal pair."""
    corner_set = set(corners)
    return any(
        diagonal_corners.issubset(corner_set)
        for diagonal_corners in POSITIVE_Z_OPPOSITE_CORNER_PAIRS
    )


def _positive_z_actionable_corners(
    cell_j: int,
    cell_i: int,
    corners_for_location: Callable[
        [int, int],
        Sequence[IntermediateCorner],
    ],
    has_shared_side_pattern: Callable[
        [int, int, Sequence[IntermediateCorner]],
        bool,
    ],
    has_opposite_diagonal_pattern: Callable[
        [int, int, Sequence[IntermediateCorner]],
        bool,
    ],
) -> list[IntermediateCorner]:
    """Return corners that should be nudged due to local or nearby contact."""
    corners = list(corners_for_location(cell_j, cell_i))
    if not corners:
        return []

    def has_actionable_pattern(
        location_j: int,
        location_i: int,
        location_corners: Sequence[IntermediateCorner],
    ) -> bool:
        return (
            has_shared_side_pattern(
                location_j,
                location_i,
                location_corners,
            )
            or has_opposite_diagonal_pattern(
                location_j,
                location_i,
                location_corners,
            )
        )

    if has_actionable_pattern(cell_j, cell_i, corners):
        return corners

    for neighbor_j in range(cell_j - 1, cell_j + 2):
        for neighbor_i in range(cell_i - 1, cell_i + 2):
            if neighbor_j == cell_j and neighbor_i == cell_i:
                continue
            neighbor_corners = list(
                corners_for_location(neighbor_j, neighbor_i),
            )
            if has_actionable_pattern(
                neighbor_j,
                neighbor_i,
                neighbor_corners,
            ):
                return corners
    return []


def _positive_z_neighbor_split_sides_from_plan(
    positive_z_nudge_plan: PositiveZNudgePlan,
    corners_from_record: Callable[
        [PositiveZNudgeRecord],
        Sequence[IntermediateCorner],
    ],
) -> dict[tuple[int, int], set[str]]:
    """Return neighbor splits implied by positive-Z local clipping."""
    neighbor_split_sides: dict[tuple[int, int], set[str]] = {}
    for location, record in positive_z_nudge_plan.items():
        corners = list(corners_from_record(record))
        if not corners or len(corners) == 4:
            continue
        for side, neighbor_delta, neighbor_side in CELL_NEIGHBOR_SIDES:
            if not _nudge_keep_footprint_splits_side(corners, side):
                continue
            neighbor_location = (
                location[0] + neighbor_delta[0],
                location[1] + neighbor_delta[1],
            )
            neighbor_split_sides.setdefault(neighbor_location, set()).add(
                neighbor_side,
            )
    return neighbor_split_sides


def _positive_z_difference_neighbor_split_sides(
    positive_z_nudge_plan: PositiveZNudgePlan,
) -> dict[tuple[int, int], set[str]]:
    """Return difference-only neighbor splits implied by local clipping."""
    return _positive_z_neighbor_split_sides_from_plan(
        positive_z_nudge_plan,
        _positive_z_effective_difference_corners,
    )


def _positive_z_empty_cleaned_edge_record() -> dict[str, Any]:
    """Return a fresh positive-Z cleaned edge record with no contact."""
    return {
        "corners": [],
        "side_edges": _empty_side_edge_sets(),
        "has_diagonal": False,
    }


def _positive_z_cell_surface_values(
    upper_raster: np.ndarray,
    lower_raster: np.ndarray,
    cell_j: int,
    cell_i: int,
    zero_threshold: float,
) -> PositiveZSurfaceValues | None:
    """Return positive-Z top and corrected bottom corner values for a cell."""
    upper_elevs = interpolate_with_NaN(upper_raster, cell_i, cell_j)
    lower_elevs = interpolate_with_NaN(lower_raster, cell_i, cell_j)
    if any(
        elev is None or np.isnan(elev)
        for elev in (*upper_elevs, *lower_elevs)
    ):
        return None

    upper_ne, upper_nw, upper_se, upper_sw = upper_elevs
    lower_ne, lower_nw, lower_se, lower_sw = lower_elevs
    upper_values = {
        IntermediateCorner.NW: upper_nw,
        IntermediateCorner.NE: upper_ne,
        IntermediateCorner.SW: upper_sw,
        IntermediateCorner.SE: upper_se,
    }
    lower_values = {
        IntermediateCorner.NW: lower_nw,
        IntermediateCorner.NE: lower_ne,
        IntermediateCorner.SW: lower_sw,
        IntermediateCorner.SE: lower_se,
    }
    for corner, elev in list(lower_values.items()):
        if elev < zero_threshold:
            lower_values[corner] = 0
    return upper_values, lower_values


def _positive_z_nudge_corners_from_values(
    surface_values: PositiveZSurfaceValues,
    output_fileformat: str,
) -> list[IntermediateCorner]:
    """Return positive-Z nudge corners from top and bottom corner values."""
    upper_values, lower_values = surface_values
    corners: list[IntermediateCorner] = []
    for corner in IntermediateCorner:
        upper_z = normalize_coordinate_to_match_mesh_serialization(
            upper_values[corner],
            output_fileformat,
        )
        lower_z = normalize_coordinate_to_match_mesh_serialization(
            lower_values[corner],
            output_fileformat,
        )
        if upper_z == lower_z and upper_z > 0:
            corners.append(corner)
    if len(corners) == 4:
        return []
    return corners


def _positive_z_cleaned_edge_record_from_values(
    corners: Sequence[IntermediateCorner],
    surface_values: PositiveZSurfaceValues,
    cell_j: int,
    cell_i: int,
    cell_size: float,
    offsetx: float,
    offsety: float,
    split_rotation: int,
    output_fileformat: str,
) -> dict[str, Any]:
    """Return contact edges after applying local zero-height cleanup."""
    if not corners:
        return _positive_z_empty_cleaned_edge_record()

    upper_values, lower_values = surface_values
    cell_w, cell_e, cell_n, cell_s = cell_bounds_for_location(
        cell_j,
        cell_i,
        cell_size,
        offsetx,
        offsety,
    )
    temp_top = quad(
        vertex(cell_w, cell_n, upper_values[IntermediateCorner.NW]),
        vertex(cell_w, cell_s, upper_values[IntermediateCorner.SW]),
        vertex(cell_e, cell_s, upper_values[IntermediateCorner.SE]),
        vertex(cell_e, cell_n, upper_values[IntermediateCorner.NE]),
    )
    temp_bottom = quad(
        vertex(cell_w, cell_n, lower_values[IntermediateCorner.NW]),
        vertex(cell_e, cell_n, lower_values[IntermediateCorner.NE]),
        vertex(cell_e, cell_s, lower_values[IntermediateCorner.SE]),
        vertex(cell_w, cell_s, lower_values[IntermediateCorner.SW]),
    )
    temp_cell = cell(
        temp_top,
        temp_bottom,
        _empty_borders(),
    )
    temp_cell.remove_zero_height_volumes(
        split_rotation=split_rotation,
        output_fileformat=output_fileformat,
    )

    contact_record = positive_z_surface_contact_edge_record(
        [temp_cell.topquad] + (temp_cell.topSurfacePolygons or []),
        [temp_cell.bottomquad] + (temp_cell.bottomSurfacePolygons or []),
        split_rotation,
        output_fileformat,
        cell_side_values(
            cell_j,
            cell_i,
            cell_size,
            offsetx,
            offsety,
            output_fileformat,
        ),
    )
    return {
        "corners": list(corners),
        "side_edges": contact_record["side_edges"],
        "has_diagonal": contact_record["has_diagonal"],
    }


def build_positive_z_nudge_plan(
    upper_raster: np.ndarray | None,
    lower_raster: np.ndarray | None,
    emit_raster: np.ndarray | None,
    split_emit_raster: np.ndarray | None,
    cell_size: float,
    offsetx: float,
    offsety: float,
    split_rotation: int,
    ymaxidx: int,
    xmaxidx: int,
    zero_threshold: float,
    output_fileformat: str,
    parallel_workers: int = 1,
) -> PositiveZNudgePlan:
    """Return per-cell positive-Z nudge and split records.

    The plan is keyed by padded raster row/col so normal and difference pair
    meshes can consume identical positive-Z nudge decisions while still
    building geometry locally in each cell.
    """
    if upper_raster is None or lower_raster is None or emit_raster is None:
        return {}

    corners_by_location: dict[
        tuple[int, int],
        tuple[IntermediateCorner, ...],
    ] = {}
    surface_values_by_location: dict[
        tuple[int, int],
        PositiveZSurfaceValues,
    ] = {}

    def cell_will_be_created(cell_j: int, cell_i: int) -> bool:
        if (
            cell_j < 1
            or cell_j > ymaxidx
            or cell_i < 1
            or cell_i > xmaxidx
        ):
            return False
        return not np.isnan(emit_raster[cell_j, cell_i])

    def split_cell_will_be_created(cell_j: int, cell_i: int) -> bool:
        if (
            cell_j < 1
            or cell_j > ymaxidx
            or cell_i < 1
            or cell_i > xmaxidx
        ):
            return False
        raster = split_emit_raster if split_emit_raster is not None else emit_raster
        return not np.isnan(raster[cell_j, cell_i])

    def candidate_for_cell(
        cell_j: int,
        cell_i: int,
    ) -> tuple[
        tuple[int, int],
        tuple[IntermediateCorner, ...],
        PositiveZSurfaceValues,
    ] | None:
        if not cell_will_be_created(cell_j, cell_i):
            return None

        surface_values = _positive_z_cell_surface_values(
            upper_raster,
            lower_raster,
            cell_j,
            cell_i,
            zero_threshold,
        )
        if surface_values is None:
            return None

        corners = tuple(
            _positive_z_nudge_corners_from_values(
                surface_values,
                output_fileformat,
            )
        )
        if not corners:
            return None
        return (cell_j, cell_i), corners, surface_values

    def candidates_for_rows(
        row_start: int,
        row_end: int,
    ) -> tuple[
        dict[tuple[int, int], tuple[IntermediateCorner, ...]],
        dict[tuple[int, int], PositiveZSurfaceValues],
    ]:
        row_corners: dict[
            tuple[int, int],
            tuple[IntermediateCorner, ...],
        ] = {}
        row_surface_values: dict[
            tuple[int, int],
            PositiveZSurfaceValues,
        ] = {}
        for cell_j in range(row_start, row_end):
            for cell_i in range(1, xmaxidx + 1):
                candidate = candidate_for_cell(cell_j, cell_i)
                if candidate is None:
                    continue
                location, corners, surface_values = candidate
                row_corners[location] = corners
                row_surface_values[location] = surface_values
        return row_corners, row_surface_values

    def merge_candidates(
        row_candidates: tuple[
            dict[tuple[int, int], tuple[IntermediateCorner, ...]],
            dict[tuple[int, int], PositiveZSurfaceValues],
        ],
    ) -> None:
        row_corners, row_surface_values = row_candidates
        corners_by_location.update(row_corners)
        surface_values_by_location.update(row_surface_values)

    worker_count = max(1, min(parallel_workers, ymaxidx))
    if not _should_parallelize_rows(ymaxidx, worker_count):
        merge_candidates(candidates_for_rows(1, ymaxidx + 1))
    else:
        for row_candidates in _parallel_range_results(
            1,
            ymaxidx + 1,
            worker_count,
            candidates_for_rows,
        ):
            merge_candidates(row_candidates)

    edge_record_cache: dict[tuple[int, int], dict[str, Any]] = {}

    def cleaned_edge_record(cell_j: int, cell_i: int) -> dict[str, Any]:
        location = (cell_j, cell_i)
        if location in edge_record_cache:
            return edge_record_cache[location]
        corners = corners_by_location.get(location)
        surface_values = surface_values_by_location.get(location)
        if not corners or surface_values is None:
            empty_record = _positive_z_empty_cleaned_edge_record()
            edge_record_cache[location] = empty_record
            return empty_record

        record = _positive_z_cleaned_edge_record_from_values(
            corners,
            surface_values,
            cell_j,
            cell_i,
            cell_size,
            offsetx,
            offsety,
            split_rotation,
            output_fileformat,
        )
        edge_record_cache[location] = record
        return record

    def has_shared_side_pattern(
        cell_j: int,
        cell_i: int,
        corners: Sequence[IntermediateCorner],
    ) -> bool:
        record = cleaned_edge_record(cell_j, cell_i)
        corner_set = set(corners)
        for (
            side_corners,
            side,
            neighbor_delta,
            neighbor_opposite_side,
            neighbor_side,
        ) in POSITIVE_Z_SIDE_CONTACT_CHECKS:
            if not side_corners.issubset(corner_set):
                continue
            neighbor = (
                cell_j + neighbor_delta[0],
                cell_i + neighbor_delta[1],
            )
            if not split_cell_will_be_created(neighbor[0], neighbor[1]):
                continue
            neighbor_corners = corners_by_location.get(neighbor, ())
            if not neighbor_side.issubset(neighbor_corners):
                continue
            if not record["side_edges"][side]:
                return True
            if (
                record["side_edges"][side]
                & cleaned_edge_record(
                    neighbor[0],
                    neighbor[1],
                )["side_edges"][neighbor_opposite_side]
            ):
                return True
        return False

    def has_opposite_diagonal_pattern(
        cell_j: int,
        cell_i: int,
        corners: Sequence[IntermediateCorner],
    ) -> bool:
        return (
            cleaned_edge_record(cell_j, cell_i)["has_diagonal"]
            and _positive_z_has_opposite_diagonal_corners(corners)
        )

    def actionable_corners(
        cell_j: int,
        cell_i: int,
    ) -> tuple[IntermediateCorner, ...]:
        return tuple(
            _positive_z_actionable_corners(
                cell_j,
                cell_i,
                lambda location_j, location_i: corners_by_location.get(
                    (location_j, location_i),
                    (),
                ),
                has_shared_side_pattern,
                has_opposite_diagonal_pattern,
            )
        )

    actionable_by_location = {
        location: corners
        for location in corners_by_location
        if (corners := actionable_corners(*location))
    }

    def midpoint_z_by_name_for_location(
        location: tuple[int, int],
        affected_corners: Sequence[IntermediateCorner],
    ) -> dict[str, float]:
        vertex_names = _nudge_keep_vertex_names(affected_corners)
        surface_values = surface_values_by_location.get(location)
        if vertex_names is None or surface_values is None:
            return {}
        upper_values = surface_values[0]
        return {
            midpoint_name: (
                upper_values[midpoint_corners[0]]
                + upper_values[midpoint_corners[1]]
            ) / 2
            for midpoint_name, midpoint_corners
            in NUDGE_MIDPOINT_CORNERS_BY_NAME.items()
            if midpoint_name in vertex_names
        }

    plan: PositiveZNudgePlan = {
        location: {
            "corners": list(corners),
            "split_sides": set(),
            "contact_corners": list(corners_by_location.get(location, ())),
            "midpoint_z_by_name": midpoint_z_by_name_for_location(
                location,
                corners,
            ),
        }
        for location, corners in actionable_by_location.items()
    }
    for (cell_j, cell_i), corners in actionable_by_location.items():
        for current_side, neighbor_delta, neighbor_side in CELL_NEIGHBOR_SIDES:
            neighbor_location = (
                cell_j + neighbor_delta[0],
                cell_i + neighbor_delta[1],
            )
            if not _nudge_keep_footprint_splits_side(corners, current_side):
                continue
            neighbor_j, neighbor_i = neighbor_location
            if not split_cell_will_be_created(neighbor_j, neighbor_i):
                continue
            record = plan.setdefault(
                neighbor_location,
                {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": list(
                        corners_by_location.get(neighbor_location, ()),
                    ),
                    "midpoint_z_by_name": {},
                },
            )
            record["split_sides"].add(neighbor_side)

    for location, corners in corners_by_location.items():
        plan.setdefault(
            location,
            {
                "corners": [],
                "split_sides": set(),
                "contact_corners": list(corners),
                "midpoint_z_by_name": {},
            },
        )

    return plan


def filter_positive_z_nudge_plan_to_actual_overused_edges(
    candidate_plan: PositiveZNudgePlan,
    cells: np.ndarray,
    cell_size: float,
    offsetx: float,
    offsety: float,
    split_rotation: int,
    output_fileformat: str,
    parallel_workers: int = 1,
) -> PositiveZNudgePlan:
    """Keep candidate cells tied to emitted positive-Z contact overuse."""
    def add_edges_to_counts(
        edge_counts: dict[Edge3D, int],
        meshes: list[SurfaceMesh | None],
    ) -> None:
        for edge_key, count in surface_mesh_edge_counts(
            meshes,
            split_rotation,
            output_fileformat,
        ).items():
            edge_counts[edge_key] = edge_counts.get(edge_key, 0) + count

    def edge_counts_for_rows(
        row_start: int,
        row_end: int,
    ) -> dict[Edge3D, int]:
        row_edge_counts: dict[Edge3D, int] = {}
        for row in range(row_start, row_end):
            for col in range(cells.shape[1]):
                current_cell = cells[row, col]
                if current_cell is None:
                    continue
                add_edges_to_counts(
                    row_edge_counts,
                    current_cell.iter_meshes_for_model(),
                )
        return row_edge_counts

    edge_counts: dict[Edge3D, int] = {}
    worker_count = max(1, min(parallel_workers, cells.shape[0]))
    if not _should_parallelize_rows(cells.shape[0], worker_count):
        _merge_count_map(edge_counts, edge_counts_for_rows(0, cells.shape[0]))
    else:
        for row_edge_counts in _parallel_range_results(
            0,
            cells.shape[0],
            worker_count,
            edge_counts_for_rows,
        ):
            _merge_count_map(edge_counts, row_edge_counts)

    overused_edges = {
        edge_key
        for edge_key, count in edge_counts.items()
        if count > 2 and edge_key[0][2] > 0 and edge_key[1][2] > 0
    }
    overused_edges_by_endpoint: dict[tuple[float, ...], set[Edge3D]] = {}
    for edge_key in overused_edges:
        for endpoint in edge_key:
            overused_edges_by_endpoint.setdefault(endpoint, set()).add(
                edge_key,
            )

    def cell_exists(cell_j: int, cell_i: int) -> bool:
        row = cell_j - 1
        col = cell_i - 1
        return (
            0 <= row < cells.shape[0]
            and 0 <= col < cells.shape[1]
            and cells[row, col] is not None
        )

    filtered: PositiveZNudgePlan = {}
    side_corners_by_side = {
        side: list(corners)
        for (
            corners,
            side,
            _delta,
            _opposite_side,
            _neighbor_side,
        ) in POSITIVE_Z_SIDE_CONTACT_CHECKS
    }

    contact_record_cache: dict[tuple[int, int], dict[str, Any]] = {}

    def contact_record_for_location(
        location: tuple[int, int],
    ) -> dict[str, Any]:
        if location not in contact_record_cache:
            current_cell = cells[location[0] - 1, location[1] - 1]
            contact_record_cache[location] = (
                positive_z_surface_contact_edge_record(
                    current_cell.top_surface_meshes(),
                    current_cell.bottom_surface_meshes(),
                    split_rotation,
                    output_fileformat,
                    cell_side_values(
                        *location,
                        cell_size,
                        offsetx,
                        offsety,
                        output_fileformat,
                    ),
                )
            )
        return contact_record_cache[location]

    def contact_edges_from_record(record: dict[str, Any]) -> set[Edge3D]:
        edges: set[Edge3D] = set(record["diagonal_edges"])
        for side_edges in record["side_edges"].values():
            edges.update(side_edges)
        return edges

    def serialized_contact_corner_points(
        location: tuple[int, int],
        corners: Sequence[IntermediateCorner],
    ) -> set[tuple[float, ...]]:
        current_cell = cells[location[0] - 1, location[1] - 1]
        side_values = cell_side_values(
            *location,
            cell_size,
            offsetx,
            offsety,
            output_fileformat,
        )
        corner_xy = {
            IntermediateCorner.NW: (side_values["W"], side_values["N"]),
            IntermediateCorner.NE: (side_values["E"], side_values["N"]),
            IntermediateCorner.SW: (side_values["W"], side_values["S"]),
            IntermediateCorner.SE: (side_values["E"], side_values["S"]),
        }
        target_xy = {corner_xy[corner] for corner in corners}

        serialized_vertices: SerializedVertexCache = {}

        def serialized_positive_points(
            meshes: Iterable[SurfaceMesh | None],
        ) -> set[tuple[float, ...]]:
            points: set[tuple[float, ...]] = set()
            for mesh in meshes:
                if mesh is None:
                    continue
                if isinstance(mesh, quad):
                    coord_iterable = (
                        v.coords for v in mesh.vl if v is not None
                    )
                else:
                    coords = mesh.exterior.coords
                    coord_iterable = (
                        coords[index] for index in range(len(coords) - 1)
                    )
                for coord in coord_iterable:
                    serialized = _serialized_vertex_from_cache(
                        coord,
                        output_fileformat,
                        serialized_vertices,
                    )
                    if serialized[2] > 0 and serialized[:2] in target_xy:
                        points.add(serialized)
            return points

        return serialized_positive_points(current_cell.top_surface_meshes()) & (
            serialized_positive_points(current_cell.bottom_surface_meshes())
        )

    def midpoint_z_by_name_from_cell_top(
        location: tuple[int, int],
        affected_corners: Sequence[IntermediateCorner],
        fallback_record: dict[str, Any],
    ) -> dict[str, float]:
        cell_j, cell_i = location
        current_cell = cells[cell_j - 1, cell_i - 1]
        if current_cell is None or current_cell.topquad is None:
            return dict(fallback_record.get("midpoint_z_by_name", {}))

        vertex_names = _nudge_keep_vertex_names(affected_corners)
        if vertex_names is None:
            return {}

        cell_w, cell_e, cell_n, cell_s = cell_bounds_for_location(
            cell_j,
            cell_i,
            cell_size,
            offsetx,
            offsety,
        )
        points = cell_corner_points(cell_w, cell_e, cell_n, cell_s)
        planes = _surface_planes_from_current_geometry(
            current_cell.topquad,
            current_cell.topSurfacePolygons,
            split_rotation,
        )
        corner_vertices = quad_corner_vertices_by_xy(
            current_cell.topquad,
            cell_w,
            cell_e,
            cell_n,
            cell_s,
        )
        midpoint_z_by_name: dict[str, float] = {}
        for midpoint_name, midpoint_corners in (
            NUDGE_MIDPOINT_CORNERS_BY_NAME.items()
        ):
            if midpoint_name not in vertex_names:
                continue
            if planes:
                try:
                    midpoint_with_z = interpolate_z_planar(
                        shapely.Point(points[midpoint_name]),
                        planes,
                    )
                except (TypeError, ValueError):
                    midpoint_with_z = None
                if isinstance(midpoint_with_z, shapely.Point):
                    midpoint_coord = midpoint_with_z.coords[0]
                    if len(midpoint_coord) >= 3:
                        midpoint_z_by_name[midpoint_name] = midpoint_coord[2]
                        continue

            midpoint_vertices = [
                corner_vertices.get(corner)
                for corner in midpoint_corners
            ]
            if any(corner_vertex is None for corner_vertex in midpoint_vertices):
                return dict(fallback_record.get("midpoint_z_by_name", {}))
            midpoint_z_by_name[midpoint_name] = (
                midpoint_vertices[0].coords[2]
                + midpoint_vertices[1].coords[2]
            ) / 2
        return midpoint_z_by_name

    for location, candidate in candidate_plan.items():
        corners = list(candidate.get("corners", []))
        if location in filtered:
            continue
        if not cell_exists(*location):
            continue
        if not corners:
            continue

        contact_record = contact_record_for_location(location)
        corner_set = set(corners)
        confirmed_overused_edges: set[Edge3D] = set()
        for (
            side_corners,
            side,
            _delta,
            _opposite_side,
            _neighbor_side,
        ) in POSITIVE_Z_SIDE_CONTACT_CHECKS:
            if not side_corners.issubset(corner_set):
                continue
            confirmed_overused_edges.update(
                contact_record["side_edges"][side] & overused_edges,
            )
        confirmed_overused_edges.update(
            contact_record["diagonal_edges"] & overused_edges,
        )
        if not confirmed_overused_edges:
            continue

        filtered[location] = {
            "corners": corners,
            "split_sides": set(),
            "contact_corners": list(candidate.get("contact_corners", corners)),
            "confirmed_overused_edges": confirmed_overused_edges,
            "midpoint_z_by_name": midpoint_z_by_name_from_cell_top(
                location,
                corners,
                candidate,
            ),
        }

    for location, candidate in candidate_plan.items():
        if location in filtered or not cell_exists(*location):
            continue

        corners = list(candidate.get("corners", []))
        contact_corners = list(candidate.get("contact_corners", corners))
        one_corner_contact = (
            corners
            if len(corners) == 1
            else (
                contact_corners
                if not corners and len(contact_corners) == 1
                else []
            )
        )
        if not one_corner_contact:
            continue

        confirmed_overused_edges: set[Edge3D] = set()
        for contact_point in serialized_contact_corner_points(
            location,
            one_corner_contact,
        ):
            confirmed_overused_edges.update(
                overused_edges_by_endpoint.get(contact_point, set()),
            )
        if not confirmed_overused_edges:
            continue
        filtered[location] = {
            "corners": one_corner_contact,
            "split_sides": set(),
            "contact_corners": contact_corners,
            "confirmed_overused_edges": confirmed_overused_edges,
            "midpoint_z_by_name": midpoint_z_by_name_from_cell_top(
                location,
                one_corner_contact,
                candidate,
            ),
        }

    confirmed_nudge_edges: set[Edge3D] = set()
    for record in filtered.values():
        if record.get("corners"):
            confirmed_nudge_edges.update(record["confirmed_overused_edges"])
    confirmed_nudge_endpoints = {
        endpoint
        for edge in confirmed_nudge_edges
        for endpoint in edge
    }
    if confirmed_nudge_endpoints:
        for location, candidate in candidate_plan.items():
            corners = list(candidate.get("corners", []))
            contact_corners = list(candidate.get("contact_corners", corners))
            if location in filtered or not cell_exists(*location):
                continue
            one_corner_contact = (
                corners if len(corners) == 1
                else contact_corners if not corners and len(contact_corners) == 1
                else []
            )
            if one_corner_contact:
                if (
                    serialized_contact_corner_points(
                        location,
                        one_corner_contact,
                    )
                    & confirmed_nudge_endpoints
                ):
                    filtered[location] = {
                        "corners": one_corner_contact,
                        "split_sides": set(),
                        "contact_corners": contact_corners,
                        "confirmed_overused_edges": set(),
                        "midpoint_z_by_name": midpoint_z_by_name_from_cell_top(
                            location,
                            one_corner_contact,
                            candidate,
                        ),
                    }
                continue
            if not corners:
                continue
            contact_edges = contact_edges_from_record(
                contact_record_for_location(location),
            )
            if not any(
                edge[0] in confirmed_nudge_endpoints
                or edge[1] in confirmed_nudge_endpoints
                for edge in contact_edges
            ):
                continue
            filtered[location] = {
                "corners": corners,
                "split_sides": set(),
                "contact_corners": list(
                    candidate.get("contact_corners", corners),
                ),
                "confirmed_overused_edges": set(),
                "midpoint_z_by_name": midpoint_z_by_name_from_cell_top(
                    location,
                    corners,
                    candidate,
                ),
            }

    for row in range(cells.shape[0]):
        for col in range(cells.shape[1]):
            current_cell = cells[row, col]
            if current_cell is None:
                continue

            location = (row + 1, col + 1)
            contact_record = contact_record_for_location(location)
            confirmed_side_edges: set[Edge3D] = set()
            inferred_corners: list[IntermediateCorner] = []
            for side, side_edges in contact_record["side_edges"].items():
                side_overused_edges = side_edges & overused_edges
                if not side_overused_edges:
                    continue
                confirmed_side_edges.update(side_overused_edges)
                for corner in side_corners_by_side[side]:
                    if corner not in inferred_corners:
                        inferred_corners.append(corner)
            if not confirmed_side_edges:
                continue

            candidate = candidate_plan.get(location, {})
            record = filtered.setdefault(
                location,
                {
                    "corners": [],
                    "difference_corners": [],
                    "split_sides": set(),
                    "contact_corners": list(
                        candidate.get("contact_corners", []),
                    ),
                    "confirmed_overused_edges": set(),
                    "midpoint_z_by_name": {},
                },
            )
            merged_corners = list(
                dict.fromkeys(
                    list(record.get("difference_corners", []))
                    + list(inferred_corners),
                ),
            )
            if 0 < len(merged_corners) < 4:
                record["difference_corners"] = merged_corners
                record.setdefault("confirmed_overused_edges", set()).update(
                    confirmed_side_edges,
                )
                record["difference_midpoint_z_by_name"] = (
                    midpoint_z_by_name_from_cell_top(
                        location,
                        merged_corners,
                        candidate,
                    )
                )

    for row in range(cells.shape[0]):
        for col in range(cells.shape[1]):
            current_cell = cells[row, col]
            if (
                current_cell is None
                or not current_cell.topSurfacePolygons
                or not current_cell.bottomSurfacePolygons
            ):
                continue
            location = (row + 1, col + 1)
            contact_record = contact_record_for_location(location)
            confirmed_flip_edges: set[Edge3D] = set()
            for side_edges in contact_record["side_edges"].values():
                confirmed_flip_edges.update(side_edges & overused_edges)
            confirmed_flip_edges.update(
                contact_record["diagonal_edges"] & overused_edges,
            )
            if not confirmed_flip_edges:
                continue

            record = filtered.setdefault(
                location,
                {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": list(
                        candidate_plan.get(location, {}).get(
                            "contact_corners",
                            [],
                        )
                    ),
                    "confirmed_overused_edges": set(),
                    "midpoint_z_by_name": dict(
                        candidate_plan.get(location, {}).get(
                            "midpoint_z_by_name",
                            {},
                        ),
                    ),
                },
            )
            record.setdefault("flip_edges", set()).update(
                confirmed_flip_edges,
            )

    for (cell_j, cell_i), record in list(filtered.items()):
        corners = record["corners"]
        for current_side, neighbor_delta, neighbor_side in CELL_NEIGHBOR_SIDES:
            neighbor_location = (
                cell_j + neighbor_delta[0],
                cell_i + neighbor_delta[1],
            )
            if not _nudge_keep_footprint_splits_side(corners, current_side):
                continue
            neighbor_candidate = candidate_plan.get(neighbor_location, {})
            if (
                not cell_exists(*neighbor_location)
                and not neighbor_candidate.get("split_sides")
            ):
                continue
            neighbor_record = filtered.setdefault(
                neighbor_location,
                {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": list(
                        neighbor_candidate.get("contact_corners", [])
                    ),
                    "confirmed_overused_edges": set(),
                    "midpoint_z_by_name": dict(
                        neighbor_candidate.get("midpoint_z_by_name", {}),
                    ),
                },
            )
            neighbor_record["split_sides"].add(neighbor_side)
            current_midpoint_name = NUDGE_SIDE_MIDPOINT_NAME[current_side]
            neighbor_midpoint_name = NUDGE_SIDE_MIDPOINT_NAME[neighbor_side]
            current_midpoint_z = record.get(
                "midpoint_z_by_name",
                {},
            ).get(current_midpoint_name)
            if current_midpoint_z is not None:
                neighbor_record.setdefault(
                    "midpoint_z_by_name",
                    {},
                )[neighbor_midpoint_name] = current_midpoint_z

    midpoint_z_by_xy: dict[tuple[float, float], float] = {}
    for (cell_j, cell_i), record in sorted(filtered.items()):
        midpoint_z_by_name = record.get("midpoint_z_by_name", {})
        if not midpoint_z_by_name:
            continue
        cell_w, cell_e, cell_n, cell_s = cell_bounds_for_location(
            cell_j,
            cell_i,
            cell_size,
            offsetx,
            offsety,
        )
        points = cell_corner_points(cell_w, cell_e, cell_n, cell_s)
        for midpoint_name, midpoint_z in list(midpoint_z_by_name.items()):
            if midpoint_name not in points:
                continue
            midpoint_xy = normalize_vertex_to_match_mesh_serialization(
                (*points[midpoint_name], 0.0),
                output_fileformat,
            )[:2]
            serialized_midpoint_z = (
                normalize_coordinate_to_match_mesh_serialization(
                    midpoint_z,
                    output_fileformat,
                )
            )
            shared_z = midpoint_z_by_xy.setdefault(
                midpoint_xy,
                serialized_midpoint_z,
            )
            midpoint_z_by_name[midpoint_name] = shared_z

    return filtered
