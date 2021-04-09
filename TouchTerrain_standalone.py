#!/usr/bin/env python

"""
TouchTerrain_standalone

USAGE: python TouchTerrain_standalone.py config.json

parses the JSON file config.json, downloads terrain raster via Earth Engine,
processes it into tiles and saves them in a zip file.
Alternative to running the TouchTerrain web server.
"""

'''
@author:     Chris Harding
@license:     GPL
@contact:     charding@iastate.edu

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
  GNU General Public License for more details.
  You should have received a copy of the GNU General Public License
  along with this program.    If not, see <http://www.gnu.org/licenses/>.
'''
import time
import json
import sys, os
from os.path import abspath, dirname

try:
    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain
    from touchterrain.common.TouchTerrainGPX import *
except:
    print("Error: touchterrain module is not installed. Use pip install . in the same folder as setup.py")
    sys.exit()


#
# How to run the standalone version:
#

# Make a copy of example_config.json (in the stuff folder), modify the parameters and save it with a new
# name (e.g. my.json) in the same folder as this .py file. The JSON file format follows the args dict shown below.
#
# run python with your JSON file as the only arg, e.g.:
#
# python TouchTerrain_standalone.py my.json
#

# main function, will be called at the end of the script
def main():

    # Default parameters:
    # The JSON file overwrites values for the following keys, which are used as
    # args for get_zipped_tiles() and save them inside a zipped folder.
    # Print each tile on a 3D printer (they are already scaled!)
    args = {
        "DEM_name": 'USGS/NED',# DEM_name:    name of DEM source used in Google Earth Engine
                            # for all valid sources, see DEM_sources in TouchTerrainEarthEngine.py
        "trlat": 44.69741706507476,        # lat/lon of top right corner
        "trlon": -107.97962089843747,
        "bllat": 44.50185267072875,        # lat/lon of bottom left corner
        "bllon": -108.25427910156247,
        "poly_file": None, # path to a local kml file
        "polyURL": None, # URL to a publicly readable(!) kml file on Google Drive
        "importedDEM": None, # if not None, the raster file to use as DEM instead of using GEE (null in JSON)
        "printres": 0.5,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
        "ntilesx": 1,      # number of tiles in x and y
        "ntilesy": 1,
        "tilewidth": 80, # width of each tile in mm (<- !!!!!), tile height is calculated
        "basethick": 1, # thickness (in mm) of printed base
        "zscale": 1.0,      # elevation (vertical) scaling
        "fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
        "tile_centered": False, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
        "zip_file_name": "terrain",   # base name of zipfile, .zip will be added
        "CPU_cores_to_use" : 0,  # 0 means all cores, None (null in JSON!) => don't use multiprocessing
        "max_cells_for_memory_only" : 1000 * 1000, # if raster is bigger, use temp_files instead of memory
        
        # these are the args that could be given "manually" via the web UI
        "no_bottom": False, # omit bottom triangles?
        #"rot_degs": 0, # rotate by degrees ccw  # CH disabled for now
        "bottom_image": None,  # 1 band greyscale image used for bottom relief
        "ignore_leq": None, # set values <= this to NaN, so they are ignored
        "lower_leq": None,  # e.g. [0.0, 2.0] values <= 0.0 will be lowered by 2mm in the final model
        "unprojected": False, # don't project to UTM, only usefull when using GEE for DEM rasters
        "only": None,# list of tile index [x,y] with is the only tile to be processed. None means process all tiles (index is 1 based)
        "importedGPX": None, # Plot GPX paths from files onto the model.
        "gpxPathHeight": 100,  # Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon,
                               # therefore this is in meters. Negative numbers are ok and put a dent in the mdoel
        "gpxPixelsBetweenPoints" : 20, # GPX Files haves a lot of points. A higher number will create more space between lines drawn
                                       # on the model and can have the effect of making the paths look a bit cleaner
        "gpxPathThickness" : 5, # Stack parallel lines on either side of primary line to create thickness.
    }

    # write an example json file, in case it gets deleted ...
    with open('example_config.json', 'w+') as fp:
        json.dump(args, fp, indent=0, sort_keys=True) # indent = 0: newline after each comma
    print('Wrote example_config.json with default values, you can use it as a template but make sure to rename it!')
    
    
    
    # parse args
    if len(sys.argv) > 1:  # sys.argv are the CLI args
        json_fname = sys.argv[1]
        try:
            fp = open(json_fname, "r")
        except Exception as e:
            sys.exit("Error: can't find " + json_fname + ": " + str(e))
    
        file_content = fp.read()
        try:
            json_args = json.loads(file_content)
        except Exception as e:
            sys.exit("Error: can't json parse " + json_fname + ": " + str(e))
    
        print("reading", json_fname)
    
        for k in list(args.keys()):
            try:
                args[k] = json_args[k]    # try to find a value for k in json config file
                #print k, args[k]
            except:
                print("info:", k, "has missing or invalid value, using defaults where possible")     # no match? no problem, just keep the default value
                #print "%s = %s" % (k, str(args[k]))
    else:
        # no JSON config file given, setting config values in code
        # you can comment out lines for which you don't want to overwrite the default settings
        overwrite_args = {
            "DEM_name": 'USGS/NED',# DEM_name:    name of DEM source used in Google Earth Engine
                                   # for all valid sources, see DEM_sources in TouchTerrainEarthEngine.py
            "trlat": 44.69741706507476,        # lat/lon of top right corner
            "trlon": -107.97962089843747,
            "bllat": 44.50185267072875,        # lat/lon of bottom left corner
            "bllon": -108.25427910156247,
            "importedDEM": None, # if not None, the raster file to use as DEM instead of using GEE (null in JSON)
            "printres": 0.5,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
            "ntilesx": 1,      # number of tiles in x and y
            "ntilesy": 1,
            "tilewidth": 80, # width of each tile in mm (<- !!!!!), tile height is calculated
            "basethick": 1, # thickness (in mm) of printed base
            "zscale": 1.0,      # elevation (vertical) scaling
            "fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
            "tile_centered": False, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
            "zip_file_name": "terrain",   # base name of zipfile, .zip will be added
            "CPU_cores_to_use" : 0,  # 0 means all cores, None (null in JSON!) => don't use multiprocessing
            "max_cells_for_memory_only" : 1000 * 1000, # if raster is bigger, use temp_files instead of memory
            "no_bottom": False, # omit bottom triangles?
            #"rot_degs": 0, # rotate by degrees ccw  # CH disabled for now
            "bottom_image": None,  # 1 band greyscale image used for bottom relief
            "ignore_leq": None, # set values <= this to NaN, so they are ignored
            "lower_leq": None,  # e.g. [0.0, 2.0] values <= 0.0 will be lowered by 2mm in the final model
            "unprojected": False, # don't project to UTM, only usefull when using GEE for DEM rasters
            "only": None,# list of tile index [x,y] with is the only tile to be processed. None means process all tiles (index is 1 based)
            "poly_file": None, #"idaho.kml", #TT_poly_test.kml",
            "smooth_borders": True, # smooth borders
        }

        # overwrite config settings in args
        for k in overwrite_args:
            args[k] = overwrite_args[k]
       
    # CH testing gpx here, so I can use the debugger
    '''
    args = {
                "importedDEM": None,
                "DEM_name": "USGS/NED",   # DEM source
                # area for gpx test
                "bllat": 39.32205105794382,   # bottom left corner lat
                "bllon": -120.37497608519418, # bottom left corner long
                "trlat": 39.45763749030933,   # top right corner lat
                "trlon": -120.2002248034559, # top right corner long
                "tilewidth": 120,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_get_zipped_tiles_gpx",   # base name of zipfile, .zip will be added
                "importedGPX": # Plot GPX paths from these files onto the model.
                            ["stuff/gpx-test/DLRTnML.gpx",
                            "stuff/gpx-test/DonnerToFrog.gpx",
                            "stuff/gpx-test/CinTwistToFrog.gpx",
                            "stuff/gpx-test/sagehen.gpx",
                            "stuff/gpx-test/dd-to-prosser.gpx",
                            "stuff/gpx-test/alder-creek-to-crabtree-canyon.gpx",
                            "stuff/gpx-test/ugly-pop-without-solvang.gpx",
                            "stuff/gpx-test/tomstrail.gpx"   
                            ],
                "gpxPathHeight": 100,  # Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon,
                                    # therefore this is in meters. Negative numbers are ok and put a dent in the mdoel  
                "gpxPixelsBetweenPoints" : 20, # GPX Files haves a lot of points. A higher number will create more space between lines drawn
                                                # on the model and can have the effect of making the paths look a bit cleaner 
                "gpxPathThickness" : 5, # Stack parallel lines on either side of primary line to create thickness. 
                                        # A setting of 1 probably looks the best 
                "smooth_borders": True, # smooth borders
    }
    
    ml = convert_to_GeoJSON(args["importedGPX"])
    '''
    
    # print out current args 
    print("\nUsing these config values:")
    for k in sorted(args.keys()):
        print("%s = %s" % (k, str(args[k])))
    
    # for local DEM, get the full path to it
    if not args["importedDEM"] == None:
        args["importedDEM"] = abspath(args["importedDEM"])

    # Give all config values to get_zipped_tiles for processing:
    totalsize, full_zip_file_name = TouchTerrain.get_zipped_tiles(**args) # all args are in a dict
    print("\nCreated zip file", full_zip_file_name,  "%.2f" % totalsize, "Mb")
    
    # Optional: unzip the zip file into the current folder
    if 1: # set this to 0 if you don't want the zip file to be unzippeed
        #import os.path
        #folder, file = os.path.splitext(full_zip_file_name) # tmp folder
        folder = os.getcwd() + os.sep + args["zip_file_name"]# new stl folder in current folder
        
        # unzip the zipfile into the folder it's already in
        import zipfile
        zip_ref = zipfile.ZipFile(full_zip_file_name, 'r')
        zip_ref.extractall(folder)
        zip_ref.close()
        print("unzipped file inside", full_zip_file_name, "into", folder)
    
    '''
    import k3d
    # get all stl files in that folder
    from glob import glob
    mesh_files = glob(folder + os.sep + "*.stl")
    print "in folder", folder, "using", mesh_files
    
    plot = k3d.plot()
    
    for m in mesh_files:
        print m
        buf = open(m, 'rb').read()
        #buf = str(stl_model)
        #buf = buf.encode('utf_32')
        print buf[:100]
        plot += k3d.stl(buf)
    
    plot.display()
    '''
    #
    # end of main()
    

if __name__ == "__main__":
    
    # this is/should only be needed on Windows and only if we do multi processing
    # but it has to be done before we know if MP is actually used
    from multiprocessing import freeze_support
    freeze_support()
    main()
