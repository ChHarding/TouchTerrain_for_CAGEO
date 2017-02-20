TouchTerrain
============

TouchTerrain converts digital elevation models drawn from Google Earth Engine,
or user provided files, into models suitable for 3D printing. It comes as both a
standalone program as well as a server which creates 3D model files and makes
them available for download.

TouchTerrain is developed by Chris Harding and Franek Hasiuk, of Iowa State
University's [GeoFabLab](http://www.public.iastate.edu/~franek/gfl/gfl.html).

To see the server version in action, go to touchterrain.geol.iastate.edu 

Getting Started
===============

You will need to install Google Earth Engine for Python 2. The directions on
GEE's [site](https://developers.google.com/earth-engine/python_install) are a
good place to start, but additional information is provided in this repository
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

`TouchTerrain_standalone.py` draws information from Google Earth Engine to
create a 3D model suitable for 3D printing. This model, possibly consisting of
several files, is saved in a ZIP along with an info file describing the
properties used to produce it.

`TouchTerrain_standalone.py` reads in a JSON configuration file such as the one
at `standalone/example_config.json`. The file has the following format

    {
      "DEM_name":      "USGS/NED",          
      "basethick":     1, 
      "bllat":         44.50185267, 
      "bllon":         -108.254279, 
      "fileformat":    "STLb", 
      "ntilesx":       1, 
      "ntilesy":       1, 
      "printres":      0.5, 
      "tile_centered": true, 
      "tilewidth":     80, 
      "trlat":         44.6974170, 
      "trlon":         -107.97962, 
      "zip_file_name": "terrain", 
      "zscale":        1.0
    }

The syntax of this file is as follows:

 * `DEM_name`:     (resolutions are approximate and strictly true only at the equator!) 
   * USGS/NED: 10 m, continental USA only
   * USGS/SRTMGL1_003: 30 m, "worldwide" but not very far north
   * USGS/GMTED2010: 90 m, truly worldwide
   * NOAA/NGDC/ETOPO1: 1000 m, worldwide, with bathymetry
   * [AU/GA/AUSTRALIA_5M_DEM (5 m, Australia only)  - coming soon]

 * `basethick`:     A layer of material this thick will be added below the 
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
   - STLb: binary STL (with normalized normals)

 * `ntilesx`:       Divide the x axis evenly among this many tiles. This is
                    useful if the area being printed would be too large to fit
                    in the printer's bed.
 * `ntilesy`:       See `ntilesx`, above.
 
 * `tilewidth`:     The width of a tile in mm, tile height will be calculated from the aspect ratio of your area.

 * `printres`:      A realistic resolution for your printer along the buildplate, typically around the 
                    thickness of the filament. This and the tile width determines the resampled resolution of the DEM 
                    raster that is the basis of the mesh. E.g. if you want your tile to be 100 mm wide and your printres 
                    is set to 0.25 mm, the DEM raster will be re-sampled from its original resolution to 
                    the equivalent of 400 cells.
                    If the tile is 4000 m wide in reality, each cell would cover 10 m, about the resolution of NED.
                    It is probably pointless to ask for a resolution below the origonal DEM by lowering printres
                    to less than 0.25 in this case.
                  
 * `tile_centered`: 
   * True:  each tile is centered around 0/0
   * False: all tiles are offset so the all "fit together" when the all are loaded into a 3D viewer, such as Meshlab

 * `zip_file_name`: Prefix of output filename. The end is the datetime of the
                    file's creation.

 * `zscale`:        Vertical exaggeration versus horizontal units.


* A note on distances: Google Earth Engine requires that the requested area is given in lat/lon coordinates but it's worth knowing the approximate real-world meter distance in order to select good values for the tile width, number of tiles and the printres. The server version displays the tile width in Javascript but for the standalone version you need to calculate it yourself. This haversine distance (https://en.wikipedia.org/wiki/Haversine_formula, interactive calulator here: http://www.movable-type.co.uk/scripts/latlong.html) depends on the latitude of your area. Once you know the width of your tile in meters divide it by the number of cells along x (400 cells in the example above) to get an idea of the re-sampled real-world resolution of your model and its scale. The server Help file (https://docs.google.com/document/d/1GlggZ47xER9N85Qls_MiE1jNuihlYEZnFFSVZtX8bKU/pub) goes into the interplay of these parameters in the section: Understanding the linkage of tile size, tile number, source DEM resolution and 3D print resolution




Server
======

Running `TouchTerrain_app.py` starts a server module (service) to be run as part
of a Google App Engine server. The server creates a webpage, through which the
user inputs the area selection and print parameters.

The server requires that the file `config.py` be edited to appropriate values.
The server also requires oauth authentication to run with Earth Engine. You will
need to obtain a private key (`.pem`) file and edit `config.py` to point to it.

The server presents users with `index.html`, which can be styled to suit your
needs, provided the various input dialogs and JavaScript remain.



Common
======

The `common` directory contains files used by both the standalone and server
apps.
