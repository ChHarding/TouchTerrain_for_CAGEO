# TouchTerrain (version 3.6)

TouchTerrain converts digital elevation data into digital model files (STL or OBJ) suitable for 3D printing. It comes as a standalone version and as a server version for a web application. To see the server version in action, go to [http://touchterrain.org](http://touchterrain.org) or
[http://touchterrain.geol.iastate.edu](http://touchterrain.geol.iastate.edu)

TouchTerrain is developed by Chris Harding (Iowa State University) and Franek Hasiuk (Sandia Labs). For questions email `tt@iastate.edu`.

For more in-depth information:

- *TouchTerrain — 3D Printable Terrain Models*, Intern. Journal of Geo-Information, Feb. 2021, [https://doi.org/10.3390/ijgi10030108](https://doi.org/10.3390/ijgi10030108) (open access)
- [ESRI Story Map](https://arcg.is/11Cv5D), [AGU 2020 conference poster](https://public.vrac.iastate.edu/~charding/TouchTerrain%20AGU%202020%20poster.htm)
- *TouchTerrain: A simple web-tool for creating 3D-printable topographic models*, Computers & Geosciences, Volume 109, December 2017, Pages 25-31,
https://doi.org/10.1016/j.cageo.2017.07.005

## Getting Started

TouchTerrain reads Digital Elevation model (DEM) data within a geographical extent (downloaded from Earth Engine or from a local raster file) and from it creates a 3D mesh model file suitable for 3D printing. Online data from EE is automatically UTM projected and adaptively downsampled. The 3D model (STL or OBJ format), possibly consisting of several files (tiles), is saved in a zip file along with a log file with details about the process steps.

For most users, the web app version will most likely meet their requirements. Iowa State University offers the web app here: [http://touchterrain.org](http://touchterrain.org)  or [http://touchterrain.geol.iastate.edu](http://touchterrain.geol.iastate.edu)


## Standalone mode

Standalone mode offers a different approach to processing than the web app. Standalone mode uses Python code, either `TouchTerrain_standalone.py` or a Jupyter notebook to define processing parameters in code and then processes a local DEM raster file or online DEM data from Earth Engine (google account required to authenticate). After processing the resulting zip file is stored locally. A few aspect of TouchTerrain are only exposed via the stand alone version. It also offers a way around around server processing quotas, that make it impossible to create some very large (> ~150 Mb) 3D models as all he processing is done locally (some Google Earth Engine imposed limitations still apply, see Appendix). 

Although a pip `setup.py` file (and `requirements.txt`) are provided, note that it can be non-trivial to get all the required Python libraries to install locally, especially those that are wrappers around C/C++, such as GDAL. It may therefore be easier to run Touchterrain inside a docker container (see [touchterrain_jupyter docker container](https://github.com/ChHarding/TouchTerrain_jupyter_docker)) or to use a jupyter notebook on Colab or Binder (see below).


### TouchTerrain_standalone.py

This defines the processing parameters either directly inside the file (parameters are basically values in a dictionary) of via a JSON file it reads in. An example of such a JSON config is *example_config.json- in the stuff folder. See Processing Parameters below for details. TouchTerrain_standalone.py has only one argument, the path to the JSON file, e.g. `python TouchTerrain_standalone.py stuff/example_config.json` would run the example configuration. Running it without an argument will create a default JSON file (same as the example) that you can then modify. TouchTerrain_standalone.py can be used in conjuction with shell scripts for batch processing (e.g. see [https://github.com/ansonl/DEM2STL](https://github.com/ansonl/DEM2STL))



The recommended way to run the standalone version is to use our [touchterrain_jupyter docker container](https://github.com/ChHarding/TouchTerrain_jupyter_docker).

To use touchterrain in standalone mode (i.e. not via a web server), either run `TouchTerrain_standalone.py` or `TouchTerrain_standalone_jupyter_notebook.ipynb`. Both sit in the project root folder and require that the touchterrain module has been installed.

The jupyter notebook version of standalone also

### Jupyter Notebook version for standalone
For most users, espcially those new to Python, the preferred way to run the standalone version of TouchTerrain is via a jupyter notebook file. Inside the notebook, the same processing parameters described in the JSON config file are defined in Python (as a dictionary). The parameters are explained below for the JSON file version but the python syntax is very similar to JSON. After processing the DEM and saving the model(s) in a zip file. All notebooks offers a map interface ([geemap](https://github.com/giswqs/geemap)) for digitizing the area of the model, either as box, circle or polygon.

We have created four versions of notebooks:

1) __TouchTerrain_standalone_jupyter_notebook.ipynb__ is meant to be run locally or via a docker container and is meant for those familiar with Python. The setup part is now somewhat outdated but the notebook may still form a useful basis. It allow the preview of the model for k3d.
2) __TouchTerrain_jupyter_for_starters.ipynb__ is a modification of 1) meant for Python beginners. It tries to walk a beginner through the process in much more detail by providing a template (workflow) for all major parameters. As such is may be unnecessarily verbose for non-beginners. It also can preview the model via k3d and is again meant to be run locally on via a docker container. 
3) __TouchTerrain_jupyter_for_starters_colab.ipynb__ is a modification of 2) specifically for running on colab (free but Google account required). To run it just click on this badge: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](http://colab.research.google.com/github/ChHarding/TouchTerrain_for_CAGEO/blob/master/TouchTerrain_jupyter_starters_colab.ipynb) and follow the instructions! With some caveats, this is __by far the easiest and fastest way to process DEM data with TouchTerrain standalone!__ The free runtime environment has plenty CPU power and disk space and, as most of the required Python packages are already installed, installation (despite being a bit quirky) is usually done under a minute. Sadly, k3d cannot be run and so it has now model preview.
4) __TouchTerrain_jupyter_for_starters_binder.ipynb__ is similar to 3) but tailored to run on Binder [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/ChHarding/TouchTerrain_for_CAGEO/HEAD?labpath=TouchTerrain_jupyter_starters_binder.ipynb) Binder sets up a free docker container within a slick web interface (nice!) and uses JupyterLab. But, in my experience the installation phase is slower and less reliable than Colab. As lots of Python packages have to be installed (more than 750 Mb!), installation can take 10 - 15 minutes, with long paused w/o progress indication. Refreshing the browser sometimes helps but I've had cases where the installation simply stopped and never finished. In addition, a created instance seems to time out quite quickly, meaning that if your don't use it right away after its lengthy installation, the instance will shut down, requiring a new installation.

__EarthEngine_authentication_guide.md__ has some notes on how to authenticate with EarthEngine, which is required when processing their online DEM data (but not when only processing uploaded local DEM raster files!).


### General Processing parameters

These parameters can be used in the JSON config file or in a python dictionary for hardingcoding them in the jupyter notebook or TouchTerrain_standalone.py.

The JSON config file has the following format:

```json
{
"CPU_cores_to_use": 0,
"DEM_name": "USGS/3DEP/10m",
"basethick": 1,
"bllat": 44.50185267072875,
"bllon": -108.25427910156247,
"bottom_image": null,
"clean_diags": false,
"fileformat": "STLb",
"fill_holes": null,
"ignore_leq": null,
"lower_leq": null,
"importedDEM": null,
"max_cells_for_memory_only": 1000000,
"min_elev": null,
"no_bottom": false,
"no_normals": true,
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

*Note that for Python, None and True/False need to be different:*

| Python | JSON |
| --- | --- |
| None | null |
| True | true |
| False | false |

- `CPU_cores_to_use`: Number of CPU cores (processes) to use. 
  - `0`: use all available cores, which will improve multi-tile processing times but has no effect for single tile processing. 
  - `null`: forces use of only a single core, even for multiple tiles, which is useful when running the multi-tile code in a Debugger.

- `DEM_name`: (resolutions are approximate and strictly true only at the equator!)
  - USGS/3DEP/10m: 10 m, continental USA only. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_NED)
  - JAXA/ALOS/AW3D30/V3_2: Global: 30 m, worldwide, but has some small "holes". [link](https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V3_2)
  - USGS/SRTMGL1_003: 30 m, "worldwide", but not very far north (lower quality and older than ALOS!). [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003)
  - MERIT/DEM/v1_0_3: 90 m, worldwide, with less error in low relief areas. [link](https://developers.google.com/earth-engine/datasets/catalog/MERIT_DEM_v1_0_3)
  - USGS/GMTED2010: ~230 m, truly worldwide. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_GMTED2010)
  - GTOPO30: 30 Arc-Second, 1000 m, 1996, worldwide. [link](https://developers.google.com/earth-engine/datasets/catalog/USGS_GTOPO30)
  - CryoSat-2 Antarctica: 1000 m, antarctica only. [link](https://developers.google.com/earth-engine/datasets/catalog/CPOM_CryoSat2_ANTARCTICA_DEM)
  - NOAA/NGDC/ETOPO1: 2000 m, worldwide, with bathymetry. [link](https://developers.google.com/earth-engine/datasets/catalog/NOAA_NGDC_ETOPO1)

- `basethick`: (in mm) A layer of material this thick will be added below the entire
 model, i.e. its thickness is counted down from the lowest elevation of the entire model. This is particularly important for models with long, deep valleys, which can cause the model to shine through if the base is not thick enough. A base thickness of at least twice the filament thickness is recommended.

- `bllat`: Bottom-left latitude of area to be printed
- `bllon`: Bottom-left longitude
- `trlat`: Top-right latitude
- `trlon`: Top-right longitude

- Polygon to define the area:
  The web app version of TouchTerrain can load a polygon (or poly line) from an uploaded kml file which will supersede the bllat, etc. extent settings. 

  The standalone version can read a kml file using the `poly_file` or `polyURL` parameters. For both, the first polygon found will be used as a mask, i.e. the model will only cover terrain inside the polygon. If no polygon is found, the first polyline is used instead. (Holes in polygons are ignored). kmz files are __not__ supported at this time. To convert kmz to kml, unzip it (will be doc.kml) and rename doc to the (pre-dot) name of the kmz file.

  - `poly_file` : path to a local kml file
  - `polyURL` : URL to a publicly readable(!) kml file on Google Drive

  The standalone version also supports: `polygon` :  a GeoJSON polygon,

- `bottom_image`: (default: `null`). If a filename to a valid greyscale (1-band) 8-bit local image is given (e.g. *TouchTerrain_bottom_example.png* in the *stuff* folder), the image is centered, uniformly resized to have a generous fringe and used to create a relief on the bottom. Low values (black pixels, 0) create a high relief (with a large gap from the buildplate), white pixels (255) make no relief. Must have a base thickness > 0.5 mm. The highest relief is scaled to be 80% of the base thickness. Note that this relief may adversely affect bed adhesion and will certainly make the first few layers considerably slower to print!

- `clean_diags`: (default: `null`). Eliminate 2x2 diagonal filled and empty cells in a DEM that lead to nonmanifold models with 4 faces sharing the same edge.

  ```
  01    and    10
  10           01
  ```

- `fileformat`: file format for 3D model file.
  - `obj`: wavefront obj (ascii)  
  - `STLa`: ascii STL  
  - `STLb`: binary STL  (__preferred mesh format__)
  - __GeoTiff__: while all formats also store the raster used for making the mesh files in the zip file as a GeoTiff, this option ONLY stores the GeoTiff. This is much, much faster and permits downloading  much larger areas without running into the server limit.  Note that this will save a projected raster (unless unprojected is true) at the equivalent of the printres resolution but will ignore all other settings, such as z-scale, etc.

- `fill_holes`: (default: `null`), Specify number of iterations to find and neighbor threshold to fill holes. -1 iterations will continue iterations until no more holes are found. Defaults to 7 neighbors in a 3x3 footprint with elevation > 0 to fill a hole with the average of the footprint. *e.g. [10, 7]*

- `ignore_leq`: (default: `null`). Using an elevation (e.g. 0.0) will ignore any cells less or equal to that elevation. Good for omitting offshore cells and print only onshore terrain. Note that 0 may not be exactly sea level, on some DEMs you may have to experiment with slightly larger values (e.g. try 0.5 for a sharper coastline)

- `lower_leq`: (default: `null`). An alternative to ignore_leq. Given a list in the format [threshold, offset], all cells less than or equal to threshold will be lowered by the offset. This helps with giving emphasis to coastlines. The offset is in mm with respect to the final mesh size. Unaffected by zscale.

- `importedDEM`: (default: `null`). If `null` a geotiff is fetched from Earth Engine as detailed above. If it is set to a filename, this file is used as DEM. In this case, DEM_name, bllat, bllon, trlat and trlon are ignored, but all other parameters are still used.
 
  - You can test this with pyramid.tif (in the stuff folder) which has an elevation of 0 to 255, so probably will need a z-scale of 0.5 on a width of 100 mm. Any GDAL raster file format
 (http://www.gdal.org/frmt_various.html) should be readable. 
    - Set printres to -1 to prevent downsampling and instead use the file's intrinsic resolution. Non-georef'ed rasters (i.e., regular images) are assumed to have a "real-world" cell size of 1.
    - The file can contain cells that are officially undefined. These undefined cells will be omitted in the STL/OBJ file, allowing you to create 3D prints with "organic" boundaries instead of rectangular ones. Unrealistically low or high elevations (e.g. -9999999) will be treated as undefined.

- `max_cells_for_memory_only`: (default: `1000000`). If the number of raster cells to be processed is bigger than this number, temp files are used in the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone. If your machine runs out of memory, lowering this may help.

- `min_elev`: (default: `null`) Minimum elevation to start the model height at after `basethick` height. If null, the minimum elevation found in the DEM is used so the `basethick` height will start at the minimum elevation found in the DEM and not necessarily sea level.

- `no_bottom`: (default: `false`). Will omit any bottom triangles i.e. only stores the top surface and the "walls". The creates ~50% smaller STL/OBJ files. When sliced it should still create a solid printed bottom (tested in Cura >3.6). Note that starting with 3.5 for simple cases, the bottom mesh have been set to just two triangles, so the no_bottom setting is really only useful for cases involving polygon outlines (e.g. from a kml file).

- `no_normals`: (default: `true`). Will NOT calculate normals for triangles in STL files and instead set them to 0,0,0. This is significantly faster and should not matter as on import most slicers and 3D viewers will calculate a normal for each triangle (via cross product) anyway. However, if you require properly calculated normals to be stored in the STL file, set this to false. *(Contributed by idenc)*

- `ntilesx`: Divide the x axis evenly among this many tiles. This is useful if the area being printed would be too large to fit in the printer's bed.
- `ntilesy`: See `ntilesx`, above.

- `only`: (default: `null`). If given a list [x,y], will only process that tile index ([1,1] is upper left tile). This will enable users to d/l otherwise unreasonably large models by processing only one of its tiles at a time (thus staying under the server limit).  
  - __Example__: only:[1,1] (JSON) or only = [1,1] (python) will d/l only the tile with index 1,1
    - Once this tile was downloaded, using __only with [1,2]__, but otherwise repeating the request, will d/l tile 1,2
    - Although each tile will be in a new zip, unzipping them and putting all tiles in a common folder will create a "single" model that will make all tiles fit together when printed. In a 3D viewer, the tiles will fit together without overlaps if tile_centered was false.

- `printres`: (in mm) Should be set to the nozzle size of your printer typically around the diameter of the nozzle (~0.4 mm). This and the tile width determines the resampled resolution of the DEM raster that is the basis of the mesh. Setting this to significantly smaller than your nozzle size is not advised:

  - __Example__: if you want your tile to be 80 mm wide and were to set your printres to 0.4 mm, the DEM raster will be re-sampled from its original resolution to the equivalent of 200 cells. If the tile's area is 2000 m wide in reality, each cell would cover 10 m, which is about the original resolution of the DEM source (for NED). It would be silly to ask for a resolution below the original 10m DEM resolution by lowering printres to less than 0.4. This would simple oversample the requested geotiff, resulting in no increase in detail at the cost of longer processing and larger files. 
    - Note: setting printres to -1 will set it to the equivalent of the DEM sources __original__ (i.e. non-downsampled) resolution. This sounds great, but is, in practice, somewhat limited as Google Earth Engine will not permit TouchTerrain to request rasters larger than 10 Mega Pixels (typically < 34 Mb). The only sanctioned way for using such large rasters is to run a script in the Earth Engine [Code Editor]( https://code.earthengine.google.com/) that requests the raster and stores it as a Google Drive file. An example script is given in the appendix. You can then download it to a regular raster file and use it in stand alone mode with the importedDEM setting (see below). Set printres to -1 to prevent downsampling.

- `sqrt`: (default: `false`) if true, will apply the square root to the final elevation and lower it so the smallest value is 0. This is done after applying z-scale and running _leq operations. When combined with a very large z-scale (100 - 500) this can help to equalize terrain models that have a wide range of elevations, such as going from sea level to 2000 m peaks. This helps to bring out details in low areas while avoiding un-printably pointy mountains. Will only work with all-positive elevation values, so apply ignore_leq(0) if e.g. cells along a shoreline have negative elevations. In the web app, large z-scales have to be set manually, e.g. lie `"sqrt":true, "zscale":100, "ignore_leq":0`

- `tile_centered`: (default: `false`)
  - `false`: All tiles are offset so they all "fit together" when they all are loaded into a 3D viewer, such as Meshlab or Meshmixer.
  - `true`:  each tile is centered around 0/0. This means they will all overlap in a 3D viewer but each tile is already centered on the buildplate, ready to be printed separately.

- `tilewidth`: The width of a tile in mm, tile height will be calculated from the aspect ratio of your area.

- `tilewidth_scale`: (default: `None`). Uses this scale factor to calculate and override the tile width. Ex: a factor of 10000 will divide the real-world width of the area by 10000 and multiply that value by 1000 to arrive at a new tilewidth (in mm). Note that the final x/y scale (reported in the log file) may be slightly different due to some projection adjustments. __(New in 3.6.1)__

- `unprojected`: (default: `false`). (__Works only for exporting GeoTiffs, not for meshes__) Normally, the DEM from EE is projected either into the UTM zone of the center of the selected region or into a polar-stereographic projection (m based) for Arctic/Antarctic regions. If this option is true, the raster is left unprojected.

- `zip_file_name`: default: "terrain" Prefix of the output filename for stand-alone. (.zip is added)

- `zscale`: (default: `1.0`). Vertical exaggeration versus horizontal units.

- `projection`: (default: `null`). By default, the DEM is reprojected to the UTM zone (datum: WGS84) the model center falls into. The EPSG code of that UTM projection is shown in the log file, e.g. UTM 13 N,  EPSG:32613. If a number(!) is given for this projection setting, the system will request the Earth Engine DEM to be reprojected into it. For example, maybe your data spans 2 UTM zones (13 and 14) and you want UTM 14 to be used, so you set projection to 32614. Or maybe you need to use UTM 13 with NAD83 instead of WGS84, so you use 26913. For continent-size models,  WGS84 Web Mercator (EPSG 3857), may work better than UTM. See [https://spatialreference.org/] for descriptions of EPSG codes.
  - Be aware, however, that  Earth Engine __does not support all possible EPSG codes__. For example, North America Lambert Conformal Conic (EPSG 102009) is not supported and gives the error message: *The CRS of a map projection could not be parsed*. I can't find a list of EPSG codes that __are__ supported by EE, so you'll need to use trial and error ...
  - A note on distances: Earth Engine requires that the requested area is given in lat/lon coordinates but it's worth knowing the approximate real-world meter distance in order to select good values for the tile width, number of tiles and the printres. The server version displays the tile width in Javascript but for the standalone version you need to calculate it yourself. This haversine distance (https://en.wikipedia.org/wiki/Haversine_formula, interactive calculator here: http://www.movable-type.co.uk/scripts/latlong.html) depends on the latitude of your area.
  - Once you know the width of your tile in meters, divide it by the number of cells along x (400 cells in the example above) to get an idea of the re-sampled real-world resolution of your model and its scale. This [Help file](https://docs.google.com/document/d/1GlggZ47xER9N85Qls_MiE1jNuihlYEZnFFSVZtX8bKU/pub) goes into the interplay of these parameters in the section: _Understanding the linkage of tile size, tile number, source DEM resolution and 3D print resolution_

- `use_geo_coords`: (default: `null`)
  - with null (or if not given at all), x/y coordinates are in mm and refer to the buildplate
  - "UTM" will use meter based UTM x/y coordinates instead. See [this](http://blog.touchterrain.org/2020/03/exporting-terrain-models-with-real.html) for some background. This is useful to import the mesh file into a 3D GIS, such as ArcGIS Pro. Note that, once imported, you will have to set the coordinate system of the mesh manually, b/c the mesh model file can't contain that information. Unless overwritten, this will be a UTM zone with WGS84. The TouchTerrain log file will contain the equivalent EPSG code.
  - "centered" will set the UTM origin to the center of the full tile, this is make it work together with [BlenderGIS](https://github.com/domlysz/BlenderGIS)

- `smooth_borders`: (default: `true`). For rasters with NoData cells, determines if the borders of "islands" should be smoothed by selectively removing certain outer triangles. This makes printing the easier and puts less "rattle" in the motion system. However, if adjacent areas are printed this option should be set to false to prevent gaps between the areas.

### GPX Path config

- `importedGPX`: list of GPX file paths that are to be plotted on the model (default: null)
- `gpxPathHeight`: (default `40`) Drape GPX path by adjusting the raster elevation by this value in meters at the specified lat/lon. Negative numbers will create a dent.
- `gpxPixelsBetweenPoints`:  (default `20`) Controls how many pixel distance there should be between points, effectively causing fewer lines to be drawn. A higher number will create more space between lines drawn on the model and can have the effect of making the paths look a bit cleaner at the expense of less precision 
- `gpxPathThickness`: (default: `5`) Stacks that number of parallel lines on either side of primary line to create thickness.  

Note on using GPX files: this will simply extrude those pixels covered by a path away from the top surface, i.e. it will not insert proper 90 deg. "walls" for delineating them. To generate a "crisp" path, it may be advisable to use a much higher printres (e.g. 0.2 mm) which allows the extrusion to create steeper (but still non-90 deg.) walls that are more noticeable when 3D printed.

### Offset Mask config

- `offset_masks_lower`: (default: `null`) Masked regions (pixel values > 0) in the file will be lowered (same method as GPX extrusion described above) by offset(mm) pixel value in the final model. *e.g. [[filename, offset], [filename2, offset2],...]* 

### Unit tests (new in 3.5)

- The test folder contains a (somewhat simplistic) setup for running unit tests.
- Each test is defined by a set of input parameters (see above section) and will create a folder (same name as the test) that will contain the resulting files (log, geotiff, STL, etc.) This should make it possible to test (or re-test) specific combination of parameters in the event of a suspected bug.
- Note that some of these tests "fail" with their parameters b/c the expected effect is not yet implemented E.g. kml files cannot (yet) be used with a local geotiff DEM. These will be flagged as WAI (working as intended)
- Note that the current set of tests do not capture all possible combinations as there are simply too many. The number of tests will grow over time but will probably never be complete.
- Running test works by editing `test_TouchTerrain_standalone.py` and selecting the desired test methods by commenting out its `@unittest.skip()` decorator that otherwise forces that test to be skipped and then running the .py file main part (inside the test folder!)
- The test folder also contains a csv file capturing which test uses which parameter settings.

## Server version

All server related files are in `touchterrain/server`

Running `TouchTerrain_app.py` starts a Flask server module, which will be run inside Apache. Contact us if you want to know about the dockerized Gunicorn version we run at ISU. The server creates a webpage, through which the user inputs the area selection and print parameters.

The server presents users with `index.html` (in templates), which can be styled to suit your needs, provided the various input dialogs and JavaScript remain. Starting with version 3, it is based on Bootstrap 4.

The config.py file inside the server folder contains server specific config settings:

- `NUM_CORES`: 0 means: use all cores, 1 means: use only 1 core (useful for debugging)
- `MAX_CELLS`: if the raster has more cells than this number, tempfiles are used instead of memory during the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone.
- `MAX_CELLS_PERMITED`: if the number of cells is bigger than this number, processing is not started. This help to prevents jobs that are so big that the server would start thrashing. It is, however, just a heuristic. Recommended practice is to start a job and see if virtual memory (swapspace) is used and to lower `MAX_CELLS_PERMITED` until this does not happen.
- `GOOGLE_ANALYTICS_TRACKING_ID` is the Google Analytics tracking id that gets inlined into index.html. By default it's our GA id, so be sure to change this to yours or set it to `UA-XXXXXXXX` to disable tracking.
- `PROJ_DIR`: (default: None). Workaround for a OSgeo/GDAL problem with projecting points. This will only matter if you a) run standalone and b) use the GPX path option. Will set the path to a folder that must contain the `proj.db` database that the point projection needs and store it in an environment variable (`PROJ`).  In some installations, `PROJ` points to a folder that doesn’t contain `proj.db`, so use this override to current this issue.

The `touchterrain/common` directory contains files used by both, the standalone and server versions.

`touchterrain/stuff` contains, well, stuff, such as pdfs and example data files.

## Appendix

## Server version (web app)

The server version offers a Google Map interface to select the area and a simple GUI to specify the processing parameters. To run your own server version, an Earth Engine account is needed. It provides a `setup.py` file that will build and install a module called `touchterrain` and also install all prerequisites. We recommend using pip for the installation: run 'pip install .' in the same folder as the setup.py file.

More specific details on how to set up and run your own server are beyond the scope of this ReadMe. If you are interested in the nitty-gritty details on how Iowa State IT deploys the server, please contact us.

### Getting large geotiffs from Google Earth Engine

- The example script below shows how to download potentially very large, high resolution geotiffs from Google Earth Engine. It works around the 10 mega-pixel download limitation by exporting it to Google Drive instead, from which it can then be downloaded and processed with the standalone version of TouchTerrain.
- The example area will only create a 1 Mb geotiff but has been shown to work for larger areas. **Be warned that exporting large areas to a Google Drive can potentially take hours(!).**

- To run this code, you'll need a Google Earth Engine account. Then, go to [https://code.earthengine.google.com/](https://code.earthengine.google.com/), create a new Script (left side) and copy/paste the code below into it. 
- You will need to know the designation for the DEM source (e.g. `JAXA/ALOS/AW3D30/V2_2`) and what the elevation band is called (e.g. `AVE_DSM`) which you can get from  the *Explore in Earth Engine* code snippet you get from the DEM info link on the web app [example](https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V2_2). This will also tells you the meter resolution of the DEM, which is the smallest number you can put into the scale parameter of the Export routine.
- To get the lat/long coordinates of the top right and bottom left corner of your print area box, use the web app and look at the coordinate info in the Area selection box.
- Finally you'll need to know the EPSG code for the coordinate system to use. For UTM, just export a low res version of the are you want with the web app and look into the log file (search for EPSG). Other coordinate systems (EPSG codes) can/may/should work, just remember that some codes seem to not be supported by EE.
- When you run the script you'll get a simple map visualization and a new Task will be created in the Tasks tab (right). `RUN` this task to have Google save the geotiff into your Google Drive. If you want, you can still change the file name and the resolution at this stage. Hit Run one more to start the job. Again, this job may take a long time when exporting large areas.
- When the job is done, you'll see a check mark for your task. Click on the question mark and a popup will appear, hit `Open in Drive`. In Google Drive, download the geotiff.
- Run TouchTerrain in standalone mode and set the importDEM parameter to your geotiff. To use the actual (source) resolution of the geotiff for generating your model, set printres to -1.

```python
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
