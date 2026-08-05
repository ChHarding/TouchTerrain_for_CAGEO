from collections.abc import Callable
from operator import iadd, imul, isub

import numpy as np


_CORE_RASTER_VARIANT_NAMES = (
    "original",
    "nan_close",
    "dilated",
)
_RASTER_VARIANT_NAMES = (*_CORE_RASTER_VARIANT_NAMES, "edge_interpolation")
_CLIPPING_METADATA_NAMES = (
    "polygon_intersection_geometry",
    "polygon_intersection_edge_buckets",
    "polygon_intersection_contains_properly",
)


class RasterVariants:
    """Holds a raster with processed copies of it."""

    original: np.ndarray | None  # Original full raster
    """
    Original raster.
    
    ## Normal mode:
    
    Top: The original.
    
    ## Difference mode:
    
    Top: original
    
    Bottom: Original, but ALL areas matched to top_hint mask are set to bottom_floor_elev.
    """
    
    # Raster after NaN close values to bottom and before dilation.
    nan_close: np.ndarray | None
    """
    Raster after nan close values between top and bottom.
    
    ## Normal mode:
    
    Top: Same as original. 
    
    ## Difference mode:
    
    Top: NaN close values
    
    Bottom: Original + top_hint mask + NaN close values. 
    """
    dilated: np.ndarray | None
    """
    Raster after dilation.
    
    ## Normal mode:
    
    Top: Same as original. 
    If top_hint provided, original but dilated outwards towards the top_hint mask with bottom_floor_elev value.
    
    
    ## Difference mode:
    
    Top: Dilated outwards from the nan_close variant outwards 2x with top.original values
    
    Bottom: Original + top_hint mask + NaN close values + Dilated outwards 2x with top.original values
    """
    
    # Original full raster with values past edges for interpolation.
    edge_interpolation: np.ndarray | None

    # ndarray dtype=object so we can set it with a list[shapely.Geometry].
    polygon_intersection_geometry: np.ndarray | None
    """
    Intersection geometry  between the cell quad and the clipping geometry. In print3DCoordinates. Represented as np.ndarray[list[shapely.Geometry]] The list can include LineString/Polygon. The Polygon geometries are used for making top/bottom surface for a cell. 

    This is not a variant! 
    - The precomputed intersecting geometries for a single cell Y,X location that applies across all variants. The cell may not be initialized yet. 
    - This is not padded.
    
    Raster values set to NaN and no polygon_intersection_geometry set if the cell quad is disjoint from the clipping polygon.
       
    Raster value kept as imported for any non-disjoint cell. Partial cells
    store polygon_intersection_geometry. Fully contained cells are tracked by
    polygon_intersection_contains_properly and intentionally do not store
    redundant full-cell intersection geometry.
    
    Contained cells have polygon_intersection_geometry set to None so that
    create_cell() uses the normal quad and split rotation for enclosed cells.
    """
    
    # ndarray dtype=object so we can set it with a dict[str, list[BorderEdge]].
    polygon_intersection_edge_buckets: np.ndarray | None
    """
    Clipping intersection lines that overlap the normal quad edges in the 4 cardinal directions. Dict keys of 'N' 'W' 'S' 'E' 'other'. Represented as np.ndarray[dict[str,list[BorderEdge]]]. The BorderEdges along the side of a cell are used when creating borders (wall) for a cell.
    
    This is not a variant!
    
    Partial cells store edge buckets for clipped-boundary wall ownership.
    Disjoint and contained cells do not store buckets; contained cells are
    identified by polygon_intersection_contains_properly.
    
    TODO: This should be stored in the cell object but we only keep the cell objects as we iterate through them so RasterVariants is the place to store this to maintain state.
    """
    
    # ndarray dtype=object so we can set it with a bool.
    polygon_intersection_contains_properly: np.ndarray | None
    """
    Store whether a cell is contains_properly within the clipping polygon
    
    This is not a variant!
    """
    
    def __init__(
        self,
        original: np.ndarray | None,
        nan_close: np.ndarray | None,
        dilated: np.ndarray | None,
        edge_interpolation: np.ndarray | None,
    ):
        self.original = original
        self.nan_close = nan_close
        self.dilated = dilated
        self.edge_interpolation = edge_interpolation
        
        self.polygon_intersection_geometry = None
        self.polygon_intersection_edge_buckets = None
        self.polygon_intersection_contains_properly = None
            
    def copy_tile_raster_variants(
        self,
        start_y: int,
        end_y: int,
        start_x: int,
        end_x: int,
    ) -> "RasterVariants":
        """Create a RasterVariants subset with copied arrays."""
        tile_raster = RasterVariants(None, None, None, None)

        for name in (*_RASTER_VARIANT_NAMES, *_CLIPPING_METADATA_NAMES):
            raster = getattr(self, name)
            if raster is not None:
                setattr(
                    tile_raster,
                    name,
                    raster[start_y:end_y, start_x:end_x].copy(),
                )

        return tile_raster

    def apply_closure_to_variants(
        self,
        f: Callable[[np.ndarray], np.ndarray],
    ) -> None:
        """Run a transformation function on all raster variants."""
        for name in _RASTER_VARIANT_NAMES:
            raster = getattr(self, name)
            if raster is not None:
                setattr(self, name, f(raster))

    def set_location_in_variants(
        self,
        location: tuple[int, int],
        new_value: float,
        set_edge_interpolation: bool = True,
    ) -> None:
        """Set one Y/X location on all raster variants."""
        variant_names = (
            _RASTER_VARIANT_NAMES
            if set_edge_interpolation
            else _CORE_RASTER_VARIANT_NAMES
        )
        for name in variant_names:
            raster = getattr(self, name)
            if raster is not None:
                raster[location] = new_value

    def _apply_inplace_operation(
        self,
        operation: Callable[[np.ndarray, object], np.ndarray],
        other: object,
    ) -> "RasterVariants":
        for name in _RASTER_VARIANT_NAMES:
            raster = getattr(self, name)
            if raster is not None:
                operation(raster, other)
        return self

    def __add__(self, other):
        return self._apply_inplace_operation(iadd, other)

    def __sub__(self, other):
        return self._apply_inplace_operation(isub, other)

    def __mul__(self, other):
        return self._apply_inplace_operation(imul, other)
