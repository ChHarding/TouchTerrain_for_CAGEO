class TouchTerrainConfig:    
    """
    Raster bounds
    """
    
    trlat = None
    "lat of top right corner"
    trlon = None
    "lon of top right corner"
    bllat = None
    "lat of bottom left corner"
    bllon = None
    "lon of bottom left corner"
    clean_diags = False
    "clean 2x2 diagonals"
    polygon = None
    "optional geoJSON polygon"
    poly_file = None
    "path to a local kml file"
    polyURL = None
    "URL to a publicly readable(!) kml file on Google Drive"
    
    """
    Raster input
    All DEMs must exactly match the sizes and cell resolution of importedDEM
    """
    
    importedDEM = None
    "None (means: get the DEM from GEE) or local file name with (top) DEM to be used instead"
    importedDEM_interp = None
    "Optional raster file for interpolating at edges"
    top_elevation_hint = None
    "elevation raster for the future top of the model that would be used for a future difference mesh. Used for Normal mode where Difference Mesh will be created in the future with the same top raster."
    bottom_elevation = None
    "elevation raster for the bottom of the model."
    projection = None
    "EPSG number (as int) of projection to be used. Default (None) use the closest UTM zone"
    
    """
    Elevation adjustment
    """
    
    basethick = 2
    "thickness (in mm) of printed base"
    bottom_floor_elev: None|float = None
    "Set bottom raster to an elevation in locations where bottom is NaN but top raster is not NaN. Defaults to min_elev-1. If set to less than min_elev, difference mesh at that point will go thru base."
    fill_holes = None
    "e.g. [10, 7] Specify number of interations to find a neighbor threshold to fill holes. -1 iterations will continue iterations until no more holes are found. Defaults to 7 neighbors in a 3x3 footprint with elevation > 0 to fill a hole with the average of the footprint."
    ignore_leq = None
    "ignore elevation values <= this value, good for removing offshore data. This filter is applied to the original DEM that is read in so further processing may set the height lower."
    lower_leq = None
    "[threshold, offset] if elevation is lower than threhold, lower it by offset mm. Good for adding emphasis to coastlines. Unaffected by z_scale."
    min_elev: None|float = None
    "None means: will be calculated from actual elevation later. min_elev defines the elevation that will be at base_thickness"
    offset_masks_lower = None
    "e.g. [[filename, offset], [filename2, offset2],...] Masked regions (pixel values > 0) in the file will be lowered by offset(mm) * pixel value in the final model."
    top_thickness = None
    "thickness of the top of the model, i.e. top - thickness = bottom. Must exactly match the sizes and cell resolution of importedDEM"
    zscale = 1.0
    "elevation (vertical scaling)"
    
    """
    Mesh generation
    """
    
    bottom_thru_base = False
    "if mesh should drop thru to base"
    CPU_cores_to_use = 0
    "0 means all cores, None (null in JSON!) => don't use multiprocessing"
    dirty_triangles = False
    "allow degenerate triangles for difference mesh. Should only be used for Difference Mesh mode."
    max_cells_for_memory_only = 500 * 500 * 4
    "if total number of cells is bigger, use temp_file instead using memory only"
    no_normals = True 
    "True -> all normals are 0,0,0, which speeds up processing. Most viewers will calculate normals themselves anyway"
    split_rotation: None | int = None
    """Should quad triangulation rotate the splitting edge based on the slope of the created edge?
    None, 0 -> NW>SW edges
    1 -> Rotate for less steep along split edges > Steeper faces along the split.
    2 -> Rotate for more steep along split edges > Less steep faces along the split.
    """
    smooth_borders = True
    "should borders be optimized (smoothed) by removing triangles?"
    temp_folder = "tmp"
    "the folder to put the temp files and the final zip file into"
    
    """
    Mesh output
    """
    
    printres = 1.0
    "resolution (horizontal) of 3D printer (= size of one pixel) in mm"
    fileformat = "STLb"
    """format of 3D model files: 
    "obj"  = wavefront obj (ascii)
    "STLa" = ascii STL
    "STLb" = binary STL
    "GeoTiff" = DEM raster only, no 3D geometry
    """
    zip_file_name: None | str = "terrain"
    "name of zipfile containing the tiles (st/obj) and helper files. If None, zip_file_name will use the config filename without the extension."
    
    """
    Tiling
    """
    
    ntilesx = 1
    "number of tiles in x"
    ntilesy = 1
    "number of tiles in y"
    tile_centered = False
    "True-> all tiles are centered around 0/0, False, all tiles 'fit together'"
    tilewidth = 100 
    "width of each tile in mm (<- !!!!!), tile height is calculated automatically"
    tilewidth_scale = None
    "divdes m width of selection box by this to get tilewidth (supersedes tilewidth setting)"
    tileScale = None
    "Optional tile scale that takes precedence over tilewidth"

    """
    GPX Track
    """
    
    importedGPX = None
    "None or List of GPX file paths that are to be plotted on the model"
    gpxPathHeight = 25
    "Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon, therefore this is in meters. Negative numbers are ok and put a dent in the model"
    gpxPixelsBetweenPoints = 10
    "GPX Files can have a lot of points. This argument controls how many pixel distance there should be between points, effectively causing fewing lines to be drawn. A higher number will create more space between lines drawn on the model and can have the effect of making the paths look a bit cleaner at the expense of less precision"
    gpxPathThickness = 1
    "Stack parallel lines on either side of primary line to create thickness. A setting of 1 probably looks the best"
    
    """
    Miscellaneous until sorted
    """

    # these are the args that could be given manually via the web UI. Is there a limit to the options allowed from the manual options input on web?
    no_bottom = False
    "don't create any bottom triangles. The STL file is not watertight but should still print fine with most slicers (e.g. Cura) and is much smaller"
    #rot_degs = None
    "unused"
    bottom_image = None
    "1 band greyscale image to use as bottom relief raster, same for _each_ tile! see make_buttom_raster)"
    DEM_name: None | str = 'USGS/3DEP/10m'
    "name of DEM source used in Google Earth Engine. for all valid sources, see DEM_sources in TouchTerrainEarthEngine.py. Also used if specifying a custom mesh and zip and extracted folder name."
    kd3_render = False
    "if True will create a html file containing the model as a k3d object."
    map_img_filename = None
    "image with a map of the area"
    only = None
    "2-list with tile index starting at 1 (e.g. [1,2]), which is the only tile to be processed"
    original_query_string = None
    "the query string from the app, including map info. Put into log only. Good for making a URL that encodes the app view"
    unprojected = False
    "don't apply UTM projection, can only work when exporting a Geotiff as the mesh export needs x/y in meters"
    use_geo_coords = None
    "None, centered, UTM. not-None forces units to be in meters, centered will put 0/0 at model center for all tiles. Not-None will interpret basethickness to be in multiples of 10 meters (0.5 mm => 5 m). create STL coords in UTM: None, \"centered\" or \"UTM\""
    
    """
    Runtime only values
    """
    
    config_path: None | str = None
    "The path of the Touch Terrain config file. Set this during runtime. If DEM_name is None or default value, use config filename for default zip and mesh filenames and unzipped folder name."
    
    def mergeDict(self, dict: dict):
        "Overwrite the config values with values from a dict. All values from the dict are added to the config including new values."
        for k in list(dict.keys()):
            try:
                getattr(self, k)
            except AttributeError as e:
                print(e)
                print(f"New config key {k} in user dict but not in default config. Adding it to config.")
            setattr(self, k, dict[k])