from touchterrain.common.user_config import TouchTerrainConfig

class TouchTerrainTileInfo:
    """
    Tile info
    Config and other calculated values
    """
    
    config: TouchTerrainConfig
    "TouchTerrainConfig that the user defined"
    
    """Set at initialization
    """
    
    bottom_relief_mm = 1.0
    "thickness of the bottom relief image (float), must be less than base_thickness"
    crs: str = "unprojected"
    "cordinate reference system, can be EPSG code or UTM zone or any projection"
    folder_name: str
    "folder/zip file name for all tiles"
    full_raster_width = -1
    "in pixels"
    full_raster_height = -1
    geo_transform = None
    "GeoTransform of geotiff"
    pixel_mm : float 
    "lateral (x/y) size of a 3D printed 'pixel' in mm"
    min_bot_elev : float
    "Minimum elevation of the processed bottom raster. Needed for multi-tile models"
    scale : float
    "horizontal scale number,  1000 means 1:1000 => 1m in model = 1000m in reality"
    temp_file: str | None = None 
    tile_no_x = -1
    "current(!) tile number along x"
    tile_no_y = -1
    "current(!) tile number along y"
    tile_width: float
    "in mm"
    tile_height: float
    "in mm"
    #user_offset: float # Removed because we can just minus the user given or calculated min_elev instead of first subtracting min elevation of the raster and adding it back again minus the min_elev and calling it user_offset
    "offset between actual data min_elev and user given min_elev"
    
    """Set later"""
    
    file_size: float
    "file size in Mb"
    
    
    """Set in grid_tesselate"""
    
    max_elev: float
    "max elevation of processed top raster"
    max_bot_elev: float
    "max elevation of processed bot raster"
    
    have_nan: bool
    "processed top raster has NaN"
    have_bot_nan: bool
    "processed bottom raster has NaN"
    
    "corner coordinates (may later be needed for 2 bottom triangles)"
    W: float
    E: float
    N: float
    S: float
   
    
            
    def __init__(self, config: TouchTerrainConfig):
        self.config = config
    
