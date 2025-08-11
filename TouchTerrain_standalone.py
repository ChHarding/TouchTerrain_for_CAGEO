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
    from touchterrain.common.user_config import TouchTerrainConfig
except Exception as e:
    print(e)
    print("Error: touchterrain module is not installed. Use pip install . in the same folder as setup.py")
    sys.exit()

#
# How to run the standalone version:
#

# A) Go to the overwrite_args section (line 136) below and change the settings there, then run this file. 
#
# B) Make a copy of example_config.json (in the stuff folder), modify the parameters and save it with a new
#    name (e.g. my.json) in the same folder as this .py file. The JSON file format follows the args dict shown below.
#
#    run python with your JSON file as the only arg, e.g.:
#
#    python TouchTerrain_standalone.py my.json
#

# main function, will be called at the end of the script
def main():

    default_args = TouchTerrainConfig()

    # Fill args dict with the bare minimum of default values
    args = {
        "importedDEM": default_args.importedDEM,
        "importedDEM_interp": default_args.importedDEM_interp,
        "offset_masks_lower": default_args.offset_masks_lower
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
    
        for k in list(json_args.keys()):
            args[k] = json_args[k]    # try to find a user set value for k in json config file

    # else:
    #     # no JSON config file given, setting config values in code
    #     # you can comment out lines for which you don't want to overwrite the default settings
        
    #     # overwrite settings in args
    #     for k in default_args:
    #         args[k] = default_args[k]
       
    
    # print out current args 
    print("\nUsing these config values:")
    for k in sorted(args.keys()):
        print("%s = %s" % (k, str(args[k])))
    
    # for local DEM, get the full path to it
    if not args["importedDEM"] == None:
        args["importedDEM"] = abspath(args["importedDEM"])
        
    # for local DEM, get the full path to it
    if not args["importedDEM_interp"] == None:
        args["importedDEM_interp"] = abspath(args["importedDEM_interp"])

    # get full path to offset mask TIFF
    if not args["offset_masks_lower"] == None and len(args["offset_masks_lower"]) > 0:
        for offset_mask_pair in args["offset_masks_lower"]:
            offset_mask_pair[0] = abspath(offset_mask_pair[0])

    # Give all config values to get_zipped_tiles for processing:
    totalsize, full_zip_file_name = TouchTerrain.get_zipped_tiles(args) # all args are in a dict
    print("\nCreated zip file", full_zip_file_name,  "%.2f" % totalsize, "Mb")
    
    # Optional: unzip the zip file into the current folder
    if 1: # set this to 0 if you don't want the zip file to be unzipped
        #import os.path
        #folder, file = os.path.splitext(full_zip_file_name) # tmp folder
        folder = os.getcwd() + os.sep + args["zip_file_name"]# new stl folder in current folder
        
        # unzip the zipfile into the folder it's already in
        import zipfile
        zip_ref = zipfile.ZipFile(full_zip_file_name, 'r')
        zip_ref.extractall(folder)
        zip_ref.close()
        print("unzipped file inside", full_zip_file_name, "into", folder)
    
    # # Optional: show the STL files in a browser
    # import k3d
    # # get all stl files in that folder
    # from glob import glob
    # mesh_files = glob(folder + os.sep + "*.stl")
    # print("in folder", folder, "using", mesh_files)
    
    # plot = k3d.plot()
    
    # for m in mesh_files:
    #     print(m)
    #     buf = open(m, 'rb').read()
    #     #buf = str(stl_model)
    #     #buf = buf.encode('utf_32')
    #     print(buf[:100])
    #     plot += k3d.stl(buf)
    
    # plot.display()

    

if __name__ == "__main__":
    
    # this is/should only be needed on Windows and only if we do multi processing
    # but it has to be done before we know if MP is actually used
    from multiprocessing import freeze_support
    freeze_support()
    main()
