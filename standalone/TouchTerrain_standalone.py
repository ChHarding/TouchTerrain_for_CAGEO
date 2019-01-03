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

#
# How to run the standalone version:
#

# Make a copy of example_config.json, modify the parameters and save it with a new
# name (e.g. my.json). The JSON file format follows the args dict shown below.
#
# run python with your JSON file as the only arg:
#
# python TouchTerrain_standalone.py my.json
#
# Gets a geotiff either from Google Earth Engine or locally, coverts it
# into one or more 3D model files (tiles) and stores it/them in a zipped folder.
# pyramid.tif can be used to test this, use a z-scale of 0.5

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
    "importedDEM": None, # if not None, the raster file to use as DEM instead of using GEE (null in JSON)
    "printres": 0.5,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
    "ntilesx": 1,      # number of tiles in x and y
    "ntilesy": 1,
    "tilewidth": 80, # width of each tile in mm (<- !!!!!), tile height is calculated
    "basethick": 1, # thickness (in mm) of printed base
    "zscale": 1.0,      # elevation (vertical) scaling
    "fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
    "tile_centered": True, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
    "zip_file_name": "terrain",   # base name of zipfile, .zip will be added
    "CPU_cores_to_use" : 0,  # 0 means all cores, None (null in JSON!) => don't use multiprocessing
    "max_cells_for_memory_only" : 1000 * 1000, # if raster is bigger, use temp_files instead of memory
    "no_bottom": False, # omit bottom triangles?
    #"rot_degs": 0, # rotate by degrees ccw  # CH disabled for now
    "bottom_image": None,  # 1 band greyscale image used for bottom relief
    "ignore_leq": None, # set values <= this to NaN,
    "unprojected": False, # don't project to UTM, only usefull when using GEE for DEM rasters
}

# write an example json file, in case it gets deleted ...
with open('example_config.json', 'w+') as fp:
    json.dump(args, fp, indent=0, sort_keys=True) # indent = 0: newline after each comma
print 'Wrote example_config.json with default values, you can use it as a template but make sure to rename it!'


import sys, os
from os.path import abspath, dirname
top = abspath(__file__)
this_folder = dirname(top)
common_folder = dirname(this_folder) + os.sep + "common"
sys.path.append(common_folder) # add common folder to sys.path


# parse args
if len(sys.argv) > 1:  # sys.argv are the CLI args
    json_fname = sys.argv[1]
    try:
        fp = open(json_fname, "rU")
    except Exception as e:
        sys.exit("Error: can't find " + json_fname + ": " + str(e))

    file_content = fp.read()
    try:
        json_args = json.loads(file_content)
    except Exception as e:
        sys.exit("Error: can't json parse " + json_fname + ": " + str(e))

    print "reading", json_fname

    for k in args.keys():
        try:
            args[k] = json_args[k]    # try to find a value for k in json config file
            #print k, args[k]
        except:
            print "info:", k, "has missing or invalid value, using defaults where possible"     # no match? no problem, just keep the default value
            #print "%s = %s" % (k, str(args[k]))
else:
    print "no config file given, using defaults:"

for k in sorted(args.keys()):
    print "%s = %s" % (k, str(args[k]))

# No DEM file given, use Google Earth Engine
if args["importedDEM"] == None:
    # initialize ee - needs a google earth engine account! See TouchTerrain_standalone_installation.pdf
    try:
        import ee
    except Exception as e:
        print >> sys.stderr, "Google Earth Engine module not installed", e
    try:
        ee.Initialize()
    except Exception as e:
        print >> sys.stderr, "EE init() error", e
else:
    args["importedDEM"] = abspath(args["importedDEM"])

# TODO: should change TouchTerrainEarthEngine.py to TouchTerrain.py as it now also deals with file DEMs
import TouchTerrainEarthEngine as TouchTerrain

totalsize, full_zip_file_name = TouchTerrain.get_zipped_tiles(**args) # all args are in a dict
print >> sys.stderr, "Created zip file", full_zip_file_name,  "%.2f" % totalsize, "Mb"

