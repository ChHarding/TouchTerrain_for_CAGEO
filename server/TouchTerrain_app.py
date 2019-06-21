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
import sys
import common
import server

from common import config
# Some server settings
from server.config import *  

from server import app

from flask import Flask, stream_with_context, request, Response, url_for
app = Flask(__name__)


# import module from common
from common import TouchTerrainEarthEngine
from common.Coordinate_system_conv import * # arc to meters conversion

import jinja2
jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(config.SERVER_DIR))
import logging
import time

# Google Maps key file: must be called GoogleMapsKey.txt and contain a single string
google_maps_key = ""
try:
    with open(GOOGLE_MAPS_KEY_FILE) as f:
        google_maps_key = f.read().rstrip()
        if google_maps_key == "Put your Google Maps key here":
            google_maps_key = ""
        else:
            print("Google Maps key is:", google_maps_key)
            pass
except:
    pass # file does not exist - will show the ugly Google map version


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
        print("EE init() error (with .config/earthengine/credentials),", e, ", trying .pem file", file=sys.stderr)
        
        try:
            # try authenticating with a .pem file
            from oauth2client.service_account import ServiceAccountCredentials
            from ee import oauth
            credentials = ServiceAccountCredentials.from_p12_keyfile(config.EE_ACCOUNT, config.EE_PRIVATE_KEY_FILE, scopes=oauth.SCOPES)
            ee.Initialize(credentials, config.EE_URL)
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
        "printres": "0.4",
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

from zipfile import ZipFile
@app.route("/<my_zip_file>", methods=["POST", "GET"])
def preview_STL(my_zip_file):

    def preview_STL_generator():
        
        # create html string
        html = '<html>'
        
        # onload event will only be triggered once </body> is given
        html +=  '''<body onload="document.getElementById('working').innerHTML='Preview'">\n'''
        html += '<h4 id="working" >Preparing for preview, please be patient ...</h4>'
        yield html  # this effectively prints html into the browser but doesn't block, so we can keep going and append more html later ...
        
        job_id = my_zip_file[:-4]
        
        full_zip_path = os.path.join(DOWNLOADS_FOLDER, my_zip_file)
        
        # make a dir in preview to contain the STLs
        preview_dir = os.path.join(PREVIEWS_FOLDER, job_id)
        try:
            os.mkdir(preview_dir)
        except OSError as e:
            if e.errno != 17:  # 17 means dir already exists, so that error is OK
                print("Error:", e, file=sys.stderr)
                return "Error:" + str(e)     
        
        with ZipFile(full_zip_path, "r") as zip_ref:
            fl = zip_ref.namelist() # list of files   
            stl_files = []
            for f in fl:
                if ".STL" in f:
                    stl_files.append(f)
                    zip_ref.extract(f, preview_dir)
                    
                    
        if len(stl_files) == 0:
            errstr = "No STL files found in " + full_zip_path
            print("Error:", errstr, file=sys.stderr)
            return "Error:" + errstr      
    
        
        html = """
                <div id="stl_cont" style="width:100%;height:600px;margin:0 auto;"></div>
        
                <script src="static/js/stl_viewer.min.js"></script>        
                <script>
                    var stl_viewer=new StlViewer
                    (
                        document.getElementById("stl_cont"),
                        {
                            models:
                            [
                                {filename:"../preview/""" 
        html += job_id + '/' + stl_files[0] + '"'
        
        html += """, rotationx:-0.78, display:"flat"}, 
                            ],
                            load_three_files: "/static/js/", // Thanks Nick!
                            
                        }
                    );
                </script>
                
            </body>
        </html> 
        """
        yield html        

    return Response(stream_with_context(preview_STL_generator()), mimetype='text/html')

# Page that creates the 3D models (tiles) in a zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file.
@app.route("/export", methods=["POST"])
def export():

    def preflight_generator():
        
        # create html string
        html = '<html>'
        
        # onload event will only be triggered once </body> is given
        html +=  '''<body onload="document.getElementById('gif').style.display='none'; document.getElementById('working').innerHTML='Processing finished'">\n'''
        html += '<h2 id="working" >Processing terrain data into 3D print file(s)<br>'
        html += 'Please be patient.<br> Once the animation stops, you can preview and download your file.</h2>'
        yield html  # this effectively prints html into the browser but doesn't block, so we can keep going and append more html later ...


        #
        #  print/log all args and their values
        #

        
        # put all agrs we got from the browser in a  dict as key:value
        args = request.form.to_dict() 

        # list of the subset of args needed for processing 
        key_list = ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                  "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat")
    
        for k in key_list:

            # float-ify some ags
            if k in ["trlat", "trlon", "bllat", "bllon","printres", "tilewidth", "basethick", "zscale"]:
                args[k] = float(args[k])

            # int-ify some args
            if k in ["ntilesx", "ntilesy"]:
                args[k] = int(args[k])


        # decode any extra (manual) args and put them in the args dict as
        # separate args as the are needed in that form for processing
        manual = args.get("manual", None)
        extra_args={}
        if manual != None:
            JSON_str = "{ " + manual + "}"
            try:
                extra_args = json.loads(JSON_str)
            except Exception as e:
                s = "JSON decode Error for manual: " + manual + "   " + str(e)
                logging.warning(s)
                print(e)
                yield "Warning: " + s + "<br>"
            else:
                for k in extra_args:
                    args[k] = extra_args[k] # append/overwrite
                    # TODO: validate

        # log and show args in browser
        html =  '<br>'
        for k in key_list:
            html += "%s = %s <br>" % (k, str(args[k]))
            logging.info("%s = %s" % (k, str(args[k])))
        html += "<br>"
        for k in extra_args:
            html += "%s = %s <br>" % (k, str(args[k]))
            logging.info("%s = %s" % (k, str(args[k])))
        html += "<br>"
        yield html
        
        #
        # bail out if the raster would be too large
        #
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

        # ???
        #from server.touchterrain_config import MAX_CELLS_PERMITED # WTH? If I don't re-import it here I get:UnboundLocalError: local variable 'MAX_CELLS_PERMITED' referenced before assignment
        # ???


        # for geotiffs only, set a much higher limit b/c we don't do any processing,
        # just d/l the GEE geotiff and zip it
        if args["fileformat"] == "GeoTiff":
            global MAX_CELLS_PERMITED # thanks Nick!
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
            html = "Your requested job is too large! Please reduce the area (red box) or lower the print resolution<br>"
            html += "<br>Current total number of Kilo pixels is " + str(round(tot_pix / 1000.0, 2))
            html += " but must be less than " + str(round(MAX_CELLS_PERMITED / 1000.0, 2))
            html += "<br><br>Hit Back on your browser to go back to the Main page and make adjustments ..."
            html +=  '</body></html>'
            yield html
            return "bailing out!"


        args["CPU_cores_to_use"] = NUM_CORES


        # check if we have a valid temp folder
        args["temp_folder"] = TMP_FOLDER
        print("temp_folder is set to", args["temp_folder"], file=sys.stderr)
        if not os.path.exists(args["temp_folder"]):
            s = "temp folder " + args["temp_folder"] + " does not exist!"
            print(s, file=sys.stderr)
            logging.error(s)
            html = '</body></html>Error:' + s
            yield html
            return "bailing out!"# Cannot continue without proper temp folder

        # name of zip file is time since 2000 in 0.01 seconds
        fname = str(int((datetime.now()-datetime(2000,1,1)).total_seconds() * 1000))
        args["zip_file_name"] = fname

        # if this number of cells to process is exceeded, use a temp file instead of memory only
        args["max_cells_for_memory_only"] = MAX_CELLS


        # show snazzy animate gif - set to style="display: none to hide once
        html =  '<img src="static/processing.gif" id="gif" alt="processing animation" style="display: block;">\n'
        yield html

        #
        # Create zip and write to tmp
        #
        try:
            totalsize, full_zip_zile_name = TouchTerrainEarthEngine.get_zipped_tiles(**args) # all args are in a dict
        except Exception as e:
            print("Error:", e, file=sys.stderr)
            html =  '</body></html>' + "Error:," + str(e)
            yield html   
            return "bailing out!"

        # if totalsize is negative, something went wrong, error message is in full_zip_zile_name
        if totalsize < 0:
            print("Error:", full_zip_zile_name, file=sys.stderr)
            html =  '</body></html>' + "Error:," + str(full_zip_zile_name)
            yield html
            return "bailing out!"

        else:
            html = "total size of zip: %.2f Mb<br>" % totalsize
            
            # move zip from temp folder to static folder so flask can serve it (. is server root!)
            zip_file = fname + ".zip"
            try:
                os.rename(full_zip_zile_name, "server" + os.sep + "static" + os.sep + zip_file)
            except Exception as e:
                print("Error:", e, file=sys.stderr)
                html =  '</body></html>' + "Error:," + str(e)
                yield html   
                return "bailing out!"       
            
            zip_url = url_for("static", filename=zip_file) 


            if args["fileformat"] in ("STLa", "STLb"): 
                html += '<br><form action="/' + zip_file +'" method="GET" enctype="multipart/form-data">' 
                html += '  <input type="submit" value="Preview STL " title=""> '
                html += 'This uses WebGL for in-browser 3D rendering and may take a while to load for large models'
                html += '</form>'            
            
            html += '<br><form action="' + zip_url +'" method="GET" enctype="multipart/form-data">' 
            html += '  <input type="submit" value="Download zip File " title="zip file contains a log file, the geotiff of the processed area and the 3D model file (stl/obj) for each tile">'
            html += '</form>'            
            
            html += "<br>All files will be deleted in 6 hrs.<br>To return to the selection map, click the back button in your browser once."
            html +=  '</body></html>'
            yield html


    # for testing the UI sequence
    def preflight_generator_test():
        
        # onload event will only be triggered once </body> is given
        html =  '''<body onload="document.getElementById('working').style.display='none'; document.getElementById('gif').style.display='none'">\n'''
       
        html += '<h2 id="working" >Processing terrain data into 3D print file(s) - please be patient!</h2> <br>'
        yield html
        
        # processing animation
        html =  '<img src="static/processing.gif" id="gif" alt="processing animation" style="display: block;">\n'
        yield html
        
        # download button - clsing body will trigger the hiding 
        html = '''<form action="" method="GET" enctype="multipart/form-data">
                     <input type="submit" value="Download zip File "></form>\n'''
        html +=  StlViewerHTML("tmp/test.stl")
        html +=  '</body>'

        yield html
        
    return Response(stream_with_context(preflight_generator()), mimetype='text/html')

#print "end of TouchTerrain_app.py"
