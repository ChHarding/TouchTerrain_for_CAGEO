# raster_interpolation.py
# interpolate DEM cell corner elevations from a padded raster

"""Corner elevation interpolation shared by cell creation and nudging.

Each shared raster corner is averaged in one canonical operand order so
adjacent cells produce identical floating-point values before mesh
serialization. See ``spec/precision_serialization_conventions.md``.
"""

import numpy as np

from touchterrain.common.mesh_vocabulary import CornerElevations


def interpolate_corner_with_canonical_order(
    elev: np.ndarray,
    top_left_row: int,
    top_left_col: int,
) -> float:
    """Return a corner average from a canonical 2x2 operand order."""
    top_left = elev[top_left_row, top_left_col]
    top_right = elev[top_left_row, top_left_col + 1]
    bottom_left = elev[top_left_row + 1, top_left_col]
    bottom_right = elev[top_left_row + 1, top_left_col + 1]

    if (
        not np.isnan(top_left)
        and not np.isnan(top_right)
        and not np.isnan(bottom_left)
        and not np.isnan(bottom_right)
    ):
        return (top_left + top_right + bottom_left + bottom_right) / 4.0

    total = np.float64(0.0)
    count = 0
    for value in (top_left, top_right, bottom_left, bottom_right):
        if not np.isnan(value):
            total += value
            count += 1
    if count == 0:
        return np.nan
    return total / count


def interpolate_with_NaN(
    elev: np.ndarray,
    i: int,
    j: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return NE, NW, SE, and SW cell corner elevations.

    The same shared raster corner is always averaged in the same operand order
    so adjacent cells produce identical floating-point values before mesh
    serialization.
    """

    NEelev = interpolate_corner_with_canonical_order(elev, j - 1, i)
    NWelev = interpolate_corner_with_canonical_order(elev, j - 1, i - 1)
    SEelev = interpolate_corner_with_canonical_order(elev, j, i)
    SWelev = interpolate_corner_with_canonical_order(elev, j, i - 1)

    if (
        np.isnan(NEelev)
        or np.isnan(NWelev)
        or np.isnan(SEelev)
        or np.isnan(SWelev)
    ):
        return None, None, None, None

    return NEelev, NWelev, SEelev, SWelev


def _interpolated_corner_grid(elev: np.ndarray) -> np.ndarray:
    """Interpolate each shared raster corner once in canonical order."""
    corner_shape = (elev.shape[0] - 1, elev.shape[1] - 1)
    corner_elevations = np.zeros(corner_shape, dtype=np.float64)
    contributing_cells = np.zeros(corner_shape, dtype=np.uint8)
    source_cells = (
        elev[:-1, :-1],
        elev[:-1, 1:],
        elev[1:, :-1],
        elev[1:, 1:],
    )

    for source_cells_at_corner in source_cells:
        contributes = ~np.isnan(source_cells_at_corner)
        corner_elevations[contributes] += source_cells_at_corner[contributes]
        contributing_cells += contributes

    has_contributors = contributing_cells > 0
    np.divide(
        corner_elevations,
        contributing_cells,
        out=corner_elevations,
        where=has_contributors,
    )
    corner_elevations[~has_contributors] = np.nan
    return corner_elevations


def _cell_corner_elevations(
    corner_elevations: np.ndarray,
    i: int,
    j: int,
) -> CornerElevations:
    """Return NE, NW, SE, and SW values from a shared corner grid."""
    return (
        corner_elevations[j - 1, i],
        corner_elevations[j - 1, i - 1],
        corner_elevations[j, i],
        corner_elevations[j, i - 1],
    )


def _zero_elevations_below_threshold(
    elevations: CornerElevations,
    threshold: float,
) -> CornerElevations:
    """Replace elevations below the model base threshold with exact zero."""
    ne_elev, nw_elev, se_elev, sw_elev = elevations
    return (
        0 if ne_elev < threshold else ne_elev,
        0 if nw_elev < threshold else nw_elev,
        0 if se_elev < threshold else se_elev,
        0 if sw_elev < threshold else sw_elev,
    )
