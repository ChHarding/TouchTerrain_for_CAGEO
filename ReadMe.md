# TouchTerrain

TouchTerrain converts digital elevation data into digital model files (STL or OBJ) suitable for 3D printing. It comes as both as a standalone version  and as a server version for a web application. To see the server version in action, go to
[touchterrain.geol.iastate.edu](http://touchterrain.geol.iastate.edu)


TouchTerrain is developed by Chris Harding (Iowa State University) and Franek Hasiuk (Kansas Geological Survey). For questions email `Geofablab AT gmail DOT com`.


For more in-depth information, read our paper in Computers & Geosciences: TouchTerrain: A simple
web-tool for creating 3D-printable topographic models, Volume 109, December 2017, Pages 25-31,
https://doi.org/10.1016/j.cageo.2017.07.005


## Getting Started

TouchTerrain reads DEM data of a geographical extent (a geotiff file downloaded from Earth Engine or from a local raster file) an creates a 3D model suitable for 3D printing. The geotiff from EE is automatically UTM projected and usually downsampled. The 3D model (STL or OBJ format), possibly consisting of several files (tiles), is saved in a zip file along with a log file with details about the process steps.


 For the standalone version the processing parameters are given directly in the code (hardcoded) or read from a JSON config file. You can use the stand-alone version to process local DEM raster file (see `importedDEM`) or get online DEM data from Earth Engine (provided you have a account with them). After processing the resulting zip file is stored locally. However, there is no graphical (map) interface for easily requesting a certain area from EE, the geographical extent of the request has to be given in lat/long coordinates as text. (Note: this might change in the future, I'm looking into using geemap inside jupyter ...)


The server version offers a Google Map interface to select the area and a simple GUI to specify the processing parameters. An Earth Engine account is needed to run the server version. Some "expert" parameters are only exposed via a JSON style text field input (called manual). Once the request has been processed it is again downloaded as a zip file.


TouchTerrain is only supported for Python 3.6 and higher. It provides a `setup.py` file that will build a module called `touchterrain` and also install all prerequisites. We recommend using pip for the installation: 'pip install .' in the same folder as the setup.py file (


 If you want to process DEM data curated by Earth Engine you will need request a (free) [Developer's license from Google](https://signup.earthengine.google.com/#!/)) and/or a [service account](https://developers.google.com/earth-engine/service_account) EarthEngine is primarily meant for cloud operations (which is sort of a pun considering its mainly used for Remote Sensing data ...) via Javascript but has a Python API for non-visual functionality, such as requesting geotiffs, which touchterrain can use.


 (TODO: add something more about how to get the Earth Engine account set up!)


## Standalone mode
To use touchterrain in standalone mode (i.e. not via a web server), either run `TouchTerrain_standalone.py` or `TouchTerrain_standalone_jupyter_notebook.ipynb`. Both sit in the project root folder and require that the touchterrain module has been installed.

### Jupyter Notebook version
The preferred way to run the standalone version of TouchTerrain is via the jupyter notebook file __standalone/TouchTerrain_standalone_jupyter_notebook.ipnb__. Inside the notebook, the processing parameters are given as a python dictionary. The parameters are explained below for the JSON file version but the python syntax is very similar to JSON. After processing the DEM and saving the model(s) in a zip file, it can also unzip it for you and visualize the model(s) in a 3D viewer inside the browser (using the k3d package).You can see a web view version of the note book [here](https://htmlpreview.github.io/?https://github.com/ChHarding/TouchTerrain_for_CAGEO/blob/master/stuff/TouchTerrain_standalone_jupyter_notebook.html)

For more details see this: [touchterrain jupyter notebook - get started](https://docs.google.com/document/d/1bS-N7elMMWU44LctQpMPbbNSurftY3fRealTwOK-5ME/edit?usp=sharing)

### Simple python version
`TouchTerrain_standalone.py`is the straight python equivalent of the jupyter notebook. Processing parameters as either given as a dictionary inside the file or are read in via a JSON configuration file such as `stuff/example_config.json`.

If you don't want to use a JSON file, edit the parameters in `TouchTerrain_standalone.py` and run it an IDE or via the command line terminal. To run it in a terminal, go into the standalone folder and type:
`python TouchTerrain_standalone.py`

To run it with the JSON config file, edit the JSON file `stuff/example_config.json`, save it in the same folder as `TouchTerrain_standalone.py` and edit it for your needs. To run it, open a terminal and type:

`python TouchTerrain_standalone.py example_config.json`


### Processing parameters

These parameters can be used in the JSON config file or in a python dictionary for hardingcoding them in the jupyter notebook or TouchTerrain_standalone.py.

The JSON config file has the following format:
```
{
"CPU_cores_to_use": 0,
"DEM_name": "USGS/NED",
"basethick": 1,
"bllat": 44.50185267072875,
"bllon": -108.25427910156247,
"bottom_image": null,
"fileformat": "STLb",
"ignore_leq": null,
"lower_leq": null,
"importedDEM": null,
"max_cells_for_memory_only": 1000000,
"no_bottom": false,
"ntilesx": 1,
"ntilesy": 1,
"only": null,
"printres": 0.5,
"tile_centered": false,
"tilewidth": 80,
"trlat": 44.69741706507476,
"trlon": -107.97962089843747,
"unprojected": false,
"zip_file_name": "terrain",
"zscale": 1.0
}
```

Note that for Python, None and True/False need to be different:

```
    Python:  JSON:
    None     null
    True     true
    False    false
```

 * `DEM_name`:     (resolutions are approximate and strictly true only at the equator!)
    - USGS/NED: 10 m, continental USA only
    - USGS/SRTMGL1_003: 30 m, "worldwide" but not very far north
    - USGS/GMTED2010: ~230 m, truly worldwide
    - NOAA/NGDC/ETOPO1: 1000 m, worldwide, with bathymetry

 * `basethick`: (in mm) A layer of material this thick will be added below the entire
 model. This is particularly important for models with long, deep valleys, which can cause the model  to shine through or if the base is not thick enough. A base thickness of at least twice the
 filament thickness is recommended.

 * `bllat`:         Bottom-left latitude of area to be printed
 * `bllon`:         Bottom-left longitude
 * `trlat`:         Top-right latitude
 * `trlon`:         Top-right longitude

 * `fileformat`: file format for 3D model file.
    - obj: wavefront obj (ascii)  
    - STLa: ascii STL  
    - STLb: binary STL  (__preferred mesh format__)
    - __GeoTiff__: while all formats also store the raster used for making the mesh files in the zip file as a GeoTiff, this option ONLY stores the GeoTiff. This is much, much faster and permits downloading  much larger areas without running into the server limit.    Note that this will save a projected raster (unless unprojected is true) at the equivalent of the printres resolution (which can be set to the source resolution with -1) but will ignore all other settings, such as z-scale, etc.


 * `ntilesx`:       Divide the x axis evenly among this many tiles. This is useful if the area being
 printed would be too large to fit in the printer's bed.
 * `ntilesy`:       See `ntilesx`, above.

 * `tilewidth`:     The width of a tile in mm, tile height will be calculated from the aspect ratio
 of your area.

 * `printres`:  (in mm) Should be set to the nozzle size of your printer typically around the diameter of the nozzle (~0.4 mm). This and the tile width determines the resampled resolution of the DEM raster that is the basis of the mesh. Setting this to significantly smaller than your nozzle size is not advised:    

 __Example__: if you want your tile to be 80 mm wide and were to set your printres to 0.4 mm, the DEM raster will be re-sampled from its original resolution to the equivalent of 200 cells. If the tile's area is 2000 m wide in reality, each cell would cover 10 m, which is about the original resolution of the DEM source (for NED).  
 It would be silly to ask for a resolution below the original 10m DEM resolution by lowering printres to less than 0.4. This would simple oversample the requested geotiff, resulting in no increase in detail at the cost of longer processing and larger files. You can set printres to be whatever the original (source) resolution of the DEM is by setting it to -1 (i.e. 10 m in this example). However, with a 0.4 mm nozzle this only makes sense if your area is more than 80 mm wide otherwise you're again only wasting time and diskspace.

 * `tile_centered`:  default: false
    - false: All tiles are offset so they all "fit together" when they all are loaded into a 3D viewer, such as Meshlab
    - true:  each tile is centered around 0/0

 * `zip_file_name`: default: "terrain" Prefix of output filename. (.zip is added)

 * `zscale`: default: 1.0 . Vertical exaggeration versus horizontal units.

 * `CPU_cores_to_use`: Number of CPU cores (processes) to use. 0 means: use all available cores,
 null does not use multiprocessing, which is useful when running the code in a Debugger.

 * `max_cells_for_memory_only`: default: 1000000 . If the number of raster cells to be processed is
 bigger than this number, temp files are used in the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone. If your machine runs out of memory, lowering this may help.

 * `importedDEM`: default: null. If `null` a geotiff is fetched from Earth Engine as detailed above. If it is set to a filename, this file is used as DEM. In this case, DEM_name, bllat, bllon, trlat and trlon are ignored, but all other parameters are still used.
 You can test this with pyramid.tif (in the standalone folder) which has an elevation of 0 to 255, so probably will need a z-scale of 0.5 on a width of 100 mm. Any GDAL raster file format
 (http://www.gdal.org/frmt_various.html) should be readable. Non-georef'ed rasters (images) are assumed to have a "real-world" cell size of 1.
 The file can contain cells that are officially undefined. These masked cells will be omitted in the STL/OBJ file, allowing you to create 3D prints with "round" borders instead of rectangular borders. Unrealistically low or high elevations (e.g.  -9999999) will also be treated as undefined.

* `no_bottom`: default: false . Will omit any bottom triangles i.e. only stores the top surface and
the "walls". The creates ~50% smaller STL/OBJ files. When sliced it should still create a solid
printed bottom (tested in Cura 3.6)

* `no_normals`: default: true . Will NOT calculate normals for triangles in STL files and instead set them to 0,0,0. This is significantly faster and should not matter as on import most slicers and 3D viewers will calculate the normal for each triangle (via cross product) anyway. However, if you require properly calculated normals, set this to false.

* `ignore_leq`: default: null . Using an elevation (e.g. 0.0) will ignore any cells less or equal to that elevation. Good for omitting offshore cells and print only onshore terrain. Note that 0 may not be exactly sealevel, on some DEMs you may have to experiment with slightly larger values (e.g. 0.5)

* `lower_leq`: default: null. An alternative to ignore_leq. Given a list in the format [threshold, offset], all cells less than or equal to threshold will be lowered by the offset. This helps with giving emphasis to coastlines. The offset is in mm with respect to the final mesh size. Unaffected by zscale.

* `unprojected`: default: false . (Works only for exporting GeoTiffs, not for meshes) Normally, the DEM from EE is projected either into the UTM zone of the center of the selected region or into a polarstereographic projection (m based) for Arctic/Antarctic regions. If this option is true, the raster is left unprojected.

* `bottom_image`: default: null . If a filename to a valid greyscale (1-band) 8-bit local image is given (e.g. *mylogo.png*), the image is uniformly resized, centered to have a generous fringe
and used to create a relief on the bottom. Low values (black pixels, 0) create a high relief (with a large gap from the buildplate), white pixels (255) make no relief. The highest relief is scaled to be 80% of the base thickness. Note that this relief may adversely affect  bed adhesion and will certainly make the first few layers considerably slower to print!

* `only`: default: null . If given a list [x,y] will only process that tile index ([1,1] is upper
left tile). This will enable users to d/l otherwise unreasonably large models by processing one of
its tiles at a time (thus staying under the server limit).  
    _Example_: only:[1,1] (JSON) or only = [1,1] (python) will d/l only the tile with index 1,1
Once this tile was downloaded, using only with [1,2], but otherwise repeating the request, will d/l tile 1,2
    Although each tile will be in a new zip, unzipping them and putting all tiles in a common folder will
create a "single" model that will make all tiles fit together when printed. In a 3D viewer, the
tiles will fit together without overlaps if tile_centered was false.

* `projection`: default: null . By default, the DEM is reprojected to the UTM zone (datum: WGS84) the model center falls into. The EPSG code of that UTM projection is shown in the log file, e.g. UTM 13 N,  EPSG:32613. If a number(!) is given for this projection setting, the system will request the Earth Engine DEM to be reprojected into it. For example, maybe your data spans 2 UTM zones (13 and 14) and you want UTM 14 to be used, so you set projection to 32614. Or maybe you need to use UTM 13 with NAD83 instead of WGS84, so you use 26913. For continent-size models,  WGS84 Web Mercator (EPSG 3857), my work better than UTM. See [https://spatialreference.org/] for descriptions of EPSG codes.
     Be aware, however, that  Earth Engine does not support all possible EPSG codes. For example, North America Lambert Conformal Conic (EPSG 102009) is not supported and gives an error message: *The CRS of a map projection could not be parsed*





__A note on distances:__ Google Earth Engine requires that the requested area is given in lat/lon
coordinates but it's worth knowing the approximate real-world meter distance in order to select good
values for the tile width, number of tiles and the printres. The server version displays the tile
width in Javascript but for the standalone version you need to calculate it yourself. This haversine distance (https://en.wikipedia.org/wiki/Haversine_formula, interactive calculator here:
http://www.movable-type.co.uk/scripts/latlong.html) depends on the latitude of your area.

Once you know the width of your tile in meters, divide it by the number of cells along x (400 cells in the example above) to get an idea of the re-sampled real-world resolution of your model and its scale. This [Help file](https://docs.google.com/document/d/1GlggZ47xER9N85Qls_MiE1jNuihlYEZnFFSVZtX8bKU/pub) goes into the interplay of these parameters in the section: _Understanding the linkage of tile size, tile number, source DEM resolution and 3D print resolution_


- "use_geo_coords": default: null.
    - "UTM" will use meter based UTM x/y coordinates for all generated coordinates instead of mm within your buildplate). See [this](http://blog.touchterrain.org/2020/03/exporting-terrain-models-with-real.html) for some background).
    - "centered" will set the UTM origin to the center of the full tile, to work with [BlenderGIS](https://github.com/domlysz/BlenderGIS)


## Server version

All server related files are in `touchterrain/server`

Running `TouchTerrain_app.py` starts a Flask server module, which will be run inside Apache. Contact us if you want a dockerized Gunicorn version). The server creates a webpage, through which the user inputs the area selection and print parameters.

The server presents users with `index.html` (in templates), which can be styled to suit your needs, provided the various input dialogs and JavaScript remain.

config.py contains server specific config settings:
- NUM_CORES:  0 means: use all cores, 1 means: use only 1 core (usefull for debugging)
- MAX_CELLS: if the raster has more cells than this number, tempfiles are used instead of memory during the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone.
- MAX_CELLS_PERMITED: if the number of cells is bigger than this number, processing is not started. This help to prevents jobs that are so big that the server would start thrashing. It is, however, just a heuristic. Recommeded practice is to start a job and see if virtual memory (swapspace) is used and to lower MAX_CELLS_PERMITED until this does not happen.
- GOOGLE_ANALYTICS_TRACKING_ID is the Google Analytics tracking id that gets inlined into index.html. By default it's our GA id, so be sure to change this to yours or set it to 'UA-XXXXXXXX' to disable tracking.


The `touchterrain/common` directory contains files used by both, the standalone and server versions.
