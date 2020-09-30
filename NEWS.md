Sep. 30, 2020 (3.0.0 alpha)
	- Rewrote GUI to use Bootstrap 4
	- Added place search bar

Sep. 7, 2020 (2.5.2)
	- Added upload of kml file with masking polygon to server version 
	- Added option to jupyter notebook to use geemap for digitizing a rectangle, circle or polygon and use it. If gpx files are used. they are also shown on the geemap

Aug. 28, 2020
	- Thanks to github.com/KohlhardtC, who added a module to drape GPX path lines over the terrain
	- added a test folder with unittests

May. 7, 2020:
- pretty massive restructuring of folders:
	- no more standalone folder, the "main" code files (TouchTerrain_standalone_jupyter_notebook.ipynb and TouchTerrain_standalone.py) are now in root
	- common and server folders are now in a new touchterrain folder
	- the eloquently named new stuff folder contains all helper files, e.g. json and getiff examples
- the vectors module (by allelos) was moved into common to remove some install trickery. It will sit there for the future, I don't anticipate any need to go to a new version (Python 4?)
- running setup.py will now build and install a __touchterrain module__ (versioning coming soon)
- use pip install .  (dot!) to have pip install it for you (better than python setup.py install clean)
- all imports were re-written to import from the installed touchterrain module (e.g. touchterrain.common.config)
	

Apr. 23, 2020: added lower_leq manual option to lower any cells below a threshold by a offset in mm. (thanks to idenc, who did nearly all the work!)

Apr. 19, 2020: added hillshade settings for azimuth and elevation angles in the GUI. Gamma is linked to changes of these settings.

Mar. 31, 2020: fixed issues arising from changes in Earth Engine API 

Mar. 16, 2020: Took out the source option for print resolution b/c the d/l size restrictions of new Mar 2020 EarthEngine API update.

Mar 2020: added use_geo_coords

Aug. 2019: Version 2.0
- 3D preview using JS
- Wait animation
- Optional feedback box
- added geotiff of full tile to d/l zip
- print resolution can be same as source (Mar 2020: only for stand alone!)
- more precise model dimensions

Apr. 19. 2019
- moved to Python 3

Mar. 5. 2019
- added support for both .pem files or .config/earthengine/credentials for authentication


Mar.1, 2019

Both versions:
- Added "only":[x,y] manual option, if given (not None/null) will only process that tile index ([1,1] is upper left tile). This will enable users to request unreasonably large models (with too many total cells to be processed by the server) by processing only one of the tiles (thus staying under the limit). Once this is downloaded, the next single tile can be processed. These separately d/l tiles will fit together, provided the same URL (settings) where otherwise used. (Only works for meshes, not for GeoTiff-only d/l!)
- switched to a proper logging based log file (..._logfile.txt) instead of redirecting stdout into a file
- authentication for .pem files was removed (no config.py needed any more). Now uses ~/.config/earthengine/credentials (thanks to Jeff Swayze!)
- EE rasters tile should now connect perfectly

Standalone only:
- added a inlined dict to overwrite default settings if no JSON file was given (TouchTerrain_standalone.py)
- added a jupyter notebook that can be run instead of TouchTerrain_standalone.py


Jan. 3, 2019:

Both versions:
- Can export to GeoTiff only, w/o creating a mesh file
- Can use the original resolution of the dem raster. Server has a limit check, which is much less strict when exporting only the geotiff
- Arctic/Antarctic regions use Polar stereographic projections (m based) instead of UTM
- manual field can contain JSON style manual options (comma separated):
  "ignore_leq":0.0    ignores elevations <= 0.0, useful for coastlines
  "unprojected":true  omits projection into UTM, Can only be used for GeoTiff export
  "no_bottom":true    bottom triangles not written in STL/OBJ file
- any other UI setting can be overridden e.g. "printres":0.37 sets the print resolution to 0.37, which can not be done via the GUI. For names of settings see standalone JSON config file

Standalone only:
- local geotiffs can be masked by a polygon and contain undefined/NoData values. Those values will be omitted in the STL/OBJ file. Note that extreme values (e.g. -9999999) will also be interpreted as undefined.


Sep. 25:
added optional Google Maps key. If a file called GoogleMapsKey.txt in the serve folder contains a valid google maps key, it will be inlined into index.html which should result in a proper Google Map. Not having this file will result in a  Google Map that's crappy but still works. Having a invalid key will result in no map at all.

Sept. 18:
- fixed bug where the print resolution was wrong in some cases when multiple tiles are used
- added the geotiff I get from Google Earth Engine to the zipped folder as DEM.tif

August 29:
- both: set resample mode for GEE to bilinear (from nearest neighbor), which was creating aliasing artifacts when projecting/resampling. Standalone resampling is still nearest neighbor.
- standalone: printers = -1 for using the original raster file resolution


April 4, 2018:
- server: added MAX_LOAD factor which prevents running of large jobs, that would requite too much memory.
- standalone: added max_cells_for_memory_only for use of tempfiles instead of in-memory for processing large rasters.

Feb. 14, 2018:
- added the use of tempfiles instead of in-memory for processing large rasters
- config settings/constants are now in common/touchterrain_config.py

Jan. 12, 2018:
- added code for zigzag magic (currently disabled). May help to prevent curling corners.
- vertex indexing is now only done for obj, not for STL

Dec. 05, 2017:
- Cleaned up index.html.
- Added getting area box from kml file.
- All GUI options are now put in URL.
- Changed tile width/height from cm to mm.
- Gamma value changes now trigger refresh.

Oct. 27, 2017: server: fixed Earth engine 404 bug. Standalone: added ability to read in local geotiff file (via json config file). Added link to blog.
Aug. 14, 2017: added a show URL button to the Area UI. This will load the app (w/o changing the area!) and show the full URL in the browser. This is useful to capture the area for others to use.

Aug. 11, 2017: added multi-core processing. By default server and standalone will use all available cores. If this doesn;t work, CPU_cores_to_use can be set to 1 to go back to single-processor mode

Apr. 18, 2017: added more options to the pulldown lists for tile size and z-scale
Apr. 4: added check to convert water cells outside the defines DEM area to 0. Does not affect onshore cells with <0 elevation (e.g. holland)

Mar. 6: index.html
- added boilerplate code for google analytics. Change UA-XXXXXX to your tracking id if you want to use it
- added contact info and github URL

Feb. 16: separated standalone and server version into subfolders:
- common: .py files (modules) used by both versions
- standalone: main for standalone, install-howto, etc.. Works
- server: server main (touchterrain_app.py) and server setup files.

version 0.12 is now live at: touchterrain.geol.iastate.edu

Jan. 23: changed the order in which ee is intialized. This enables the stand alone version to use any google account for authentication, rather than having to go through config.py (server still uses config.py)

April 3, 2017:  added check to set all <0 elevations to 0 for non-bathymetry DEM sources (NED, STRM).  

0.12 (Dec. 12, 2016 - X-mas edition):
- Transparency defaults to 40%
- results page has link to viewstl.com to preview downloaded files
- ETOPO elevation is for ice, not bedrock
- can now use server type flags: Apache, paste or GEA_devserver
- added a hillshade gamma slider to change default gamma (1.0). Requires reload of page: press set new gamma button.
- added 30m SRTM DEM as data source
- better info on how the original raster DEM will be rescaled based on area, tile number/size, etc.
- tile height (in cm) is now automatically calculated from tile width and aspect ratio of red box (using meters for box sides).
- general layout changes, incl. a link to help page.

0.11 (Oct. 31, 2016 - Halloween edition): Includes Levi's changes/fixes/additions:
- proper separation of server vs stand-alone:
- stand-alone version can now be run without having to install the google app engine (GAE) modules
- full server now runs on Apache mod_wsgi, rather than via the Google App Engine dev server. However, the GAE modules still need to be installed, as some parts are used by the server module.
- fixed a noobish use of a Python global for duplicating request_handling data for the pre-flight page


Version 0.10 of the TouchTerrain project, primarily a set of python source code files for Python 2.7:

- TouchTerrain-app.py: a server module (service) to be run as part of a Google App Engine server. The server creates a webpage, through which the user inputs the area selection and print parameters.
- index.html: HTML template for the main webpage, includes Javascript
- TouchTerrain_standalone.py: A stand-alone version in which the user input is given
    in a JSON file, rather then via a web page.
- TouchTerrainEarthEngine.py: With the user input, gets the DEM raster (geotiff) from the Google Earth Engine data server and, using the grid class, creates the 3D models (tiles).
- grid_tesselate.py: defines the grid class used to create a triangle "mesh" and save it in the desired file format (STL or OBJ)
- Coordinate_system_conv.py, InMemoryZip.py: utility functions  
- config.py: used for oauth credentials for the Google dev (Earth Engine) account
- tmp folder: contains an example terrain model, a zipped stl file
