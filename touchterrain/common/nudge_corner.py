from collections.abc import Iterable
from enum import Enum

import numpy


class IntermediateCorner(Enum):
    NE = 0
    NW = 1
    SW = 2
    SE = 3


_OUTWARD_CORNER_OFFSETS: dict[
    IntermediateCorner,
    tuple[tuple[int, int], ...],
] = {
    IntermediateCorner.NE: ((-1, 0), (-1, 1), (0, 1)),
    IntermediateCorner.NW: ((-1, 0), (-1, -1), (0, -1)),
    IntermediateCorner.SW: ((1, 0), (1, -1), (0, -1)),
    IntermediateCorner.SE: ((1, 0), (1, 1), (0, 1)),
}

_SOURCE_CORNER_OFFSETS: dict[
    IntermediateCorner,
    tuple[tuple[int, int], ...],
] = {
    IntermediateCorner.NW: ((-1, -1), (-1, 0), (0, -1), (0, 0)),
    IntermediateCorner.NE: ((-1, 0), (-1, 1), (0, 0), (0, 1)),
    IntermediateCorner.SW: ((0, -1), (0, 0), (1, -1), (1, 0)),
    IntermediateCorner.SE: ((0, 0), (0, 1), (1, 0), (1, 1)),
}

_OPPOSITE_CORNER: dict[IntermediateCorner, IntermediateCorner] = {
    IntermediateCorner.NE: IntermediateCorner.SW,
    IntermediateCorner.NW: IntermediateCorner.SE,
    IntermediateCorner.SW: IntermediateCorner.NE,
    IntermediateCorner.SE: IntermediateCorner.NW,
}


def _location_is_in_raster(
    raster: numpy.ndarray,
    row: int,
    col: int,
) -> bool:
    return 0 <= row < raster.shape[0] and 0 <= col < raster.shape[1]


def _offset_locations(
    cell_location: tuple[int, int],
    offsets: Iterable[tuple[int, int]],
) -> list[tuple[int, int]]:
    row, col = cell_location
    return [
        (row + row_offset, col + col_offset)
        for row_offset, col_offset in offsets
    ]


def _window_has_value_above(
    raster: numpy.ndarray,
    locations: Iterable[tuple[int, int]],
    threshold: float,
    ignore_nan: bool,
) -> bool:
    for row, col in locations:
        if not _location_is_in_raster(raster, row, col):
            continue
        value = raster[row, col]
        if ignore_nan and numpy.isnan(value):
            continue
        if value > threshold:
            return True
    return False


def corner_directions_border_outward_by_lte(
    raster: numpy.ndarray,
    cell_location: tuple[int, int],
    lte: float,
) -> list[IntermediateCorner]:
    """Return corners whose outward neighbor window has no value above lte."""
    matching_corners: list[IntermediateCorner] = []
    for corner, offsets in _OUTWARD_CORNER_OFFSETS.items():
        if not _window_has_value_above(
            raster,
            _offset_locations(cell_location, offsets),
            lte,
            ignore_nan=False,
        ):
            matching_corners.append(corner)
    return matching_corners


def z0_nudge_corners_from_source_raster(
    raster: numpy.ndarray,
    cell_location: tuple[int, int],
    zero_threshold: float = 0,
) -> list[IntermediateCorner]:
    """Return Z0 nudge corners from source-cell contributor windows.

    The target cell must be at or below ``zero_threshold``. The cell is
    considered only when at least one corner's 2x2 contributor window sees a
    value above that threshold. A corner needs nudging when its own contributor
    window does not see a value above the threshold.
    """
    row, col = cell_location
    if row < 0 or row >= raster.shape[0] or col < 0 or col >= raster.shape[1]:
        return []

    current_value = raster[row, col]
    if numpy.isnan(current_value) or current_value > zero_threshold:
        return []

    window_has_positive: dict[IntermediateCorner, bool] = {}
    for corner, offsets in _SOURCE_CORNER_OFFSETS.items():
        window_has_positive[corner] = _window_has_value_above(
            raster,
            _offset_locations(cell_location, offsets),
            zero_threshold,
            ignore_nan=True,
        )

    if not any(window_has_positive.values()):
        return []

    return [
        corner
        for corner, has_positive in window_has_positive.items()
        if not has_positive
    ]


def find_middle_corner(corners: list[IntermediateCorner]) -> IntermediateCorner:
    """Return the spatially middle corner of 3 corners.

    :param corners: 3 corners that border outward with values that are Z=0
    :type corners: list[IntermediateCorner]
    :return: The middle corner
    :rtype: IntermediateCorner
    """
    unique_corners = set(corners)
    if len(corners) != len(unique_corners):
        raise ValueError(
            f"Expected 3 corners, got {len(unique_corners)} unique corners"
        )

    if len(corners) != 3:
        raise ValueError(f"Expected 3 corners, got {len(corners)} corners")

    missing_corner = next(iter(set(IntermediateCorner) - unique_corners))
    return _OPPOSITE_CORNER[missing_corner]
