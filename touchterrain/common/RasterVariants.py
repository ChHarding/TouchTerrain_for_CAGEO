from typing import Union, Any, Callable
import numpy as np

class RasterVariants:
    """Holds a raster with processed copies of it
    """
    
    original: Union[None, np.ndarray] # Original full raster
    """
    Original raster.
    
    ## Normal mode:
    
    Top: The original.
    
    ## Difference mode:
    
    Top: original
    
    Bottom: Original, but ALL areas matched to top_hint mask are set to bottom_floor_elev.
    """
    nan_close: Union[None, np.ndarray] # Raster after NaN close values to bottom and before dilation
    """
    Raster after nan close values between top and bottom.
    
    ## Normal mode:
    
    Top: Same as original. 
    
    ## Difference mode:
    
    Top: NaN close values
    
    Bottom: Original + top_hint mask + NaN close values. 
    """
    dilated: Union[None, np.ndarray]
    """
    Raster after dilation.
    
    ## Normal mode:
    
    Top: Same as original. 
    If top_hint provided, original but dilated outwards towards the top_hint mask with bottom_floor_elev value.
    
    
    ## Difference mode:
    
    Top: Dilated outwards from the nan_close variant outwards 2x with top.original values
    
    Bottom: Original + top_hint mask + NaN close values + Dilated outwards 2x with top.original values
    """
    
    edge_interpolation: Union[None, np.ndarray] # Original full raster with values past edges for interpolation
    
    
    polygon_intersection_geometry: Union[None, np.ndarray] #ndarray dtype=object so we can set it with a list[shapely.Geometry]
    """
    Intersection geometry  between the cell quad and the clipping geometry. In print3DCoordinates. Represented as np.ndarray[list[shapely.Geometry]] The list can include LineString/Polygon. The Polygon geometries are used for making top/bottom surface for a cell. 

    
    This is not a variant! 
    - The precomputed intersecting geometries for a single cell Y,X location that applies across all variants. The cell may not be initialized yet. 
    - This is not padded.
    
    Raster values set to NaN and no polygon_intersection_geometry set if the cell quad is disjoint from the clipping polygon.
    
    Raster value kept as imported and no polygon_intersection_geometry set if cell quad is contained properly in the clipping polygon. Walls can be determined for these non-intersecting cells (no or points-only intersection) by checking if the neighboring walls is NaN.
    
    Raster value kept as imported and polygon_intersection_geometry in partial intersection
    """
    
    polygon_intersection_edge_buckets: Union[None, np.ndarray] #ndarray dtype=object so we can set it with a dict[str,list[BorderEdge]]
    """
    Clipping intersection lines that overlap the normal quad edges in the 4 cardinal directions. Dict keys of 'N' 'W' 'S' 'E' 'other'. Represented as np.ndarray[dict[str,list[BorderEdge]]]. The BorderEdges along the side of a cell are used when creating borders (wall) for a cell.
    
    This is not a variant! 
    
    TODO: This should be stored in the cell object but we only keep the cell objects as we iterate through them so RasterVariants is the place to store this to maintain state.
    """
    
    def __init__(self, original: Union[None, np.ndarray], nan_close: Union[None, np.ndarray], dilated: Union[None, np.ndarray], edge_interpolation: Union[None, np.ndarray]):
        self.original = original
        self.nan_close = nan_close
        self.dilated = dilated
        self.edge_interpolation = edge_interpolation
        
        self.polygon_intersection_geometry = None
        self.polygon_intersection_edge_buckets = None
            
    def copy_tile_raster_variants(self, start_y, end_y, start_x, end_x):
        """Create a RasterVariants based on a subset of the current RasterVariants. Arrays are copied.
        """
        tile_raster = RasterVariants(None, None, None, None)
        
        if self.original is not None:
            tile_raster.original = self.original[start_y:end_y, start_x:end_x].copy()
        if self.nan_close is not None:
            tile_raster.nan_close = self.nan_close[start_y:end_y, start_x:end_x].copy()
        if self.dilated is not None:
            tile_raster.dilated = self.dilated[start_y:end_y, start_x:end_x].copy()
        if self.edge_interpolation is not None:
            tile_raster.edge_interpolation = self.edge_interpolation[start_y:end_y, start_x:end_x].copy()
            
        if self.polygon_intersection_geometry is not None:
            tile_raster.polygon_intersection_geometry = self.polygon_intersection_geometry[start_y:end_y, start_x:end_x].copy()
        if self.polygon_intersection_edge_buckets is not None:
            tile_raster.polygon_intersection_edge_buckets = self.polygon_intersection_edge_buckets[start_y:end_y, start_x:end_x].copy()
            
        return tile_raster
    
    def apply_closure_to_variants(self, f: Callable[[np.ndarray], np.ndarray]):
        """Run a function on all variants. The function takes a ndarray as input and return a ndarray. 
        """
        if self.original is not None:
            self.original = f(self.original)
        if self.nan_close is not None:
            self.nan_close = f(self.nan_close)
        if self.dilated is not None:
            self.dilated = f(self.dilated)
        if self.edge_interpolation is not None:
            self.edge_interpolation = f(self.edge_interpolation)
            
    def set_location_in_variants(self, location: tuple[int, int], new_value:float, set_edge_interpolation: bool = True):
        """Set a location to new value on all variants. The function takes a tuple in Y,X order as location and a new value to set. 
        """
        if self.original is not None:
            self.original[location[0]][location[1]] = new_value
        if self.nan_close is not None:
            self.nan_close[location[0]][location[1]] = new_value
        if self.dilated is not None:
            self.dilated[location[0]][location[1]] = new_value
        if set_edge_interpolation and self.edge_interpolation is not None:
            self.edge_interpolation[location[0]][location[1]] = new_value
        
    def __add__(self, other):
        if self.original is not None:
            self.original += other
        if self.nan_close is not None:
            self.nan_close += other
        if self.dilated is not None:
            self.dilated += other
        if self.edge_interpolation is not None:
            self.edge_interpolation += other
            
        return self
            
    def __sub__(self, other):
        if self.original is not None:
            self.original -= other
        if self.nan_close is not None:
            self.nan_close -= other
        if self.dilated is not None:
            self.dilated -= other
        if self.edge_interpolation is not None:
            self.edge_interpolation -= other
            
        return self
            
    def __mul__ (self, other):
        if self.original is not None:
            self.original *= other
        if self.nan_close is not None:
            self.nan_close *= other
        if self.dilated is not None:
            self.dilated *= other
        if self.edge_interpolation is not None:
            self.edge_interpolation *= other
            
        return self