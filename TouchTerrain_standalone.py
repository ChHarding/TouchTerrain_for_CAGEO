"""
TouchTerrain_standalone

USAGE: python TouchTerrain_standalone.py config.json

parses the JSON file config.json, downloads terrain raster via Earth Engine,
processes it into tiles and saves them in a zip file. 
Alternative to running the TouchTerrain web server.
"""

'''
@author:     Chris Harding
@license:    GPL
@contact:    charding@iastate.edu

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

#
# How to run the standalone version:
# 

# Install google app_engine and put this folder into it (google_appengine\this_folder)
#
# Although this standalone version doesn't actually run a sever, it still 
# needs access to some of the google apps modules. Set this to point to your
# google_appengine folder:
import sys;sys.path.append(r"C:\Program Files (x86)\Google\google_appengine") 

# Get a google dev account, set up a google earth engine project. 
# Modify the settings in config.py. Put your public key file (.pem) into this folder.

# Make a copy of example_config.json, modify the parameters and save it with a new
# name (e.g. my.json). The JSON file format follows the args dict shown below.
#
# run python with your JSON file as the only arg:
#
# python TouchTerrain_standalone.py my.json
#
# This will authenticate with Google EE, request the specific raster, covert it
# into one or more 3D model files (tiles) and store it/them as a zipped folder.

# Default parameters:
# The JSON file overwrites values for the following keys, which are used as
# args for get_zipped_tiles() and save them inside a zipped folder. 
# Print each tile on a 3D printer (they are already scaled!)

import time
import json

args = {
"DEM_name": 'USGS/NED',# DEM_name:  name of DEM source used in Google Earth Engine 
                       # for all valid sources, see DEM_sources in TouchTerrainEarthEngine.py
"trlat": 44.69741706507476,     # lat/lon of top right corner
"trlon": -107.97962089843747,
"bllat": 44.50185267072875,     # lat/lon of bottom left corner
"bllon": -108.25427910156247, 
"printres": 0.5,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
"ntilesx": 1,     # number of tiles in x and y
"ntilesy": 1, 
"tilewidth": 80, # width of each tile in mm (<- !!!!!), tile height is calculated
"basethick": 1, # thickness (in mm) of printed base
"zscale": 1.0,    # elevation (vertical) scaling
"fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
"tile_centered": True, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
"zip_file_name": "terrain"   # base name of zipfile, a timestamp and .zip will be added  
}

# write an example json file, in case it gets deleted ...
with open('example_config.json', 'w+') as fp: 
    json.dump(args, fp, indent=0, sort_keys=True) # indent = 0: newline after each comma
print "Wrote example_config.json with default value, use it as a template but make sure to rename it!"



import config # this needs to be set up for your dev account and needs a .pem file
import ee

import TouchTerrainEarthEngine as TouchTerrain 
from InMemoryZip import InMemoryZip



if len(sys.argv) > 1:  # sys.argv are the CLI args
    json_fname = sys.argv[1]
    try:
	fp = open(json_fname, "rU")
	json_args = json.load(fp)
    except:
	sys.exit("Error: config file", json_fname, "not found")
    print "reading", json_fname
    
    for k in args.keys():
	try:
	    args[k] = json_args[k]  # try to find a value for k in json config file
	except:
	    print "warning: ignored invalid option", k   # no match, no problem, just keep the default value
	print "%s = %s" % (k, str(args[k]))
else:
    print "no config file given, using defaults:"
    for k in args.keys():
	print "%s = %s" % (k, str(args[k]))
    
fname = args["zip_file_name"] + "_" + time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime()) + ".zip"
del args["zip_file_name"] # otherwise get_zipped_tiles complains about this argument
	
str_buf = TouchTerrain.get_zipped_tiles(**args) # all args are in a dict
with open(fname, 'wb+') as fp: 
    fp.write(str_buf)
    print "finished writing %s" % (fname)	
    
