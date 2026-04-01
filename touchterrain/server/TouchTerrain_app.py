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
from datetime import datetime, timedelta
import json
import ee
import sys
import requests
from io import BytesIO, StringIO
from PIL import Image
from shutil import copyfileobj
from geojson import Polygon
from io import BytesIO
from zipfile import ZipFile

from touchterrain.common import config # general settings
from touchterrain.server.config import * # server only settings
from touchterrain.server import app

from flask import Flask, stream_with_context, request, Response, url_for, send_from_directory 
from flask import render_template, flash, redirect, make_response, session
import mimetypes

from urllib.parse import urlparse
app = Flask(__name__)

# import modules from common
from touchterrain.common import TouchTerrainEarthEngine # will also init EE
from touchterrain.common.Coordinate_system_conv import * # arc to meters conversion

import logging
import time
from zipfile import ZipFile

# Dedicated quota logger — appends to quota.log next to this file
_quota_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quota.log')
quota_log = logging.getLogger('touchterrain.quota')
quota_log.setLevel(logging.DEBUG)
quota_log.propagate = False  # don't bleed into Flask's root logger
if not quota_log.handlers:
    _qh = logging.FileHandler(_quota_log_path, mode='w', encoding='utf-8')  # 'w' clears on startup
    _qh.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    quota_log.addHandler(_qh)

# Google Maps key removed - ESRI/Leaflet version does not use Google Maps

# RecaptchaKeys.txt in server folder must contain keys for recaptcha site key, 
# recaptcha secret key and flask secret key as single strings in separate lines 

try:
    with open(RECAPTCHA_V3_KEYS_FILE) as f:
        lines = f.readlines()
        keys = [line.rstrip() for line in lines]
        app.config['RECAPTCHA_SITE_KEY'] = keys[0]
        app.config['RECAPTCHA_SECRET_KEY'] = keys[1]
        app.secret_key = keys[2]
except:
     # file does not exist - will show the ugly Google map version
     sys.exit("Problem with RecaptchaKeys.txt in server folder, it must contain keys for the (v3) recaptcha site key, recaptcha secret key and flask secret key as single strings in separate lines. Exiting.")
else:
    print("Recaptcha_v3_keys.txt sucessfully parsed.")

# Check ESRI API key at startup (if one is configured)
def check_esri_api_key(key):
    """Test basemap tile and geocoding endpoints with the given key.
    Prints a one-line status for each service. Returns True if both pass."""
    if not key:
        print("ESRI_API_KEY: not set — using free public CDN (no auth required).")
        return True

    # ESRI enforces referrer restrictions on all requests (including server-side).
    # Send Referer matching the first allowed domain so the check isn't blocked
    # by the referrer restriction itself.
    headers = {'Referer': 'http://127.0.0.1'}
    results = {}

    # 1. Basemap: request a World_Imagery tile (always raster; Streets is vector so
    #    its /MapServer/tile path returns 404 — Imagery covers the same privilege).
    try:
        url = ("https://ibasemaps-api.arcgis.com/arcgis/rest/services/"
               "World_Imagery/MapServer/tile/0/0/0?token=" + key)
        r = requests.get(url, timeout=10, headers=headers)
        ct = r.headers.get('Content-Type', '')
        if r.status_code == 200 and 'image' in ct:
            print("ESRI_API_KEY basemap:   OK  (ibasemaps-api.arcgis.com)")
            results['basemap'] = True
        else:
            print(f"ESRI_API_KEY basemap:   FAILED  (HTTP {r.status_code}, {ct}) — check key & Basemaps privilege")
            results['basemap'] = False
    except Exception as e:
        print(f"ESRI_API_KEY basemap:   ERROR  ({e})")
        results['basemap'] = False

    # 2. Geocoding: single candidate lookup — success = 200 + no "error" key in JSON
    try:
        url = ("https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/"
               "findAddressCandidates?SingleLine=Ames%2C+IA&f=json&maxLocations=1&token=" + key)
        r = requests.get(url, timeout=10, headers=headers)
        data = r.json() if r.headers.get('Content-Type','').startswith('application/json') else {}
        if r.status_code == 200 and 'error' not in data:
            print("ESRI_API_KEY geocoding: OK  (geocode-api.arcgis.com)")
            results['geocoding'] = True
        else:
            err = data.get('error', {})
            print(f"ESRI_API_KEY geocoding: FAILED  (HTTP {r.status_code}, {err.get('message','unknown error')}) — check key & Geocoding privilege")
            results['geocoding'] = False
    except Exception as e:
        print(f"ESRI_API_KEY geocoding: ERROR  ({e})")
        results['geocoding'] = False

    return all(results.values())

check_esri_api_key(ESRI_API_KEY)

# May 2025: set the mimetype for javascript files to application/javascript so that 
# load_stl_min.js can be loaded
mimetypes.add_type('application/javascript', '.js')

# set recaptcha v3 threshold for no-bot detection
app.config["score"] = None
app.config["score_threshold"] = 0.5 # 0.0 - 1.0


def verify_recaptcha(token):
    """Verify reCAPTCHA v3 token with Google."""
    secret = app.config['RECAPTCHA_SECRET_KEY']
    payload = {
        'secret': secret,
        'response': token
    }
    r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=payload)
    result = r.json()
    print("recaptcha results:", result)
    app.config["score"] = result.get('score', 0)

    # JSON structure ex: {'success': True, 'challenge_ts': '2025-04-24T19:36:47Z', 'hostname': '127.0.0.1', 'score': 0.9, 'action': 'submit'}
    if RECAPTCHA_V3_LOG_FILE:
        with open(RECAPTCHA_V3_LOG_FILE, 'a') as f:
            f.write(f"{result.get('challenge_ts', '')}, {result.get('success', False)}, "
                    f"{result.get('score', 0)}, {app.config['score_threshold']}, {result.get('hostname', '')}\n")

    return result.get('success', False) and result.get('score', 0) > app.config["score_threshold"]

# a JS script to init google analytics, so I can use ga send on the pages with preview and download buttons
# Note this is inconsistent when used with the preview page as its download  events is fired off when its download
# button is clicked as onclick code and does not use onclick_for_dl()
def make_GA_script(page_title):
    html = """<title>Settings:""" + page_title + """</title>\n"""
    html += """<script async src="https://www.googletagmanager.com/gtag/js?id=""" + GOOGLE_ANALYTICS_TRACKING_ID + '"></script>\n' 
    html += """<script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        gtag('js', new Date());
        gtag('config', '""" + GOOGLE_ANALYTICS_TRACKING_ID + """');
    
        //fire off events to GA when download button is clicked
        function onclick_for_dl(){
            gtag('event', 'Click', {'event_category':'Download', 'event_label':'direct_dl', 'value':'1'});

            let comment_text = document.getElementById('comment').value;
            if (comment_text !== ""){ 
                gtag('event', 'Comment', {'event_category':'Comment', 'event_label':comment_text, 'value':'1', 'nonInteraction': true});
            }
        }
    </script>        
    """
    return html

# entry page that shows a world map does the Recaptch_v3 and, if passed, 
# loads the main page when clicked
@app.route('/', methods=['GET', 'POST'])
def intro_page():
    if request.method == 'POST':
        token = request.form.get('g-recaptcha-response')
        if token and verify_recaptcha(token):
            session['recaptcha_verified'] = True  # Store in Flask session
            print("User has been verified (intro), showing main page.", file=sys.stderr)
            return redirect(url_for('main_page'))
        else:
            session['recaptcha_verified'] = False # default to False, set to True if recaptcha is verified
            print("Verification failed", file=sys.stderr)
            return render_template(
                'intro.html',
                site_key=app.config['RECAPTCHA_SITE_KEY'],
                error=f"reCAPTCHA.v3 failed with score {app.config['score']} < {app.config['score_threshold']}. If you're not a bot, you may be penalized for using privacy tools, a VPN, or incognito mode. Disable them and try again. (Sorry!)"
            )
    return render_template('intro.html', site_key=app.config['RECAPTCHA_SITE_KEY'])

#
# The page for selecting the ROI and putting in printer parameters
#
@app.route("/main", methods=['GET', 'POST'])
def main_page():
    # example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247&hs_gamma=1.0

    # init all browser args with defaults, these must be strings and match the SELECT values
    args = {
        'DEM_name': 'USGS/3DEP/10m_collection',

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
        'warning':"",
    }
        
    # re-assemble the URL query string and store it , so we can put it into the log file
    qs = "?"
    requ_args = list(request.args.items())
    for k,v in requ_args:
        v = v.replace('\"', '&quot;')
        qs = qs + k + "=" + v + "&"
    #print qs

    # overwrite args with values from flask request args (skip NULL placeholder values from unset form fields)
    for key in request.args:
        if request.args[key] != 'NULL':
            args[key] = request.args[key]
        #print(key, request.args[key])

    # get hillshade for elevation
    _IC_BANDS = {
        "USGS/3DEP/10m_collection": "elevation",
        "USGS/3DEP/1m": "elevation",
        "NRCan/CDEM": "elevation",
        "AU/GA/AUSTRALIA_5M_DEM": "elevation",
        "JAXA/ALOS/AW3D30/V4_1": "DSM",
    }
    if args["DEM_name"] in _IC_BANDS:  # Image collection?
        band = _IC_BANDS[args["DEM_name"]]
        dataset = ee.ImageCollection(args["DEM_name"])
        elev = dataset.select(band)
        proj = elev.first().select(0).projection() # must use common projection(?)
        elev = elev.mosaic().setDefaultProjection(proj) # must mosaic collection into single image
    elif args["DEM_name"] == "IGN/RGE_ALTI/1M/2_0/FXX":
        elev = ee.Image(args["DEM_name"]).select("MNT")
    elif args["DEM_name"] == "UK/EA/ENGLAND_1M_TERRAIN/2022":
        elev = ee.Image(args["DEM_name"]).select("dtm")
    else:
        elev = ee.Image(args["DEM_name"])

    hsazi = float(args["hsazi"]) # compass heading of sun
    hselev = float(args["hselev"]) # angle of sun above the horizon
    elev = elev.resample('bilinear')  # smooth elevation before computing hillshade gradients
    hs = ee.Terrain.hillshade(elev, hsazi, hselev)

    gamma = float(args["gamma"])
    _zoom = int(args.get('map_zoom', 0) or 0)
    quota_log.info(f"[hillshade] request: DEM={args['DEM_name']}  zoom={_zoom}  azi={hsazi}  elev={hselev}  gamma={gamma}")
    # No reproject() — GEE's tile pyramid auto-selects the computation scale per tile zoom level.
    # reproject() pins ALL zoom levels to one scale, causing wide-zoom tiles to time out.
    quota_log.info("[hillshade] using GEE native tile pyramid (scale auto-selected per tile zoom level)")
    hs = hs.resample('bilinear')  # bilinearly upsample hillshade tiles when browser zooms past native DEM resolution
    quota_log.info("[hillshade] calling getMapId()…")
    _t0 = time.time()
    try:
        mapid = hs.getMapId({'gamma': gamma})  # request map from EE, transparency will be set in JS
        quota_log.info(f"[hillshade] getMapId OK in {time.time()-_t0:.2f}s  mapid={mapid['mapid']}")
    except Exception as _gee_err:
        quota_log.error(f"[hillshade] getMapId FAILED after {time.time()-_t0:.2f}s: {_gee_err}")
        raise  # re-raise so Flask returns an error page as before

    # these have to be added to the args so they end up in the template
    args['mapid'] = mapid['mapid']
    #args['token'] = mapid['token'] # no token needed anymore
   
    # in manual, replace " with \" i.e. ""ignore_leq":123" -> "\"ignore_leq\":123"
    # so that it's a valid JS string after it's been inlined
    args["manual"] = args["manual"].replace('"', chr(92)+chr(34))  # \ + "

    # serve index.html unless user has not been verified earlier  
    if session.get('recaptcha_verified') == True:
        print("User has been verified, showing main page.", file=sys.stderr)
        # string with index.html "file" with mapid, token, etc. inlined
        html_str = render_template("index.html", **args,
                                    GOOGLE_ANALYTICS_TRACKING_ID=GOOGLE_ANALYTICS_TRACKING_ID,
                                    esri_api_key=ESRI_API_KEY)
        return html_str

    # if user has not been verified yet, show the intro page to get the reCAPTCHA
    print("User has not been verified, showing intro page.", file=sys.stderr)
    return render_template('intro.html', site_key=app.config['RECAPTCHA_SITE_KEY'])

# Page that unzips the tiles and shows a preview of the STL files using a template
@app.route("/preview/<string:zip_file>")
def preview(zip_file):

    # get path (not URL) to zip file in download folder
    full_zip_path = os.path.join(DOWNLOADS_FOLDER, zip_file)

    # make a dir in preview to contain the STLs
    job_id = zip_file[:-4] # name for folder
    preview_dir = os.path.join(PREVIEWS_FOLDER, job_id)
    try:
        os.makedirs(preview_dir, exist_ok=True)  # Use makedirs with exist_ok
    except OSError as e:
        print("Error:", e, file=sys.stderr)
        return "Error:" + str(e)

    # extract stl files from zip file
    try:
        with ZipFile(full_zip_path, "r") as zip_ref:
            fl = zip_ref.namelist() # list of files inside the zip file
            stl_files = []
            for f in fl:
                if f[-4:].lower() == ".stl": # only extract stl files
                    stl_files.append(f) # list of extracted files
                    zip_ref.extract(f, preview_dir)
    except Exception as e:
        errstr = "Error unzipping file: " + str(e)
        print("Error:", errstr, file=sys.stderr)
        return "Error:" + errstr

    # bail out if zip didn't contain any stl files
    if len(stl_files) == 0:
        errstr = "No STL files found in " + full_zip_path
        print("Error:", errstr, file=sys.stderr)
        return "Error:" + errstr

    # Prepare data for the template
    job_id = zip_file[:-4] # folder: zip filename without .zip
    zip_url = url_for("download", filename=zip_file)
    models = []

    for i, f in enumerate(stl_files):
        url = url_for("serve_stl", job_id=job_id, filename=f) # route to call with its 2 args
        models.append({'id': i + 1, 'filename': url, 'rotationx': -0.35, 'display': 'flat'})

    # Convert models to JSON string
    models_json = json.dumps(models)

    center_models = 'false' if len(stl_files) > 1 else 'true'

    ga_script = make_GA_script("Preview") #  JS script for GA

    # Render the template
    html = render_template('preview.html', # template name
                            zip_url=zip_url,
                            models=models_json,
                            center_models=center_models,
                            ga_script=ga_script) 
    return html


# called behind the scenes to serve an STL file from the previews folder
@app.route("/previews/<job_id>/<filename>")
def serve_stl(job_id, filename):
    # Use PREVIEWS_FOLDER (from config) so extraction and serving both resolve to the same directory
    previews_dir = os.path.join(PREVIEWS_FOLDER, job_id)
    return send_from_directory(previews_dir, filename)

def make_current_URL(query_string_names_and_values_list):
    '''Assembles a string from a list of query names and value tuples:
    [('trlat', '12.34'), ('trlon', '-56,78')] into "?trlat=12.34&trlon=-56,78" '''
    from urllib.parse import quote
    # display-only fields that are not valid /main query params
    _skip_keys = {'DEMresolution', 'scale', 'place'}
    query = '/main?'
    for kv in query_string_names_and_values_list:
        if kv[1] != '' and kv[1] != 'NULL' and kv[0] not in _skip_keys: # skip empty, unset placeholders, and display-only fields
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

        html += '<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">\n'
        html += '</head>\n' # end head

        ## start body 
        # with the setTimeout the onerror should not be needed anymore, leaving it in just in case
        html += '''<body onerror="document.getElementById('error').innerHTML=\'''' + 'onerror: ' + timeout_msg + ''''"\n'''
        # onload event will only be triggered once </body> is given
        html += '''onload="var g=document.getElementById('gif'); if(g) g.remove(); document.getElementById('working').innerHTML='Processing finished'">\n'''
        html += '<div class="container mt-3">\n'
        html += '<div class="alert alert-info" id="working">Processing terrain data into 3D print file(s), please be patient.<br>\n'
        html += 'Once the animation stops, you can preview and download your file.</div>\n'
        
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

                    try:
                        zipped_stream = BytesIO(kml_stream)  # zipped stream (binary)
                        zipped_archive = ZipFile(zipped_stream)
                        kml_stream = zipped_archive.read('doc.kml')
                    except:
                        html += "Warning: " + kml_file.filename + " is not a valid kmz polygon file! (falling back to area selection box.)\n"

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
            cell_width_arcsecs = {"USGS/3DEP/10m_collection":1/9,  "MERIT/DEM/v1_0_3":3,"USGS/GMTED2010":7.5, "CPOM/CryoSat2/ANTARCTICA_DEM":30,
                                  "NOAA/NGDC/ETOPO1":60, "USGS/GTOPO30":30,
                                  "JAXA/ALOS/AW3D30/V4_1":1, "NRCan/CDEM": 0.75, 
                                  "AU/GA/AUSTRALIA_5M_DEM": 1/18,
                                  "IGN/RGE_ALTI/1M/2_0/FXX": 1/111,
                                  "UK/EA/ENGLAND_1M_TERRAIN/2022": 1/111,
                                  "USGS/3DEP/1m": 1/111} # in arcseconds!
            cwas = float(cell_width_arcsecs[DEM_name])
            tot_pix = int((((dlon * 3600) / cwas) *  ((dlat * 3600) / cwas)) / div_by)
            print("total requested pixels to print at a source resolution of", round(cwas,2), "arc secs is ", tot_pix, ", max is",  MAX_CELLS_PERMITED, file=sys.stderr)

        # warn user if job is large
        if tot_pix >  MAX_CELLS_PERMITED:
            html  = f'<b>Export blocked:</b> your requested job requires <b>{tot_pix:,}</b> pixels, '
            html += f'which exceeds this server\'s limit of <b>{int(MAX_CELLS_PERMITED):,}</b> pixels. '
            html += 'The job has <b>not</b> been submitted.<br><br>'
            html += 'Please <b>close this tab</b>, return to the main page, and reduce the pixel count by:'
            html += '<ul>'
            html += '<li><b>Shrink the red selection box</b> — a smaller area means fewer DEM pixels to download.</li>'
            html += '<li><b>Increase the print resolution</b> (nozzle diameter / mm per pixel) — a coarser resolution means fewer pixels for the same area.</li>'
            html += '<li><b>Reduce the tile width</b> — narrower tiles at the same resolution cover less area.</li>'
            html += '<li><b>Use fewer tiles</b> (reduce tile count in X or Y) — each tile downloads a separate DEM chunk.</li>'
            html += '</ul>'
            html += f'(Note: Google Earth Engine also has its own hard limits — max 32 MB or 10,000 pixels per side per request. '
            html += f'This server\'s limit of {int(MAX_CELLS_PERMITED):,} pixels is intentionally below those ceilings '
            html += f'to protect shared server memory.)'
 
            # set timout flag to true, so the timeout script doesn't fire ...
            html += '''\n
                <script type="text/javascript">
                    pageLoadedSuccessfully = true;
                </script>'''

            html +=  '</div></body></html>'
            yield html
            return

        # Set number of cores to use 
        # server/config.py defined NUM_CORES 0 means all, 1 means single, etc. which can be overwritten
        # via manual option CPU_cores_to_use. 
        args["CPU_cores_to_use"] = NUM_CORES
        if extra_args.get("CPU_cores_to_use") != None: # Override if given as manual option
            args["CPU_cores_to_use"] = extra_args.get("CPU_cores_to_use")


        # check if we have a valid temp folder
        args["temp_folder"] = TMP_FOLDER
        print("temp_folder is set to", args["temp_folder"], file=sys.stderr)
        if not os.path.exists(args["temp_folder"]):
            s = "temp folder " + args["temp_folder"] + " does not exist!"
            print(s, file=sys.stderr)
            logging.error(s)
            html = '</div></body></html>Error:' + s
            yield html
            return "bailing out!"# Cannot continue without proper temp folder

        # name of zip file is time since 2000 in 0.01 seconds
        fname = str(int((datetime.now()-datetime(2000,1,1)).total_seconds() * 1000))
        args["zip_file_name"] = fname

        # if this number of cells to process is exceeded, use a temp file instead of memory only
        args["max_cells_for_memory_only"] = MAX_CELLS
        print(f"GEE quota [download]: MAX_CELLS_PERMITED={MAX_CELLS_PERMITED:.0f} "
              f"(requests exceeding this are rejected before hitting GEE; "
              f"transient 429s on valid requests are handled by exponential backoff in the engine)",
              file=sys.stderr)

        # set geojson_polygon as polygon arg (None by default)
        args["polygon"] = geojson_polygon

        # show snazzy animated gif - set to style="display: none to hide once processing is done
        html = '<img src="static/processing.gif" id="gif" alt="processing animation" class="d-block my-3" style="display: block;">\n'

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
            html =  '</div></body></html>' + "Error: " + str(e)
            yield html
            return "bailing out!"

        # if totalsize is negative, something went wrong, error message is in full_zip_file_name
        if totalsize < 0:
            print("Error:", full_zip_file_name, file=sys.stderr)
            html =  '</div></body></html>' + "Error:," + str(full_zip_file_name)
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
                html =  '</div></body></html>' + "Error:," + str(e)
                yield html
                return "bailing out!"

            zip_url = url_for("download", filename=zip_file)


            if args["fileformat"] in ("STLa", "STLb"):
                html += '<br><form action="' + url_for("preview", zip_file=zip_file)  +'" method="GET" enctype="multipart/form-data">'
                html += '  <input type="submit" class="btn btn-warning mb-2" value="Preview STL " '
                html += ''' onclick="gtag('event', 'Click', {'event_category':'Preview', 'event_label':'preview', 'value':'1'})" '''
                html += '   title=""> '
                html += 'Note: This uses WebGL for in-browser 3D rendering and may take a while to load for large models.<br>\n'
                html += 'You may not see anything for a while even after the progress bar is full!'
                html += '</form>\n'

            html += '<div class="form-group mt-3"><label>Optional: Tell us what you\'re using this model for:</label>\n'
            html += '''<textarea autofocus form="dl" id="comment" class="form-control" maxlength=150 rows="2"></textarea></div>\n'''

            html += '<form id="dl" action="' + zip_url +'" method="GET" enctype="multipart/form-data">\n'
            html += '  <input type="submit" class="btn btn-success btn-lg mb-2" value="Download zip File " \n'
            html += '''  onclick=onclick_for_dl();\n'''
            html += '   title="zip file contains a log file, the geotiff of the processed area and the 3D model file (stl/obj) for each tile">\n'
            html += "   Size: %.2f Mb   (All files will be deleted in 6 hrs.)<br>\n" % totalsize
            html += '</form>\n'
        

                        
            html += "<br>To have somebody else generate the same model click this button and then use paste:\n"
            url_js = json.dumps(URL_query_str)  # safely JSON-encoded, used inside a <script> block (not an HTML attribute)
            html += f'<script>var _shareUrl = {url_js};</script>\n'
            html += '<button class="btn btn-secondary btn-sm mt-1" onclick="var b=this; navigator.clipboard.writeText(_shareUrl).then(function(){b.textContent=\'Copied!\'; b.classList.replace(\'btn-secondary\',\'btn-success\');}).catch(function(e){alert(\'Copy failed — try HTTPS or allow clipboard access.\');});">Copy URL to clipboard</button>\n'

            html += "<br>To process a new model, close this tab and switch back to the TouchTerrain tab"
 
            # set timout flag to true, so the timeout script doesn't fire
            html += '''\n
                <script type="text/javascript">
                    pageLoadedSuccessfully = true;
                </script>'''

            html +=  '</div></body></html>'
            yield html

    r =  Response(stream_with_context(preflight_generator()), mimetype='text/html')
    return r

@app.route('/log', methods=['POST'])
def browser_log():
    """Receive a short log message from the browser and append it to quota.log."""
    msg = request.get_json(silent=True, force=True)
    if isinstance(msg, dict):
        text = str(msg.get('msg', ''))[:500]  # cap length, avoid injecting huge strings
        quota_log.info(f"[browser] {text}")
    return '', 204

@app.route('/download/<string:filename>')
def download(filename):
    return send_from_directory(DOWNLOADS_FOLDER,
                               filename, as_attachment=True)

