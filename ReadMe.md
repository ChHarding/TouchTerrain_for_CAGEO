TouchTerrain
============

TouchTerrain converts digital elevation models drawn from Google Earth Engine,
or user provided files, into models suitable for 3D printing. It comes as both a
standalone program as well as a server which creates 3D model files and makes
them available for download.

TouchTerrain is developed by Chris Harding and Franek Hasiuk, of Iowa State
University's [GeoFabLab](http://www.public.iastate.edu/~franek/gfl/gfl.html).



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

 * `DEM_name`:      ????

 * `basethick`:     A layer of material this thick will be added below the 
                    entire model. This is particularly important for models 
                    with long, deep valleys, which can cause the model to break 
                    if the base is not thick enough.

 * `bllat`:         Bottom-left latitude

 * `bllon`:         Bottom-left longitude

 * `fileformat`:    ????

 * `ntilesx`:       Divide the x axis evenly among this many tiles. This is
                    useful if the area being printed would be too large to fit
                    in the printer's bed.

 * `ntilesy`:       See `ntilesx`, above.

 * `printres`:      ????

 * `tile_centered`: ????

 * `tilewidth`:     ????

 * `trlat`:         Top-right latitude

 * `trlon`:         Top-right longitude

 * `zip_file_name`: Prefix of output filename. The end is the datetime of the
                    file's creation.

 * `zscale`:        Vertical exaggeration versus horizontal units.



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
