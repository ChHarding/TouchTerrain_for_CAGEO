"""TouchTerrain-app - a server module"""

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

import math
import os
from datetime import datetime
import json
import ee

import common
import server

from server import config  # sets location of .pem file

from server import app

from flask import stream_with_context, request, Response

# Google Maps key file: must be called GoogleMapsKey.txt and contain a single string
google_maps_key = ""
try:
    with open(config.GOOGLE_MAPS_KEY_FILE) as f:
        google_maps_key = f.read().rstrip()
        if google_maps_key == "Put your Google Maps key here":
            google_maps_key = ""
        else:
            print("Google Maps key is:", google_maps_key)
            pass
except:
    pass # file does not exist - will show the ugly Google map version 
  

from server.touchterrain_config import *  # Some server settings, touchterrain_config.py must be in this folder

# import module from common
import sys
from os.path import abspath, dirname
top = abspath(__file__)
this_folder = dirname(top)
tmp_folder = this_folder + os.sep + "tmp"  # dir to store zip files and temp tile files

from common import TouchTerrainEarthEngine
from common.Coordinate_system_conv import * # arc to meters conversion

#import webapp2


from flask import Flask, request
app = Flask(__name__)



import jinja2
jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
import logging
import time



# functions for computing hillshades in EE (from EE examples)
# Currently, I only use the precomputed hs, but they might come in handy later ...
def Radians(img):
  return img.toFloat().multiply(math.pi).divide(180)

def Hillshade(az, ze, slope, aspect):
  """Compute hillshade for the given illumination az, el."""
  azimuth = Radians(ee.Image(az))
  zenith = Radians(ee.Image(ze))
  # Hillshade = cos(Azimuth - Aspect) * sin(Slope) * sin(Zenith) +
  #     cos(Zenith) * cos(Slope)
  return (azimuth.subtract(aspect).cos()
          .multiply(slope.sin())
          .multiply(zenith.sin())
          .add(
              zenith.cos().multiply(slope.cos())))






#
# The page for selecting the ROI and putting in printer parameters
#

@app.route("/", methods=["GET"]) 
def main_page():
    # example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247&hs_gamma=1.0
   
    # try both ways of authenticating
    try:
        ee.Initialize() # uses .config/earthengine/credentials
    except Exception as e:
        print("EE init() error (with .config/earthengine/credentials)", e, ", trying .pem file", file=sys.stderr)
 
        try:
            # try authenticating with a .pem file
            ee.Initialize(config.EE_CREDENTIALS, config.EE_URL)
        except Exception as e:
            print("EE init() error with .pem file", e, file=sys.stderr)      
    
    # init all browser args with defaults, these must be strings and match the SELECT values
    args = {
        'DEM_name': 'USGS/NED',
    
        # defines map location
        'map_lat': "44.59982",
        'map_lon': "-108.11695",
        'map_zoom': "11",
    
         # defines area box
        'trlat' : "",
        'trlon' : "",
        'bllat' : "",
        'bllon' : "",
    
        # 3D print parameters
        "printres": "0.5",
        "ntilesx" : "1",
        "ntilesy" : "1",
        "tilewidth" : "80",
        "basethick" : "1",
        "zscale" : "1.0",
        "fileformat" : "STLb",
    
        "hsgamma": "1.0",
        
        "google_maps_key": google_maps_key,  # '' or a key, if there was a key file
    }    
    
    #re-assemble the URL query string and store it , so we can put it into the log file
    qs = "?"    
    for k,v in list(request.args.items()):
        v = v.replace('\"', '&quot;')
        qs = qs + k + "=" + v + "&"
    #print qs   

    
    # overwrite args with values from request
    for key in request.args:
        args[key] = request.args[key]
        #print(key, request.args[key])
            
    # convert " to &quot; for URL
    if args.get("manual") != None:
        args["manual"] = args["manual"].replace('\"', '&quot;')
 
    # for ETOPO1 we need to first select one of the two bands as elevation
    if args["DEM_name"] == """NOAA/NGDC/ETOPO1""":
        img = ee.Image(args["DEM_name"])
        elev = img.select('bedrock') # or ice_surface
        terrain = ee.Terrain.products(elev)
    else:
        terrain = ee.Algorithms.Terrain(ee.Image(args["DEM_name"]))

    
    hs = terrain.select('hillshade')
    
    gamma = float(args["hsgamma"])
    mapid = hs.getMapId( {'gamma':gamma}) # opacity is set in JS
    
    # these have to be added to the args so they end up in the template
    # 'mapid': mapid['mapid'],
    # 'token': mapid['token'],
    
    args['mapid'] = mapid['mapid']
    args['token'] = mapid['token']
    
    # this creates a index.html "file" with mapid, token, etc. inlined
    template = jinja_environment.get_template('index.html')
    html_str = template.render(args)
    return html_str



# Page that creates the 3D models (tiles) in a in-memory zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file. 
# Needs to use the args from preflight 
@app.route("/export", methods=["POST"]) 
def export():

    def preflight_generator():
        # create html
        html =  '<html>'
        html += """
        <script type="text/javascript">  
        function show_gif(){
            // hide submit button
            let f = document.forms["export"];
            f.style.display='none'

            // unhide gif
            let gif = document.getElementById('gif');
            gif.style.display = 'block';

            f.submit();
        }      
        </script>
        """    
        html += '<body>'
        html += "<h2>Processing terrain data into 3D print file(s):</h2>"
        html += "This may take some time, please be patient! <br>"
        #html += "Press the Start button to process the DEM into 3D model files.<br>"
        #html += "Note that there's NO progress indicator (yet), you will only see this page trying to connect. That's OK, just be patient!<br>"
        #html += "Pressing Start again during processing has no effect.<br>"
        #html += "Once your 3D model is created, you will get a new page (Processing finished) for downloading a zip file.<br><br>"
        #html += '<form action="/export" method="POST" enctype="multipart/form-data">'
        #html += '<input type="hidden" maxlength="50" size="20" name="Note" id="Note" value="NULL">' # for user comment
        #html += '<input type="hidden" name="prog_pct" id="prog_pct" value="0">') # progress percentage
        #html += '<input type="submit" value="Start"> </form>'
        #html += '<img src="static/gears.gif" alt="gears.gif">' 

        html += """
        Once your 3D model is created, you will get a new page (Processing finished) for downloading a zip file.<br>
        <img src="static/processing.gif" id="gif" alt="processing" style="display: none;">
        """

        yield html
    
        html += '<h2>Processing finished:</h2>'

        #
        # debug: print/log all args and their values
        #

        # using a list here to preserve the order when printing them out to the user
        key_list = ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres", 
                  "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat")
        args = request.form.to_dict() # put arg name and value in a dict as key:value
        for k in key_list:
            if k not in ["DEM_name", "fileformat"]: 
                args[k] = float(args[k]) # floatify non-string args
            print(k, args[k])

        # decode any extra (manual) args and put them in args dict
        #print(app.preflight_args_dict)
        manual = args.get("manual", None)
        extra_args={}
        if manual != None:
            JSON_str = "{ " + manual + "}" 
            try:
                extra_args = json.loads(JSON_str)
            except Exception as e:
                logging.error("JSON decode Error for: " + manual + "   " + str(e))
                print(e)
            else:
                for k in extra_args:
                    args[k] = extra_args[k] # append/overwrite
                    # TODO: validate  

        # log and show args in browser
        for k in key_list:
            html += "%s = %s <br>" % (k, str(args[k]))
            logging.info("%s = %s" % (k, str(args[k])))
        html += "<br>"
        for k in extra_args:
            html += "%s = %s <br>" % (k, str(args[k]))
            logging.info("%s = %s" % (k, str(args[k])))        
        html += "<br>"

        #
        # bail out if the raster would be too large
        #

        # ???
        from server.touchterrain_config import MAX_CELLS_PERMITED # WTH? If I don't re-import it here I get:UnboundLocalError: local variable 'MAX_CELLS_PERMITED' referenced before assignment 
        # ???        

        width = args["tilewidth"]
        bllon = args["bllon"]
        trlon = args["trlon"]
        bllat = args["bllat"]
        trlat = args["trlat"]
        dlon =  180 - abs(abs(bllon - trlon) - 180) # width in degrees
        dlat =  180 - abs(abs(bllat - trlat) - 180) # height in degrees
        center_lat = bllat + abs((bllat - trlat) / 2.0)
        latitude_in_m, longitude_in_m = arcDegr_in_meter(center_lat)
        num_total_tiles = args["ntilesx"] * args["ntilesy"]
        pr = args["printres"]

        # if we have "only" set, divide load by number of tiles
        div_by = 1
        if extra_args.get("only") != None:
            div_by = float(num_total_tiles)


        # for geotiffs only, set a much higher limit b/c we don't do any processing, 
        # just d/l the GEE geotiff and zip it
        if args["fileformat"] == "GeoTiff": 
            MAX_CELLS_PERMITED *= 100                     

        # pr <= 0 means: use source 
        if pr > 0: # print res given by user (width and height are in mm)
            height = width * (dlat / float(dlon))
            pix_per_tile = (width / float(pr)) * (height / float(pr))
            tot_pix = int((pix_per_tile * num_total_tiles) / div_by) # total pixels to print
            print("total requested pixels to print", tot_pix, ", max is", MAX_CELLS_PERMITED, file=sys.stderr)
        else:
            # estimates the total number of cells from area and arc sec resolution of source
            # this is done for the entire area, so number of cell is irrelevant
            DEM_name = args["DEM_name"]
            cell_width_arcsecs = {"""USGS/NED""":1/9.0, """USGS/GMTED2010""":7.5, """NOAA/NGDC/ETOPO1""":30, """USGS/SRTMGL1_003""":1} # in arcseconds!            
            cwas = float(cell_width_arcsecs[DEM_name])
            tot_pix =    int( ( ((dlon * 3600) / cwas) *  ((dlat * 3600) / cwas) ) / div_by)
            print("total requested pixels to print at a source resolution of", round(cwas,2), "arc secs is ", tot_pix, ", max is", MAX_CELLS_PERMITED, file=sys.stderr)

        if tot_pix >  MAX_CELLS_PERMITED:
            html = "Your requested job is too large! Please reduce the area (red box) or lower the print resolution"
            html += "<br>Current total number of Kilo pixels is " + str(tot_pix / 1000.0)
            html += " but must be less than " + str(MAX_CELLS_PERMITED / 1000.0)
            html += "<br>(Hit Back on your browser to get back to the Main page)"
            yield html      


        args["CPU_cores_to_use"] = NUM_CORES

        # getcwd() returns / on Linux ????
        cwd = os.path.dirname(os.path.realpath(__file__))
        args["temp_folder"] = cwd + os.sep + TMP_FOLDER
        print("temp_folder is:", args["temp_folder"], file=sys.stderr)

        # name of zip file is time since 2000 in 0.01 seconds
        fname = str(int((datetime.now()-datetime(2000,1,1)).total_seconds() * 1000))
        args["zip_file_name"] = fname

        # if this number of cells to process is exceeded, use a temp file instead of memory only
        args["max_cells_for_memory_only"] = MAX_CELLS    

        #
        # Create zip and write to tmp
        #
        try:
            totalsize, full_zip_zile_name = TouchTerrainEarthEngine.get_zipped_tiles(**args) # all args are in a dict
        except Exception as e:
            logging.error(e)
            print(e, file=sys.stderr)
            yield "Error:" + str(e)

        # totalsize is negative, something went wrong, error message is in full_zip_zile_name
        if totalsize < 0: 
            print("Error:", full_zip_zile_name, file=sys.stderr)
            yield full_zip_zile_name
        else:    
            print(("Finished processing", full_zip_zile_name))
            html += "total zipped size: %.2f Mb<br>" % totalsize

            html +='<br><form action="tmp/%s.zip" method="GET" enctype="multipart/form-data">' % (fname)
            html +='<input type="submit" value="Download zip File " title="">   (will be deleted in 6 hrs)</form>'
            #html +='<form action="/" method="GET" enctype="multipart/form-data">'
            #html +='<input type="submit" value="Go back to selection map"> </form>'
            html +="<br>To return to the selection map, click the back button in your browser twice"
            html += """<br>After downloading you can preview a STL/OBJ file at <a href="http://www.viewstl.com/" target="_blank"> www.viewstl.com ) </a>  (limit: 35 Mb)"""   

            yield html
    return Response(stream_with_context(preflight_generator()), mimetype='text/html')
    
#print "end of TouchTerrain_app.py"
