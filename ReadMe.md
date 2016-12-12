0.12 (Dec. 12 - X-mas edition): 
- can now use server tyep flags: Apache, paste or GEA_devserver
- added a hillshade gamma slider to change default gamma (1.0). Requires reload of page: press set new gamma button.
- added 30m SRTM DEM as data source
- better info on how the original raster DEM will be rescaled based on area, tile number/size, etc. 
- tile height (in cm) is now automatically calculated from tile width and aspect ratio of red box (using meters for box sides).
- general layout changes, incl. a link to help page.

0.11 (Oct. 31 - Halloween edition): Includes Levi's changes/fixes/additions:
- proper separation of server vs stand-alone:
- stand-alone version can now be run without having to install the google app engine (GAE) modules
- full server now runs on Apache mod_wsgi, rather than via the Google App Engine dev server. However, the GAE modules still need to be installed, as some parts are used by the server module.
- fixed a noobish use of a Python global for duplicating request_handling data for the pre-flight page


Version 0.10 of the TouchTerrain project, primarily a set of python source code files
for Python 2.7:

- TouchTerrain-app.py: a server module (service) to be run as part of a Google App Engine server. The server creates a webpage, through which the user inputs the area selection and print parameters.
    
- index.html: HTML template for the main webpage, includes Javascript
    
- TouchTerrain_standalone.py: A stand-alone version in which the user input is given 
    in a JSON file, rather then via a web page.
    
- TouchTerrainEarthEngine.py: With the user input, gets the DEM raster (geotiff) from the Google Earth Engine data server and, using the grid class, creates the 3D models (tiles).
    
- grid_tesselate.py: defines the grid class used to create a triangle "mesh" and save it in the desired file format (STL or OBJ)
    
- Coordinate_system_conv.py, InMemoryZip.py: utility functions  

- config.py: used for oauth credentials for the Google dev (Earth Engine) account 

- tmp folder: contains an example terrain model, a zipped stl file 

Note that running the server or the stand-alone version does require some additional setup,
it cannot be run right away with just those files! 
https://developers.google.com/earth-engine/python_install describes the setup of 
the Earth Engine Python API, including the required oauth authentication to the Earth Engine. 
This will create a credentials file on your system and a private key (.pem) file that are 
needed by config.py. You will also need to install all required third party modules, 
such as numpy and pillow.



