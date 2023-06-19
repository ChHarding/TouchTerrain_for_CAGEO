"""TouchTerrain-app - flask server module"""

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
import requests
from io import BytesIO, StringIO
from PIL import Image
from shutil import copyfileobj

from touchterrain.common import config # general settings
from touchterrain.server.config import * # server only settings
from touchterrain.server import app

from flask import Flask, stream_with_context, request, Response, url_for, send_from_directory, render_template, flash, redirect
from urllib.parse import urlparse
app = Flask(__name__)

# import modules from common
from touchterrain.common import TouchTerrainEarthEngine # will also init EE
from touchterrain.common.Coordinate_system_conv import * # arc to meters conversion

import logging
import time
from zipfile import ZipFile

# Google Maps key file: must be called GoogleMapsKey.txt and contain key as a single string
google_maps_key = ""
try:
    with open(GOOGLE_MAPS_KEY_FILE) as f:
        google_maps_key = f.read().rstrip()
        if google_maps_key == "Put your Google Maps key here":
            google_maps_key = ""
        else:
            print("Google Maps key is:", google_maps_key)
except:
     # file does not exist - will show the ugly Google map version
     logging.warning("Problem with Google Maps key file - you will only get the ugly Google Map!")



# a JS script to init google analytics, so I can use ga send on the pages with preview and download buttons
def make_GA_script(page_title):
    html = """<title>TouchTerrain: processing finished. Settings used:""" + page_title + """</title>"""
    if GOOGLE_ANALYTICS_TRACKING_ID:
        html += """
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-EGX5Y3PBYH"></script>
        <script>
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '""" + GOOGLE_ANALYTICS_TRACKING_ID + """');
        
        //fire off events to GA when download button is clicked
        function onclick_for_dl(){
                //ga('send', 'event', 'Download', 'Click', 'direct', '1');
                gtag('event', 'Click', {'event_category':'Download', 'event_label':'direct_dl', 'value':'1'});
                
                let comment_text=document.getElementById('comment').value;
                if (comment_text !== ""){ // log comment with GA
                    //console.log(comment_text); 
                    //ga('send', 'event', 'Comment1', 'Click', comment_text, {nonInteraction: true});
                    gtag('event', 'Comment', {'event_category':'Comment', 'event_label':comment_text, 'value':'1', 'nonInteraction': true});
                }
        }
        </script>        
        """
    return html

# entry page that shows a world map and loads the main page when clicked
@app.route("/", methods=['GET', 'POST'])
def intro_page():
    return render_template("intro.html")

#
# The page for selecting the ROI and putting in printer parameters
#
@app.route("/main", methods=['GET', 'POST'])
def main_page():
    # example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247&hs_gamma=1.0

    # init all browser args with defaults, these must be strings and match the SELECT values
    args = {
        'DEM_name': 'USGS/3DEP/10m',

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
        "tilewidth" : "100",
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

        # defines optional polygon (currently not used)
        'polyURL': "", #"https://drive.google.com/file/d/1qrBnX-VHXiHCIIxCZhyG1NDicKnbKu8p/view?usp=sharing", # in KML file at Google Drive
        "google_maps_key": google_maps_key,  # '' or a key from GoogleMapsKey.txt
        'warning':"",
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

    # get hillshade for elevation
    if args["DEM_name"] in ("NRCan/CDEM", "AU/GA/AUSTRALIA_5M_DEM"):  # Image collection?
        dataset = ee.ImageCollection(args["DEM_name"])
        elev = dataset.select('elevation')
        proj = elev.first().select(0).projection() # must use common projection(?)
        elev = elev.mosaic().setDefaultProjection(proj) # must mosaic collection into single image
    else:
        elev = ee.Image(args["DEM_name"])

    hsazi = float(args["hsazi"]) # compass heading of sun
    hselev = float(args["hselev"]) # angle of sun above the horizon
    hs = ee.Terrain.hillshade(elev, hsazi, hselev)

    gamma = float(args["gamma"])
    mapid = hs.getMapId( {'gamma':gamma}) # request map from EE, transparency will be set in JS

    # these have to be added to the args so they end up in the template
    args['mapid'] = mapid['mapid']
    args['token'] = mapid['token']
   
    # in manual, replace " with \" i.e. ""ignore_leq":123" -> "\"ignore_leq\":123"
    # so that it's a valid JS string after it's been inlined
    args["manual"] = args["manual"].replace('"', chr(92)+chr(34))  # \ + "

    # string with index.html "file" with mapid, token, etc. inlined
    html_str = render_template("index.html", **args)

    return html_str


@app.route("/preview/<string:zip_file>")
def preview(zip_file):

    def preview_STL_generator():

        # create html string
        html = '<html>'
        html += make_GA_script("TouchTerrain preview") # <head> with script that inits GA with my tracking id 

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
        html += ''' onclick="gtag('event', 'Click', {'event_category':'Download', 'event_label':'preview_dl', 'value':'1'})" '''
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

        # extract stl files from zip file
        with ZipFile(full_zip_path, "r") as zip_ref:
            fl = zip_ref.namelist() # list of files inside the zip file
            stl_files = []
            for f in fl:
                if f[-4:].lower() == ".stl": # only extract stl files
                    stl_files.append(f) # list of extracted files
                    zip_ref.extract(f, preview_dir)

        # bail out if zip didn't contain any stl files
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


def make_current_URL(query_string_names_and_values_list):
    '''Assembles a string from a list of query names and value tuples:
    [('trlat', '12.34'), ('trlon', '-56,78')] into "?trlat=12.34&trlon=-56,78" '''
    from urllib.parse import quote
    query = '/main?'
    for kv in query_string_names_and_values_list: 
        if kv[1] != '': # skip empty
            query += quote(kv[0]) + "=" + quote(kv[1]) + "&" 
    return query[:-1] # omit last &


# Page that creates the 3D models (tiles) in a zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file.
@app.route("/export", methods=["POST"])
def export():
    # clean up old exports
    os.system('tmpwatch --mtime 6h {} {} {}'.format(DOWNLOADS_FOLDER, PREVIEWS_FOLDER, TMP_FOLDER))

    def preflight_generator():

        # header info is stringified query parameters (to encode the GUI parameters via GA)
        query_list = list(request.form.items()) 
        header = make_current_URL(query_list)[1:] # skip leading ? 

        # make a URL with full query parameters to repeat this job later
        query_list = list(request.form.items())
        
        o = urlparse(request.base_url)
        server = o.scheme + "://" + o.netloc # was: hostname e.g. https://touchterrain.geol.iastate.edu 

        URL_query_str = server + make_current_URL(query_list) # make_current_URL return will start with main? so it doesn't go to the splash screen

        # create html string
        html = '<html>'

        ## make head
        html += '<head>'
        html += make_GA_script(header) # <head> with script that inits GA with my tracking id a 
        
        # script to set a very long timeout to deliver a message should
        # the server get stuck. pageLoadedSuccessfully will be set to true once processing has been
        # done successfully. (Thanks to Nick Booher)
        timeout_msg =  "Sorry, the server timed out. It's not clear how and why, but your processing job did not finish. Maybe the server had to many jobs to process and did run out of memory? This is sad.<br>"
        timeout_msg += "Your only option is to run the job again and hope for better luck.<br>"
        
        html += '''
            <script type="text/javascript">
            var pageLoadedSuccessfully = false;
            setTimeout(function(){ 
                if(!pageLoadedSuccessfully){'''
        html += '    document.write("' + timeout_msg + '"); }\n'
        html += '  }, 5 * 60 * 1000);\n' # 5 * 60 * 1000 = 5 mins
        html += '</script>\n'

        html += '</head>\n' # end head

        ## start body 
        # with the setTimeout the onerror should not be needed anymore, leaving it in just in case
        html += '''<body onerror="document.getElementById('error').innerHTML=\'''' + 'onerror: ' + timeout_msg + ''''"\n'''
        # onload event will only be triggered once </body> is given
        html += '''onload="document.getElementById('gif').style.display='none'; document.getElementById('working').innerHTML='Processing finished'">\n'''
        html += '<h2 id="working" >Processing terrain data into 3D print file(s), please be patient.<br>\n'
        html += 'Once the animation stops, you can preview and download your file.</h2>\n'
        
        yield html  # this effectively prints html into the browser but doesn't block, so we can keep going and append more html later ...


        #
        #  print/log all args and their values
        #

        # put all args we got from the browser in a dict as key:value
        args = request.form.to_dict()

        # list of the subset of args needed for processing
        key_list = ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                    "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat")

        for k in key_list:
            # float-ify some args
            if k in ["trlat", "trlon", "bllat", "bllon","printres", "tilewidth", "basethick", "zscale"]:
                args[k] = float(args[k])

            # int-ify some args
            if k in ["ntilesx", "ntilesy"]:
                args[k] = int(args[k])


        # decode any extra (manual) args and put them in the args dict as
        # separate args as the are needed in that form for processing
        # Note: the type of each arg is decided by json.loads(), so 1.0 will be a float, etc.
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
                yield "Warning: " + s + " (ignored)<br>"
            else:
                for k in extra_args:
                    args[k] = extra_args[k] # append/overwrite
                    # TODO: validate

        # log and show args in browser
        html =  '<br>'
        for k in key_list:
            if args[k] != None and args[k] != '':
                html += "%s = %s <br>" % (k, str(args[k]))
                logging.info("%s = %s" % (k, str(args[k])))
        html += "<br>"
        for k in extra_args:
            if args[k] != None and args[k] != '':
                html += "%s = %s <br>" % (k, str(args[k]))
                logging.info("%s = %s" % (k, str(args[k])))

        # see if we have a optional kml file in requests
        geojson_polygon = None
        if 'kml_file' in request.files:
            kml_file = request.files['kml_file']

            if kml_file.filename != '':  # '' happens when kml file was invalidated
                
                # process kml file
                kml_stream = kml_file.read()

                # for a kmz file stream, unzip into a text string (kmz archive contains a single doc.kml file)
                if kml_file.filename[-4:] == ".kmz":
                    from io import BytesIO
                    from zipfile import ZipFile
                    try:
                        zipped_stream = BytesIO(kml_stream)  # zipped stream (binary)
                        zipped_archive = ZipFile(zipped_stream)
                        kml_stream = zipped_archive.read('doc.kml')
                    except:
                        html += "Warning: " + kml_file.filename + " is not a valid kmz polygon file! (falling back to area selection box.)\n"

                from geojson import Polygon
                try:
                    coords, msg = TouchTerrainEarthEngine.get_KML_poly_geometry(kml_stream) 
                except:
                    html += "Warning: " + kml_file.filename + " is not a valid kml polygon file! (falling back to area selection box.)\n"
                else:
                    if msg != None: # Either got a line instead of polygon or nothing good at all
                        if coords == None: # got nothing good
                            html += "Warning: " + kml_file.filename + " contained neither polygon nor line, falling back to area selection box.<br>"
                        else: 
                            html += "Warning: Using line with " + str(len(coords)) + " points in " + kml_file.filename + " as no polygon was found.<br>"
                            geojson_polygon = Polygon([coords])  
                    else: # got polygon
                        geojson_polygon = Polygon([coords]) # coords must be [0], [1] etc. would be holes 
                        html  += "Using polygon from kml file " + kml_file.filename + " with " + str(len(coords)) + " points.<br>"                   
        
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
        #latitude_in_m, longitude_in_m = arcDegr_in_meter(center_lat)
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
            height = width * (dlat / dlon) # get height from aspect ratio
            pix_per_tile = (width / pr) * (height / pr) # pixels in each dimension
            tot_pix = int((pix_per_tile * num_total_tiles) / div_by) # total pixels to print
            print("total requested pixels to print", tot_pix, ", max is", MAX_CELLS_PERMITED, file=sys.stderr)
        else:
            # estimates the total number of cells from area and arc sec resolution of source
            # this is done for the entire area, so number of cells is irrelevant
            DEM_name = args["DEM_name"]
            cell_width_arcsecs = {"USGS/3DEP/10m":1/9,  "MERIT/DEM/v1_0_3":3,"USGS/GMTED2010":7.5, "CPOM/CryoSat2/ANTARCTICA_DEM":30,
                                  "NOAA/NGDC/ETOPO1":60, "USGS/GTOPO30":30, "USGS/SRTMGL1_003":1,
                                  "JAXA/ALOS/AW3D30/V3_2":1, "NRCan/CDEM": 0.75, 
                                  "AU/GA/AUSTRALIA_5M_DEM": 1/18} # in arcseconds!
            cwas = float(cell_width_arcsecs[DEM_name])
            tot_pix = int((((dlon * 3600) / cwas) *  ((dlat * 3600) / cwas)) / div_by)
            print("total requested pixels to print at a source resolution of", round(cwas,2), "arc secs is ", tot_pix, ", max is",  MAX_CELLS_PERMITED, file=sys.stderr)

        if tot_pix >  MAX_CELLS_PERMITED:
            html = "Your requested job is too large! Please reduce the area (red box) or lower the print resolution<br>"
            html += "<br>Current total number of Kilo pixels is " + str(round(tot_pix / 1000, 2))
            html += " but must be less than " + str(round(MAX_CELLS_PERMITED / 1000, 2)) + " Kilo pixels"
            html +  "If you're trying to process multiple tiles: Consider using the only manual setting to instead print one tile at a time (https://chharding.github.io/TouchTerrain_for_CAGEO/)"
            html += "<br><br>Click \n"
        
            # print out the query parameter URL 
            html += '<a href = "'
            html += URL_query_str + '">' + "here" + "</a> to go back to the main page to make adjustments."
 
            # set timout flag to true, so the timeout script doesn't fire ...
            html += '''\n
                <script type="text/javascript">
                    pageLoadedSuccessfully = true;
                </script>'''

            html +=  '</body></html>'
            yield html
            return "bailing out!"


        # Set number of cores to use 
        # server/config.py defined NUM_CORES 0 means all, 1 means single, etc. which can be overwritten
        # via manual option CPU_cores_to_use. However, Forced_single_core_only will 
        # set the cores to 1 and not allow manual override. MP on ISU servers was disabled 
        # Nov. 2021 as we could not figure out why it was giving us problems (jobs bailed out early)
        # Forced_single_core_only was added 3/13/23 as response to user request to put MP back
        args["CPU_cores_to_use"] = NUM_CORES
        if args["CPU_cores_to_use"] == "Forced_single_core_only":
            args["CPU_cores_to_use"] = 1
        elif extra_args.get("CPU_cores_to_use") != None: # Override if given as manual option
            args["CPU_cores_to_use"] = extra_args.get("CPU_cores_to_use")


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

        # set geojson_polygon as polygon arg (None by default)
        args["polygon"] = geojson_polygon

        # show snazzy animated gif - set to style="display: none to hide once processing is done
        html = '<img src="static/processing.gif" id="gif" alt="processing animation" style="display: block;">\n'

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
            html =  '</body></html>' + "Error: " + str(e)
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
                html += ''' onclick="gtag('event', 'Click', {'event_category':'Preview', 'event_label':'preview', 'value':'1'})" '''
                html += '   title=""> '
                html += 'Note: This uses WebGL for in-browser 3D rendering and may take a while to load for large models.<br>\n'
                html += 'You may not see anything for a while even after the progress bar is full!'
                html += '</form>\n'

            html += "Optional: Tell us what you're using this model for<br>\n"
            html += '''<textarea autofocus form="dl" id="comment" cols="100" maxlength=150 rows="2"></textarea><br>\n'''

            html += '<br>\n<form id="dl" action="' + zip_url +'" method="GET" enctype="multipart/form-data">\n'
            html += '  <input type="submit" value="Download zip File " \n'
            html += '''  onclick=onclick_for_dl();\n'''
            html += '   title="zip file contains a log file, the geotiff of the processed area and the 3D model file (stl/obj) for each tile">\n'
            html += "   Size: %.2f Mb   (All files will be deleted in 6 hrs.)<br>\n" % totalsize
            html += '</form>\n'
            
            html += "   <br><br>If you take picture of your touchterrain 3D prints (or CNC carves) and put them on Instagram why not tag them with #touchterrain?"

            html += "   <br><br>To return to the selection map, click on the back button in your browser once, or on the link below:<br>"
            #html += "<br>Click on the URL below to return to the selection map:<br>"

            # print out the query parameter URL 
            html += '<a href = "'
            html += URL_query_str + '">' + URL_query_str + "</a><br>"
            html += "<br>To have somebody else generate the same model, have them copy&paste this URL into a browser<br>" 
 
            # set timout flag to true, so the timeout script doesn't fire
            html += '''\n
                <script type="text/javascript">
                    pageLoadedSuccessfully = true;
                </script>'''

            html +=  '</body></html>'
            yield html

    r =  Response(stream_with_context(preflight_generator()), mimetype='text/html')
    return r

@app.route('/download/<string:filename>')
def download(filename):
    return send_from_directory(DOWNLOADS_FOLDER,
                               filename, as_attachment=True)

#print "end of TouchTerrain_app.py"
