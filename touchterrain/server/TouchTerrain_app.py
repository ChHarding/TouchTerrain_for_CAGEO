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


from touchterrain.common import config # general settings
from touchterrain.server.config import * # server only settings
from touchterrain.server import app

from flask import Flask, stream_with_context, request, Response, url_for, send_from_directory, render_template
app = Flask(__name__)


# import modules from common
from touchterrain.common import TouchTerrainEarthEngine # will also init EE
from touchterrain.common.Coordinate_system_conv import * # arc to meters conversion

import logging
import time

from zipfile import ZipFile

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


# a JS script to init google analytics, so I can use ga send on the pages with preview and download buttons
GA_script = """
<head>
 <script>
  (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
  (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
  m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
  })(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

  ga('create',
      '""" + GOOGLE_ANALYTICS_TRACKING_ID + """',  // put your own tracking id in server/config.py
      'auto');
  ga('send', 'pageview');
  
  //fire off several messages to GA when download button is clicked
  function onclick_for_dl(){
  		ga('send', 'event', 'Download', 'Click', 'direct', '1');
  		let comment_text=document.getElementById('comment').value;
  		//console.log(comment_text) 
  		ga('send', 'event', 'Comment1', 'Click', comment_text, {nonInteraction: true});
  		//console.log('done comment1') 
  		//ga('send', 'event', 'Comment2', 'Click', "this is comment 2", {nonInteraction: true}); // works
  		//console.log('done comment2') 
  		//ga('set', 'dimension3', 'example of text for dimension3 using set'); /// doesn't work
  		//console.log('done comment3') 
  }
 </script>
</head>
"""


#
# The page for selecting the ROI and putting in printer parameters
#

@app.route("/", methods=["GET"])
def main_page():
    # example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247&hs_gamma=1.0

    '''
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
    else:
        print("EE init() worked (with .config/earthengine/credentials)", file=sys.stderr)
    '''
    # init all browser args with defaults, these must be strings and match the SELECT values
    args = {
        'DEM_name': 'USGS/NED',

        # defines map location
        'map_lat': "44.59982",
        'map_lon': "-108.11695",
        'map_zoom': "11",

        # defines optional polygon
        'polyURL': "", #"https://drive.google.com/file/d/1qrBnX-VHXiHCIIxCZhyG1NDicKnbKu8p/view?usp=sharing", # in KML file at Google Drive

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
        "manual": "",   # &quot;bottom:true&quot;

        # Earth engine layer vis
        "maptype": "roadmap",  # or: 'satellite' 'terrain' 'hybrid'
        "transp": 20, # transparency in %
        "gamma": 1, # gamma ("contrast")
        "hsazi": 315, # hillshade azimuth (compass)
        "hselev": 45, # hillshade elevation (above horizon)

        "google_maps_key": google_maps_key,  # '' or a key from GoogleMapsKey.txt
    }
        
    # re-assemble the URL query string and store it , so we can put it into the log file
    qs = "?"
    requ_args = list(request.args.items())
    for k,v in requ_args:
        v = v.replace('\"', '&quot;')
        qs = qs + k + "=" + v + "&"
    #print qs

    # overwrite args with values from flask request args 
    for key in request.args:
        args[key] = request.args[key]
        #print(key, request.args[key])

    '''
    # for ETOPO1 we need to first select one of the two bands as elevation
    if args["DEM_name"] == """NOAA/NGDC/ETOPO1""":
        img = ee.Image(args["DEM_name"])
        elev = img.select('bedrock') # or ice_surface
        terrain = ee.Terrain.products(elev)
    else:
        terrain = ee.Algorithms.Terrain(ee.Image(args["DEM_name"]))

    hs = terrain.select('hillshade')
    '''
    # get hillshade for elevation
    if args["DEM_name"] in ("NRCan/CDEM", "AU/GA/AUSTRALIA_5M_DEM"):  # Image collection?
        dataset = ee.ImageCollection('NRCan/CDEM')
        elev = dataset.select('elevation')
    else:
        elev = ee.Image(args["DEM_name"])
    
    
    hsazi = float(args["hsazi"]) # compass heading of sun
    hselev = float(args["hselev"]) # angle of sun above the horizon
    hs = ee.Terrain.hillshade(elev, hsazi, hselev)

    gamma = float(args["gamma"])
    mapid = hs.getMapId( {'gamma':gamma}) # request map from EE, transparency will be set in JS

    # these have to be added to the args so they end up in the template
    # 'mapid': mapid['mapid'],
    # 'token': mapid['token'],

    args['mapid'] = mapid['mapid']
    args['token'] = mapid['token']

    # work around getattr throwing an exeption if name is not in module
    def mygetattr(mod, name):
        try:
            r = getattr(mod, name)
        except:
            r = "" # name not found
        else:
            return r

    # add any vars from server/config.py that may need to be inlined
    args["GOOGLE_ANALYTICS_TRACKING_ID"] = mygetattr(config, "GOOGLE_ANALYTICS_TRACKING_ID")
   

    # string with index.html "file" with mapid, token, etc. inlined
    html_str = render_template("index.html", **args)
    return html_str

# @app.route("/cleanup_preview/<string:zip_file>")  onunload="myFunction()"

@app.route("/preview/<string:zip_file>")
def preview(zip_file):

    def preview_STL_generator():

        # create html string
        html = '<html>'

        html += GA_script # <head> with script that inits GA with my tracking id and calls send pageview

        # onload event will only be triggered once </body> is given
        html += '''<body  onload="document.getElementById('working').innerHTML='&nbsp Preview: (zoom with mouse wheel, rotate with left mouse drag, pan with right mouse drag)'">\n'''

        # progress bar, will be hidden after loading is complete
        html += '<progress id="pbtotal" value="0" max="1" style="display:block;margin:0 auto 10px auto; width:100%"></progress>\n'

        # Message shown during unzipping
        html += '\n<h4 id="working" style="display:inline; white-space:nowrap" >Preparing for preview, please be patient ...</h4>\n'
        yield html  # this effectively prints html into the browser but doesn't block, so we can keep going and append more html later ...

        # download button
        zip_url = url_for("download", filename=zip_file) # URL(!) of unzipped zip file
        html = '\n<form style="float:left" action="' + zip_url +'" method="GET" enctype="multipart/form-data">'
        html += '  <input type="submit" value="Download zip File" '
        html += ''' onclick="ga('send', 'event', 'Download', 'Click', 'from preview', '0')" '''
        html += '   title="zip file contains a log file, the geotiff of the processed area and the 3D model file (stl/obj) for each tile\n">'
        #html += '  To return to the selection map, click the back button in your browser twice.\n'
        html += '</form>\n'

        # get path (not URL) to zip file in download folder
        full_zip_path = os.path.join(DOWNLOADS_FOLDER, zip_file)

        # make a dir in preview to contain the STLs
        job_id = zip_file[:-4] # name for folder
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
                if f[-4:].lower() == ".stl":
                    stl_files.append(f)
                    zip_ref.extract(f, preview_dir)


        if len(stl_files) == 0:
            errstr = "No STL files found in " + full_zip_path
            print("Error:", errstr, file=sys.stderr)
            return "Error:" + errstr


        # JS functions for loading bar
        html +=  """
            <script>
                  function load_prog(load_status, load_session){
                      let loaded = 0;
                      let total = 0;

                      //go over all models that are/were loaded
                      Object.keys(load_status).forEach(function(model_id)
                      {
                          //need to make sure we're on the last loading session (not counting previous loaded models)
                          if (load_status[model_id].load_session == load_session){
                              loaded += load_status[model_id].loaded;
                              total += load_status[model_id].total;
                          }
                      });

                      //set total progress bar
                      document.getElementById("pbtotal").value = loaded/total;
                  }
            </script>"""

        html += """
                <div id="stl_cont" style="width:100%;height:80%;margin:0 auto;border:1px dashed rgb(0, 0, 0)"></div>

                <script src="/static/js/stl_viewer.min.js"></script>
                <script>
                    var stl_viewer=new StlViewer(
                        document.getElementById("stl_cont"),
                        {
                            loading_progress_callback:load_prog,
                            //all_loaded_callback:all_loaded,
                            all_loaded_callback: function(){document.getElementById("pbtotal").style.display='none';},
                            models:
                            ["""

        # make JS object for each tile
        for i,f in enumerate(stl_files):
            html += '\n                            {'
            html += 'id:' + str(i+1) + ', '
            url = url_for("preview_file", zip_file=zip_file, filename=f)
            html += 'filename:"' + url + '", rotationx:-0.35, display:"flat",'
            #html += 'animation:{delta:{rotationx:1, msec:3000, loop:true}}'
            html += '},'
        html += """\n                            ],
                            load_three_files: "/static/js/",
                            center_models:"""

        # if we have multiple tiles, don't center models, otherwise each is centered and they overlap.
        # Downside: the trackball will rotate around lower left tile corner (which is 0/0), not the center
        html += 'false' if len(stl_files) > 1 else 'true'

        html += """
                        }
                    );
                </script>

            </body>
        </html>
        """
        #print(html)
        yield html

    return Response(stream_with_context(preview_STL_generator()), mimetype='text/html')

@app.route("/preview/<string:zip_file>/<string:filename>")
def preview_file(zip_file, filename):
    job_id = zip_file[:-4]
    return send_from_directory(os.path.join(PREVIEWS_FOLDER, job_id),
                               filename, as_attachment=True)

# Page that creates the 3D models (tiles) in a zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file.
@app.route("/export", methods=["POST"])
def export():

    def preflight_generator():

        # create html string
        html = '<html>'
        html += GA_script # <head> with script that inits GA with my tracking id and calls send pageview
        
        # onload event will only be triggered once </body> is given
        html +=  '''<body onerror="document.getElementById('error').innerHTML='Error (non-python), possibly the server timed out ...'"\n onload="document.getElementById('gif').style.display='none'; document.getElementById('working').innerHTML='Processing finished'">\n'''
        html += '<h2 id="working" >Processing terrain data into 3D print file(s), please be patient.<br>\n'
        html += 'Once the animation stops, you can preview and download your file.</h2>\n'
        yield html  # this effectively prints html into the browser but doesn't block, so we can keep going and append more html later ...


        #
        #  print/log all args and their values
        #

        # put all args we got from the browser in a  dict as key:value
        args = request.form.to_dict()

        # list of the subset of args needed for processing
        key_list = ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                  "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat",
                  "polyURL")

        for k in key_list:
            # float-ify some args
            if k in ["trlat", "trlon", "bllat", "bllon","printres", "tilewidth", "basethick", "zscale"]:
                args[k] = float(args[k])

            # int-ify some args
            if k in ["ntilesx", "ntilesy"]:
                args[k] = int(args[k])


        # decode any extra (manual) args and put them in the args dict as
        # separate args as the are needed in that form for processing
        # Note: the type of each arg is decided by  json.loads(), so 1.0 will be a float, etc.
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

        # for geotiffs only, set a much higher limit b/c we don't do any processing,
        # just d/l the GEE geotiff and zip it
        if args["fileformat"] == "GeoTiff":
            global MAX_CELLS_PERMITED # thanks Nick!
            MAX_CELLS_PERMITED *= 100

        # pr <= 0 means: use source resolution
        if pr > 0: # print res given by user (width and height are in mm)
            height = width * (dlat / float(dlon))
            pix_per_tile = (width / float(pr)) * (height / float(pr))
            tot_pix = int((pix_per_tile * num_total_tiles) / div_by) # total pixels to print
            print("total requested pixels to print", tot_pix, ", max is", MAX_CELLS_PERMITED, file=sys.stderr)
        else:
            # estimates the total number of cells from area and arc sec resolution of source
            # this is done for the entire area, so number of cell is irrelevant
            DEM_name = args["DEM_name"]
            cell_width_arcsecs = {"USGS/NED":1/9.0, "USGS/GMTED2010":7.5, "CPOM/CryoSat2/ANTARCTICA_DEM":30,
                                  "NOAA/NGDC/ETOPO1":60, "USGS/GTOPO30":30, "USGS/SRTMGL1_003":1,
                                  "JAXA/ALOS/AW3D30/V2_2":1, "NRCan/CDEM": 0.75,} # in arcseconds!
            cwas = float(cell_width_arcsecs[DEM_name])
            tot_pix =    int( ( ((dlon * 3600) / cwas) *  ((dlat * 3600) / cwas) ) / div_by)
            print("total requested pixels to print at a source resolution of", round(cwas,2), "arc secs is ", tot_pix, ", max is", MAX_CELLS_PERMITED, file=sys.stderr)

        if tot_pix >  MAX_CELLS_PERMITED:
            html = "Your requested job is too large! Please reduce the area (red box) or lower the print resolution<br>"
            html += "<br>Current total number of Kilo pixels is " + str(round(tot_pix / 1000.0, 2))
            html += " but must be less than " + str(round(MAX_CELLS_PERMITED / 1000.0, 2))
            html += "<br><br>Hit Back on your browser to go back to the Main page and make adjustments ...\n"
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

        # show snazzy animated gif - set to style="display: none to hide once processing is done
        html =  '<img src="static/processing.gif" id="gif" alt="processing animation" style="display: block;">\n'

        # add an empty paragraph for error messages during processing that come from JS
        html += '<p id="error"> </p>\n'
        yield html

        #
        # Create zip and write to tmp
        #
        try:
            totalsize, full_zip_file_name = TouchTerrainEarthEngine.get_zipped_tiles(**args) # all args are in a dict
        except Exception as e:
            print("Error:", e, file=sys.stderr)
            html =  '</body></html>' + "Error:," + str(e)
            yield html
            return "bailing out!"

        # if totalsize is negative, something went wrong, error message is in full_zip_file_name
        if totalsize < 0:
            print("Error:", full_zip_file_name, file=sys.stderr)
            html =  '</body></html>' + "Error:," + str(full_zip_file_name)
            yield html
            return "bailing out!"

        else:
            html = ""

            # move zip from temp folder to static folder so flask can serve it (. is server root!)
            zip_file = fname + ".zip"
            try:
                os.rename(full_zip_file_name, os.path.join(DOWNLOADS_FOLDER, zip_file))
            except Exception as e:
                print("Error moving file from tmp to downloads:", e, file=sys.stderr)
                html =  '</body></html>' + "Error:," + str(e)
                yield html
                return "bailing out!"

            zip_url = url_for("download", filename=zip_file)


            if args["fileformat"] in ("STLa", "STLb"):
                html += '<br><form action="' + url_for("preview", zip_file=zip_file)  +'" method="GET" enctype="multipart/form-data">'
                html += '  <input type="submit" value="Preview STL " '
                html += ''' onclick="ga('send', 'event', 'Preview', 'Click', 'preview', '0')" '''
                html += '   title=""> '
                html += 'Note: This uses WebGL for in-browser 3D rendering and may take a while to load for large models.<br>\n'
                html += 'You may not see anything for a while even after the progress bar is full!'
                html += '</form>\n'

            html += "Optional: tell us what you're using this model for<br>\n"
            html += '''<textarea autofocus form="dl" id="comment" cols="100" maxlength=150 rows="2"></textarea><br>\n'''

            html += '<br>\n<form id="dl" action="' + zip_url +'" method="GET" enctype="multipart/form-data">\n'
            html += '  <input type="submit" value="Download zip File " \n'
            #https://stackoverflow.com/questions/57499732/google-analytics-events-present-in-console-but-no-more-in-api-v4-results
            html += '''  onclick=onclick_for_dl();\n'''
            
            
            #html += '''  onclick="ga('send', 'event', 'Download', 'Click', 'from preview', '0');\n
                                  #ga('send', 'event', 'Comment1', 'Click', document.getElementById('comment') , 1);"\n '''
                                  #{
                                       #'dimension1': document.getElementById('comment').value,
                                       #'dimension2': 'Test for setting dimension2 from download button click'
                                       #'dimension03': 'Test for setting dimension03 from download button click'
                                      #},
                                      #1);" \n

            html += '   title="zip file contains a log file, the geotiff of the processed area and the 3D model file (stl/obj) for each tile">\n'
            html += "   Size: %.2f Mb   (All files will be deleted in 6 hrs.)<br>\n" % totalsize
            html += "   <br>To return to the selection map, click the back button in your browser once.\n"
            html += '</form>\n'



            html +=  '</body></html>'
            yield html


    r =  Response(stream_with_context(preflight_generator()), mimetype='text/html')
    return r

@app.route('/download/<string:filename>')
def download(filename):
    return send_from_directory(DOWNLOADS_FOLDER,
                               filename, as_attachment=True)

#print "end of TouchTerrain_app.py"
