# TouchTerrain (version 3.0)

TouchTerrain converts digital elevation data into digital model files (STL or OBJ) suitable for 3D printing. It comes as a standalone version and as a server version for a web application. To see the server version in action, go to [http://touchterrain.org](http://touchterrain.org)  or
[http://touchterrain.geol.iastate.edu](http://touchterrain.geol.iastate.edu)


TouchTerrain is developed by Chris Harding (Iowa State University) and Franek Hasiuk (Kansas Geological Survey). For questions email `Geofablab AT gmail DOT com`.


For more in-depth information:
- *TouchTerrain — 3D Printable Terrain Models*, Intern. Journal of Geo-Information, Feb. 2021, [https://doi.org/10.3390/ijgi10030108](https://doi.org/10.3390/ijgi10030108) (open access)
- [ESRI Story Map](https://arcg.is/11Cv5D), [AGU 2020 conference poster](https://public.vrac.iastate.edu/~charding/TouchTerrain%20AGU%202020%20poster.htm)
- *TouchTerrain: A simple web-tool for creating 3D-printable topographic models*, Computers & Geosciences, Volume 109, December 2017, Pages 25-31,
https://doi.org/10.1016/j.cageo.2017.07.005


## Getting Started

TouchTerrain reads DEM data of a geographical extent (a geotiff file downloaded from Earth Engine or from a local raster file) and from it creates a 3D model suitable for 3D printing. Online data from EE is automatically UTM projected and usually downsampled. The 3D model (STL or OBJ format), possibly consisting of several files (tiles), is saved in a zip file along with a log file with details about the process steps.


 For the standalone version the processing parameters are given directly in the code (hardcoded) or read from a JSON config file. You can use the stand-alone version to process local DEM raster file (see `importedDEM`) or get online DEM data from Earth Engine (provided you have a account with them). After processing the resulting zip file is stored locally. The jupyter notebook version of standalone also offers a graphical (map) interface for digitizing the area of the  model, either as box, circle or polygon. The recommended way to run the standalone version is to use our [touchterrain_jupyter docker container](https://github.com/ChHarding/TouchTerrain_jupyter_docker).

The server version offers a Google Map interface to select the area and a simple GUI to specify the processing parameters. An Earth Engine account is needed to run the server version. Some "expert" parameters are only exposed via a JSON style text field input (called manual). Once the request has been processed it is again downloaded as a zip file.

TouchTerrain is only supported for Python 3.6 and higher. It provides a `setup.py` file that will build a module called `touchterrain` and also install all prerequisites. We recommend using pip for the installation: run 'pip install .' in the same folder as the setup.py file.

__Unclear if the dev license is still needed__
 If you want to process DEM data curated by Earth Engine you will need to request a (free) [Developer's license from Google](https://signup.earthengine.google.com/#!/)) and/or a [service account](https://developers.google.com/earth-engine/service_account). EarthEngine is primarily meant for cloud operations  via Javascript but has a Python API for non-visual functionality, such as requesting geotiffs, which touchterrain uses.
To learn more about how to set up a Earth Engine account, refer to the jupyter notebook _TouchTerrain_standalone_jupyter_notebook.ipynb_ or [TouchTerrain_standalone_jupyter_notebook.html](https://chharding.github.io/TouchTerrain_for_CAGEO/TouchTerrain_standalone_jupyter_notebook.html) (which is the notebook rendered into html).


## Standalone mode
To use touchterrain in standalone mode (i.e. not via a web server), either run `TouchTerrain_standalone.py` or `TouchTerrain_standalone_jupyter_notebook.ipynb`. Both sit in the project root folder and require that the touchterrain module has been installed.

### Jupyter Notebook version
The preferred way to run the standalone version of TouchTerrain is via the jupyter notebook file __TouchTerrain_standalone_jupyter_notebook.ipnb__. Inside the notebook, the processing parameters are given as a python dictionary. The parameters are explained below for the JSON file version but the python syntax is very similar to JSON. After processing the DEM and saving the model(s) in a zip file, it can also unzip it for you and visualize the model(s) in a 3D viewer inside the browser (using the `k3d` package).You can see a web view version of the note book [here](https://htmlpreview.github.io/?https://github.com/ChHarding/TouchTerrain_for_CAGEO/blob/master/stuff/TouchTerrain_standalone_jupyter_notebook.html)

For more details see this: [touchterrain jupyter notebook - get started](https://docs.google.com/document/d/1bS-N7elMMWU44LctQpMPbbNSurftY3fRealTwOK-5ME/edit?usp=sharing)

A beginner friendly jupyter note book (TouchTerrain_jupyter_for_starters.ipynb) is also available, which required little to no jupyter knowledge.


### Simple python version
`TouchTerrain_standalone.py`is the straight python equivalent of the jupyter notebook. Processing parameters are either given as a dictionary inside the file or are read in from a JSON configuration file such as `stuff/example_config.json`.

If you don't want to use a JSON file, edit the hardcoded parameters in `TouchTerrain_standalone.py` and run it an IDE or via the command line terminal. To run it in a terminal, go into the standalone folder and type:

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
    - USGS/NED: 10 m, continental USA only. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_NED)
    - JAXA/ALOS/AW3D30/V2_2: Global: 30 m, worldwide, but has some small "holes". [link](https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V2_2)
    - USGS/SRTMGL1_003: 30 m, "worldwide", but not very far north (lower quality and older than ALOS!). [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003)
    - MERIT/DEM/v1_0_3: 90 m, worldwide, with less error in low relief areas. [link](https://developers.google.com/earth-engine/datasets/catalog/MERIT_DEM_v1_0_3)
    - USGS/GMTED2010: ~230 m, truly worldwide. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_GMTED2010)
    - GTOPO30: 30 Arc-Second, 1000 m, 1996, worldwide. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_GTOPO30)
    - CryoSat-2 Antarctica: 1000 m, antarctica only. [link](https://developers.google.com/earth-engine/datasets/catalog/CPOM_CryoSat2_ANTARCTICA_DEM)
    - NOAA/NGDC/ETOPO1: 2000 m, worldwide, with bathymetry. [link](https://developers.google.com/earth-engine/datasets/catalog/NOAA_NGDC_ETOPO1)


 * `basethick`: (in mm) A layer of material this thick will be added below the entire
 model, i.e. its thickness is counted down from the lowest elevation of the entire model. This is particularly important for models with long, deep valleys, which can cause the model to shine through if the base is not thick enough. A base thickness of at least twice the filament thickness is recommended.

 * `bllat`:         Bottom-left latitude of area to be printed
 * `bllon`:         Bottom-left longitude
 * `trlat`:         Top-right latitude
 * `trlon`:         Top-right longitude

* Polygon to define the area:
    The web app version of TouchTerrain can load a polygon (or poly line) from an uploaded kml file which will supersede the bllat, etc. extent settings. 

    The standalone version can read a kml file using the `poly_file` or `polyURL` parameters. For both, the first polygon found will be used as a mask, i.e. the model will only cover terrain inside the polygon. If no polygon is found, the first polyline is used instead. (Holes in polygons are ignored). kmz files are __not__ supported at this time. To convert kmz to kml, unzip it (will be doc.kml) and rename doc to the (pre-dot) name of the kmz file.

    * `poly_file` : path to a local kml file
    * `polyURL` : URL to a publicly readable(!) kml file on Google Drive

    The standalone version also supports:
    * `poly` : string containing a GeoJSON polygon, for example:
        ```
        {"type": "Polygon", 
        "coordinates": [ [[30, 10], [40, 40], [20, 40], [10, 20], [30, 10]]]}
        ```

 * `fileformat`: file format for 3D model file.
    - obj: wavefront obj (ascii)  
    - STLa: ascii STL  
    - STLb: binary STL  (__preferred mesh format__)
    - __GeoTiff__: while all formats also store the raster used for making the mesh files in the zip file as a GeoTiff, this option ONLY stores the GeoTiff. This is much, much faster and permits downloading  much larger areas without running into the server limit.  Note that this will save a projected raster (unless unprojected is true) at the equivalent of the printres resolution but will ignore all other settings, such as z-scale, etc.

 * `ntilesx`:       Divide the x axis evenly among this many tiles. This is useful if the area being printed would be too large to fit in the printer's bed.
 * `ntilesy`: See `ntilesx`, above.

 * `tilewidth`: The width of a tile in mm, tile height will be calculated from the aspect ratio of your area.

 * `printres`:  (in mm) Should be set to the nozzle size of your printer typically around the diameter of the nozzle (~0.4 mm). This and the tile width determines the resampled resolution of the DEM raster that is the basis of the mesh. Setting this to significantly smaller than your nozzle size is not advised:    

    - __Example__: if you want your tile to be 80 mm wide and were to set your printres to 0.4 mm, the DEM raster will be re-sampled from its original resolution to the equivalent of 200 cells. If the tile's area is 2000 m wide in reality, each cell would cover 10 m, which is about the original resolution of the DEM source (for NED). It would be silly to ask for a resolution below the original 10m DEM resolution by lowering printres to less than 0.4. This would simple oversample the requested geotiff, resulting in no increase in detail at the cost of longer processing and larger files. 
    - Note: setting printres to -1 will set it to the equivalent of the DEM sources _original_ (i.e. non-downsampled) resolution. This sounds great, but is, in practice, somewhat limited as Google Earth Engine will not permit TouchTerrain to request rasters larger than 10 Mega Pixels (typically < 34 Mb). The only sanctioned way for using such large rasters is to run a script in the Earth Engine [Code Editor]( https://code.earthengine.google.com/) that requests the raster and stores it as a Google Drive file. An example script is given in the appendix. You can then download it to a regular raster file and use it in stand alone mode with the importedDEM setting (see below). Set printres to -1 to prevent downsampling.

 * `tile_centered`:  default: false
    - false: All tiles are offset so they all "fit together" when they all are loaded into a 3D viewer, such as Meshlab or Meshmixer.
    - true:  each tile is centered around 0/0. This means they will all overlap in a 3D viewer but each tile is already centered on the buildplate, ready to be printed separately.

 * `zip_file_name`: default: "terrain" Prefix of the output filename for stand-alone. (.zip is added)

 * `zscale`: default: 1.0 . Vertical exaggeration versus horizontal units.

 * `CPU_cores_to_use`: Number of CPU cores (processes) to use. 
    - 0: use all available cores, which will improve multi-tile processing times but has no effect for single tile processing. 
    - null: forces use of only a single core, even for multiple tiles, which is useful when running the multi-tile code in a Debugger.

 * `max_cells_for_memory_only`: default: 1000000 . If the number of raster cells to be processed is
 bigger than this number, temp files are used in the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone. If your machine runs out of memory, lowering this may help.

 * `importedDEM`: default: null. If `null` a geotiff is fetched from Earth Engine as detailed above. If it is set to a filename, this file is used as DEM. In this case, DEM_name, bllat, bllon, trlat and trlon are ignored, but all other parameters are still used.
 You can test this with pyramid.tif (in the stuff folder) which has an elevation of 0 to 255, so probably will need a z-scale of 0.5 on a width of 100 mm. Any GDAL raster file format
 (http://www.gdal.org/frmt_various.html) should be readable. 
Set printres to -1 to prevent downsampling and instead use the file's intrinsic resolution. Non-georef'ed rasters (i.e., regular images) are assumed to have a "real-world" cell size of 1.
 The file can contain cells that are officially undefined. These undefined cells will be omitted in the STL/OBJ file, allowing you to create 3D prints with "organic" boundaries instead of rectangular ones. Unrealistically low or high elevations (e.g. -9999999) will be treated as undefined.

* `no_bottom`: default: false. Will omit any bottom triangles i.e. only stores the top surface and
the "walls". The creates ~50% smaller STL/OBJ files. When sliced it should still create a solid
printed bottom (tested in Cura >3.6)

* `no_normals`: default: true. Will NOT calculate normals for triangles in STL files and instead set them to 0,0,0. This is significantly faster and should not matter as on import most slicers and 3D viewers will calculate a normal for each triangle (via cross product) anyway. However, if you require properly calculated normals to be stored in the STL file, set this to false. (Contributed by idenc)

* `ignore_leq`: default: null. Using an elevation (e.g. 0.0) will ignore any cells less or equal to that elevation. Good for omitting offshore cells and print only onshore terrain. Note that 0 may not be exactly sealevel, on some DEMs you may have to experiment with slightly larger values (e.g. 0.5)

* `lower_leq`: default: null. An alternative to ignore_leq. Given a list in the format [threshold, offset], all cells less than or equal to threshold will be lowered by the offset. This helps with giving emphasis to coastlines. The offset is in mm with respect to the final mesh size. Unaffected by zscale.

* `unprojected`: default: false. (__Works only for exporting GeoTiffs, not for meshes__) Normally, the DEM from EE is projected either into the UTM zone of the center of the selected region or into a polar-stereographic projection (m based) for Arctic/Antarctic regions. If this option is true, the raster is left unprojected.

* `bottom_image`: default: null. If a filename to a valid greyscale (1-band) 8-bit local image is given (e.g. *mylogo.png*), the image is uniformly resized, centered to have a generous fringe
and used to create a relief on the bottom. Low values (black pixels, 0) create a high relief (with a large gap from the buildplate), white pixels (255) make no relief. Must have a base thickness > 0.5 mm. The highest relief is scaled to be 80% of the base thickness. Note that this relief may adversely affect bed adhesion and will certainly make the first few layers considerably slower to print!

* `only`: default: null. If given a list [x,y], will only process that tile index ([1,1] is upper
left tile). This will enable users to d/l otherwise unreasonably large models by processing only one of its tiles at a time (thus staying under the server limit).  

    _Example_: only:[1,1] (JSON) or only = [1,1] (python) will d/l only the tile with index 1,1
Once this tile was downloaded, using _only with [1,2]_, but otherwise repeating the request, will d/l tile 1,2
    Although each tile will be in a new zip, unzipping them and putting all tiles in a common folder will
create a "single" model that will make all tiles fit together when printed. In a 3D viewer, the
tiles will fit together without overlaps if tile_centered was false.

* `projection`: default: null . By default, the DEM is reprojected to the UTM zone (datum: WGS84) the model center falls into. The EPSG code of that UTM projection is shown in the log file, e.g. UTM 13 N,  EPSG:32613. If a number(!) is given for this projection setting, the system will request the Earth Engine DEM to be reprojected into it. For example, maybe your data spans 2 UTM zones (13 and 14) and you want UTM 14 to be used, so you set projection to 32614. Or maybe you need to use UTM 13 with NAD83 instead of WGS84, so you use 26913. For continent-size models,  WGS84 Web Mercator (EPSG 3857), may work better than UTM. See [https://spatialreference.org/] for descriptions of EPSG codes.

    - Be aware, however, that  Earth Engine __does not support all possible EPSG codes__. For example, North America Lambert Conformal Conic (EPSG 102009) is not supported and gives the error message: *The CRS of a map projection could not be parsed*. I can't find a list of EPSG codes that _are_ supported by EE, so you'll need to use trial and error ...
      
    - A note on distances: Earth Engine requires that the requested area is given in lat/lon coordinates but it's worth knowing the approximate real-world meter distance in order to select good values for the tile width, number of tiles and the printres. The server version displays the tile width in Javascript but for the standalone version you need to calculate it yourself. This haversine distance (https://en.wikipedia.org/wiki/Haversine_formula, interactive calculator here: http://www.movable-type.co.uk/scripts/latlong.html) depends on the latitude of your area.

    - Once you know the width of your tile in meters, divide it by the number of cells along x (400 cells in the example above) to get an idea of the re-sampled real-world resolution of your model and its scale. This [Help file](https://docs.google.com/document/d/1GlggZ47xER9N85Qls_MiE1jNuihlYEZnFFSVZtX8bKU/pub) goes into the interplay of these parameters in the section: _Understanding the linkage of tile size, tile number, source DEM resolution and 3D print resolution_

* `use_geo_coords`: default: true. On DEM's with NWill smooth out
    - with null (or if not given at all), x/y coordinates are in mm and refer to the buildplate
    - "UTM" will use meter based UTM x/y coordinates instead. See [this](http://blog.touchterrain.org/2020/03/exporting-terrain-models-with-real.html) for some background. This is useful to import the mesh file into a 3D GIS, such as ArcGIS Pro. Note that, once imported, you will have to set the coordinate system of the mesh manually, b/c the mesh model file can't contain that information. Unless overwritten, this will be a UTM zone with WGS84. The TouchTerrain log file will contain the equivalent EPSG code.
    - "centered" will set the UTM origin to the center of the full tile, this is make it work together with [BlenderGIS](https://github.com/domlysz/BlenderGIS)

* `smooth_borders`: default: true. For rasters with NoData cells, determines if the borders of "islands" should be smoothed by selectively removing
                    certain outer triangles. This makes printing the easier and puts less "rattle" in the motion system. However, if adjacent areas are printed this option should be set to false to prevent gaps between the areas.    

* `importedGPX`: list of GPX file paths that are to be plotted on the model (default: null)
* `gpxPathHeight`: (default 40) Drape GPX path by adjusting the raster elevation by this value in meters at the specified lat/lon. Negative numbers will create a dent.
* `gpxPixelsBetweenPoints`:  (default 20) Controls how many pixel distance there should be between points, effectively causing fewing lines to be drawn. A higher number will create more space between lines drawn on the model and can have the effect of making the paths look a bit cleaner at the expense of less precision 
* `gpxPathThickness`: (default: 5) Stacks that number of parallel lines on either side of primary line to create thickness.  

Note on using GPX files: this will simply extrude those pixels covered by a path away from the top surface, i.e. it will not insert proper 90 deg. "walls" for delineating them. To generate a "crisp" path, it may be advisable to use a much higher printres (e.g. 0.2 mm) which allows the extrusion to create steeper (non-90 deg.) walls that are more noticeable when 3D printed.



## Server version

All server related files are in `touchterrain/server`

Running `TouchTerrain_app.py` starts a Flask server module, which will be run inside Apache. Contact us if you want to know about the dockerized Gunicorn version we run at ISU. The server creates a webpage, through which the user inputs the area selection and print parameters.

The server presents users with `index.html` (in templates), which can be styled to suit your needs, provided the various input dialogs and JavaScript remain. Starting with version 3, it is based on Bootstrap 4.

The config.py file inside the server folder contains server specific config settings:
- NUM_CORES: 0 means: use all cores, 1 means: use only 1 core (useful for debugging)
- MAX_CELLS: if the raster has more cells than this number, tempfiles are used instead of memory during the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone.
- MAX_CELLS_PERMITED: if the number of cells is bigger than this number, processing is not started. This help to prevents jobs that are so big that the server would start thrashing. It is, however, just a heuristic. Recommeded practice is to start a job and see if virtual memory (swapspace) is used and to lower MAX_CELLS_PERMITED until this does not happen.
- GOOGLE_ANALYTICS_TRACKING_ID is the Google Analytics tracking id that gets inlined into index.html. By default it's our GA id, so be sure to change this to yours or set it to 'UA-XXXXXXXX' to disable tracking.
- PROJ_DIR: (default: None). Workaround for a OSgeo/GDAL problem with projecting points. This will only matter if you a) run standalone and b) use the GPX path option. Will set the path to a folder that must contain the proj.db database that the point projection needs and store it in an environment variable (PROJ).  In some installations, PROJ points to a folder that doesn’t contain proj.db, so use this override to current this issue.


The `touchterrain/common` directory contains files used by both, the standalone and server versions.

`touchterrain/stuff` contains, well, stuff, such as pdfs and example data files.

## Appendix

### Getting large geotiffs from Google Earth Engine
- The example script below shows how to download potentially very large, high resolution geotiffs from Google Earth Engine. It works around the 10 mega-pixel download limitation by exporting it to Google Drive instead, from which it can then be downloaded and processed with the stand alone version of TouchTerrain.
- The example area will only create a 1 Mb geotiff but has been shown to work for larger areas. **Be warned that exporting large areas to a Google Drive can potentially take hours(!).**

- To run this code, you'll need a Google Earth Engine account. Then, go to [https://code.earthengine.google.com/](https://code.earthengine.google.com/), create a new Script (left side) and copy/paste the code below into it. 
- You will need to know the designation for the DEM source (e.g. `JAXA/ALOS/AW3D30/V2_2`) and what the elevation band is called (e.g. `AVE_DSM`) which you can get from  the Explore in Earth Engine code snippet you get from DEM info link on the web app [example](https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V2_2). This will also tells you the meter resolution of the DEM, which is the smallest number you can put into the scale parameter of the Export routine.
- To get the lat/long coordinates of the top right and bottom left corner of your print area box, use the web app and look at the coordinate info in the Area selection box.
- Finally you'll need to know the EPSG code for the coordinate system to use. For UTM, just export a low res version of the are you want with the web app and look into the log file (search for EPSG).
- When you run the script you'll get a simple map visualization and a new Task will be created in the Tasks tab (right). `RUN` this task to have Google save the geotiff into your Google Drive. If you want, you can still change the file name and the resolution at this stage. Hit Run one more to start the job. Again, this job may take a long time when exporting large areas.
- When the job is done, you'll see a check mark for your task. Click on the question mark and a popup will appear, hit `Open in Drive`. In Google Drive, download the geotiff.


```
// Example of exporting a raster from EE to Google Drive (Jan. 2021)

// You will need the corner coords, which you can get from the Area Selection Box display
// on the web app and the EPSG code for whatever projection you want to use. If you want
// to use a UTM zon, look at the log file from the web app.
// You also should know the source resolution of your DEM so you can set the scale parameter
// of the export to it.


// Set DEM source  
var dataset = ee.Image('JAXA/ALOS/AW3D30/V2_2');
var elevation = dataset.select('AVE_DSM');
print(elevation); // print some metadata into console

// make a spectral color scheme for elevation data layer
var elevationVis = { 
  min: 0,
  max: 4000,
  palette: ['0000ff', '00ffff', 'ffff00', 'ff0000', 'ffffff'],
  opacity: 0.5,
};
Map.addLayer(elevation, elevationVis, 'Elevation');

// define area to export and show as box layer
var trlat = 46.78374215384358
var trlon = 8.071201291153262
var bllat = 46.63448889213306
var bllon = 7.574375128591488
var geometry = ee.Geometry.Rectangle([ trlon, trlat, bllon, bllat ]);
Map.addLayer(geometry, {'opacity': 0.5}, 'box');  

// Fly to center of Box
Map.setCenter(
  trlon - ((trlon - bllon) / 2), 
  trlat - ((trlat - bllat) / 2), 
  8 // zoomlevel
);

// Export the image, specifying scale and region.
// https://developers.google.com/earth-engine/guides/exporting
Export.image.toDrive({
  image: elevation,
  description: 'EE_to_Google_Drive_example', // name of geotiff (.tif will be added)
  fileFormat: 'GeoTIFF',
  scale: 30, // resolution in meters
  maxPixels: 1e12, // overwrites the default of 1e08
  region: geometry,
  crs: "EPSG:32632" // EPSG code for the UTM zone or whatever coordinate system you want to use
});

// When this code is run, an export task will be created in the Code Editor Tasks tab. 
// Click the Run button next to the task to start it. 
// The image will be created in your Drive account with the specified fileFormat.
```

