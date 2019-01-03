TouchTerrain
============

TouchTerrain converts publically accessible digital elevation data into digital model files (STL or OBJ) 
suitable for 3D printing. It comes as both a standalone program and a server which creates 3D model files and makes
them available for download.

TouchTerrain is developed by Chris Harding and Franek Hasiuk, of Iowa State
University's [GeoFabLab](http://www.public.iastate.edu/~franek/gfl/gfl.html).

To see the server version in action, go to [touchterrain.geol.iastate.edu](http://touchterrain.geol.iastate.edu) 

For more in-depth information read our paper in Computers & Geosciences:
TouchTerrain: A simple web-tool for creating 3D-printable topographic models, Volume 109, December 2017, Pages 25-31, https://doi.org/10.1016/j.cageo.2017.07.005

Getting Started
===============

Unless you're planning to only use the stand-alone version to import a DEM from a rasterfile (see importedDEM under Standalone), you will need to install Google Earth Engine for Python 2. The directions on GEE's [site](https://developers.google.com/earth-engine/python_install) are a good place to start, but additional information is provided in this repository
in the file `standalone/TouchTerrain_standalone_installation.pdf`.

If you do not already have an account with Google Earth Engine, you will need to
apply for one from Google. This process is typically painless. Once a request is
submitted Google usually approves it within about a day.

Various Python modules must be installed, as detailed in
`standalone/TouchTerrain_standalone_installation.pdf`.

Once Earth Engine is installed you can run either
`standalone/TouchTerrain_standalone.py`
or
`server/TouchTerrain_app.py`
from within their respective directories.



Standalone
==========

`TouchTerrain_standalone.py` uses DEM data from Google Earth Engine of from a local raster file (geotiff, etc.) to
create a 3D model suitable for 3D printing. This model, possibly consisting of several files (tiles), is saved in a ZIP along with an info file describing the properties used to produce it. The downsampled and UTM projected DEM for the area is saved as DEM.tif

`TouchTerrain_standalone.py` reads in a JSON configuration file such as the one
at `standalone/example_config.json`. To run it in a python shell, go into the standalone folder and type

`python TouchTerrain_standalone.py example_config.json`

Note: you will have to install an bunch of modules this to actually work. You can use a local DEM file via the `importedDEM` parameter but if you want to use the Google Earth Engine curated DEMs, you need to get a Google Earth Engine license (free). See the TouchTerrain_standalone_installation.pdf for more on that.

The JSON config file has the following format

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
"importedDEM": null, 
"max_cells_for_memory_only": 1000000, 
"no_bottom": false, 
"ntilesx": 1, 
"ntilesy": 1, 
"printres": 0.5, 
"tile_centered": true, 
"tilewidth": 80, 
"trlat": 44.69741706507476, 
"trlon": -107.97962089843747, 
"unprojected": false, 
"zip_file_name": "terrain", 
"zscale": 1.0
}
```

The syntax of this file is as follows:

 * `DEM_name`:     (resolutions are approximate and strictly true only at the equator!) 
   * USGS/NED: 10 m, continental USA only
   * USGS/SRTMGL1_003: 30 m, "worldwide" but not very far north
   * USGS/GMTED2010: 90 m, truly worldwide
   * NOAA/NGDC/ETOPO1: 1000 m, worldwide, with bathymetry
 
 * `basethick`:  default: 1  (in mm) 
                    A layer of material this thick will be added below the 
                    entire model. This is particularly important for models 
                    with long, deep valleys, which can cause the model to shine through or 
                    if the base is not thick enough. A base thickness of at least twice the
                    filament thickness is recommended.

 * `bllat`:         Bottom-left latitude of area to be printed
 * `bllon`:         Bottom-left longitude
 * `trlat`:         Top-right latitude
 * `trlon`:         Top-right longitude

 * `fileformat`: file format for 3D model file. Units are in meters, you will have to scale them down to print.    
   - obj: wavefront obj (ascii)  (no normals, no texture coordinates yets ...)
   - STLa: ascii STL (with normalized normals)
   - STLb: binary STL (with normalized normals), prefered format
   - GeoTiff: while all formats also store the raster used for making the mesh files in the zip file as a GeoTiff, this option ONLY stores the GeoTiff. This is much, much faster and permits downloading much larger areas without running into the server limit. Note that this will save a projected raster (unless unprojected is true) at the equivalent of the printres resolution (which can be set to the source resolution with -1) but will ignore all other settings, such as z-scale, etc. (__NEW__) 

 * `ntilesx`:       Divide the x axis evenly among this many tiles. This is
                    useful if the area being printed would be too large to fit
                    in the printer's bed.
 * `ntilesy`:       See `ntilesx`, above.
 
 * `tilewidth`:     The width of a tile in mm, tile height will be calculated from the aspect ratio of your area.

 * `printres`:  default: 0.5 (in mm) A realistic resolution for your printer along the buildplate, typically around the diameter of the nozzle (~0.4 mm). This and the tile width determines the resampled resolution of the DEM raster that is the basis of the mesh. E.g. if you want your tile to be 100 mm wide and your printres  is set to 0.25 mm, the DEM raster will be re-sampled from its original resolution to the equivalent of 400 cells. If the tile is 4000 m wide in reality, each cell would cover 10 m, which is already close to the original resolution of the DEM source (for NED).  It is probably pointless to ask for a resolution below the original DEM by lowering printres to less than 0.25 in this case. __New: You can now use the original (source) resolution of the DEM by setting printres to -1!__ 
                  
 * `tile_centered`:  default: false
   * false: all tiles are offset so they all "fit together" when they all are loaded into a 3D viewer, such as Meshlab
   * true:  each tile is centered around 0/0

 * `zip_file_name`: default: "terrain" Prefix of output filename. (.zip is added)

 * `zscale`: default: 1.0 . Vertical exaggeration versus horizontal units.
 
 * `CPU_cores_to_use`: Number of CPU cores (processes) to use. 0 means: use all available cores, null does not use multiprocessing, which is useful when running the code in a Debugger.
 
 * `max_cells_for_memory_only`: default: 1000000 . Tf the number of raster cells to be processed is bigger than this number , temp files are used in the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone.
 
 * `importedDEM`: default: null . With the default, the DEM is fetched from Google Earth Engine as detailed above. If it is set to a filename, such as `pyramid.tif`, this file is used as DEM. In this case, DEM_name, bllat, bllon, trlat and trlon are ignored, but all other parameters are still used. You can test this with pyramid.tif (in the standalone folder) which has an elevation of 0 to 255, so probably will need a z-scale of 0.5 on a width of 100 mm. Any GDAL raster file format (http://www.gdal.org/frmt_various.html) should be readable. __New: the local DEM file can contain cells that have been "masked" as undefined or with unrealistically low or high elevations (e.g. -9999999). These masked cells will be omitted in the STL/OBJ file, allowing you to create 3D prints with "round" borders instead of rectangular borders!

__New options as of Jan. 2019:__

* `no_bottom`: default: false . Will omit any bottom triangles i.e. only stores the top surface and the "walls". The creates ~50% smaller STL/OBJ files. When sliced it should still create a solid printed bottom (tested in Cura 3.6)

* `ignore_leq`: default: null . Using an elevation (e.g. 0.0) will ignore any cells less or equal to that elevation. Good for omitting offshore cells and print shorlines. Note that 0 may not be excatly sealevel on some DEMs, you may have to experiment with slightly larger values (e.g. 0.5)

* `unprojected`: default: false . (Works only for exporting GeoTiffs!) Normally, the DEM from GEE is projected either into the UTM zone of the center of the selected region or into a polar stereographic projection (m based) for Arctic/Antarctic regions. If this option is true, the raster is left unprojected.

* `bottom_image`: default: null . If a filename to a valid greyscale (1-band) 8-bit local image is given (e.g. *mylogo.png*), the image is uniformly resized, and centered to have a generous fringe and used to create a relief on the bottom. Low values (black pixels, 0) create a high relief (with a large gap from the buildplate), white pixels (255) make no relief. The highest relief is scaled to be 80% of the base thickness, to create a list one solid 3D printed layer. Note that this may adversly affect the bed adhesion and will certainly make the first few layers considerably slower to print! 




A note on distances: Google Earth Engine requires that the requested area is given in lat/lon coordinates but it's worth knowing the approximate real-world meter distance in order to select good values for the tile width, number of tiles and the printres. The server version displays the tile width in Javascript but for the standalone version you need to calculate it yourself. This haversine distance (https://en.wikipedia.org/wiki/Haversine_formula, interactive calulator here: http://www.movable-type.co.uk/scripts/latlong.html) depends on the latitude of your area. Once you know the width of your tile in meters, divide it by the number of cells along x (400 cells in the example above) to get an idea of the re-sampled real-world resolution of your model and its scale. The server Help file (https://docs.google.com/document/d/1GlggZ47xER9N85Qls_MiE1jNuihlYEZnFFSVZtX8bKU/pub) goes into the interplay of these parameters in the section: Understanding the linkage of tile size, tile number, source DEM resolution and 3D print resolution




Server
======

Running `TouchTerrain_app.py` starts a server module (service) which will be run inside Apache. Modify the ansiable script to set up the server. The server creates a webpage, through which the user inputs the area selection and print parameters.

The server requires that the file `config.py` be edited to appropriate values.The server also requires oauth authentication to run with Earth Engine. You will need to obtain a private key (`.pem`) file and edit `config.py` to point to it.

The server presents users with `index.html`, which can be styled to suit your needs, provided the various input dialogs and JavaScript remain.

index.html contain the standard Google Analytics tracking boilerplate code at the top. By default it has a bogus tracking id ('UA-XXXXXXXX'), so tracking doesn't work. If you want to activate it, you need to set up your own Google Analytics (https://www.google.com/analytics/web/#home) and use your own UA- tracking code instead.

touchterrain_config.py contains server specific config settings:
- NUM_CORES:  0 means: use all cores, 1 means: use only 1 core (usefull for debugging)
- MAX_CELLS: if the raster has more cells than this number, tempfiles are used instead of memory during the later stages of processing. This is slower but less memory intensive than assembling the entire zip file in memory alone.
- MAX_CELLS_PERMITED: if the number of cells is bigger than this number, processing is not started. This prevents jobs that are so big that the server runs out of memory. It is, however, just a heuristic. Recommeded practice is to start a job and see if virtual memory (swapspace) is used and to lower MAX_CELLS_PERMITED until this does not happen. 


Common
======

The `common` directory contains files used by both the standalone and server apps.
