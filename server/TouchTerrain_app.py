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
# CH 29/01/2018: for large areas (MAX_CELLS), temp files are used instead of only using memory
# CH 11/30/2017: added all print parameters to URL
# CH 11/21/2016: Added support for hillshade gamma. Unlike hs opacity, it needs to be set on server side
# and so requires a reload
# CH 11/16/2016: added flags for server will run: Apache, GAE_devserver, or paste
# CH 06/20/2016: added ETOPO and changed the DEM source strings, see DEM_sources from TouchTerrainEarthEngine.py
# CH 12/01/2016: MainPage() request handler now uses GET, the querie string contains the coords of the window, the DEM and the coords of the region
# CH 12/22/2015: changes UI for switching (no need to click button) and clipped SRTM data to 0 for offshore (was -32768)
# CH 12/16/2015: added switch between 10m (NED) and 90m (SRTM) DEM
# CH 12/01/2015: created a way to remotely disable the write restrictions on the devserver via a fake __init__
# CH 11/23/2015: went back to no-threading as it didn't seem to work in the devserver
#    added a pre-flight page to warn the user of no feedback. Had to fake the request part via a global var (eeewwww!))

import math
import os
from datetime import datetime
import ee


# Earth Engine config
import config  # config.py must be in this folder

from touchterrain_config  import *  # Some server settings, touchterrain_config.py must be in this folder

# import module form common
import sys
from os.path import abspath, dirname
top = abspath(__file__)
this_folder = dirname(top)
tmp_folder = this_folder + os.sep + "tmp"  # dir to store zip files and temp tile files
common_folder = dirname(this_folder) + os.sep + "common"
sys.path.append(common_folder) # add common folder to sys.path
#print >> sys.stderr, "sys.path:", sys.path
import TouchTerrainEarthEngine

import webapp2

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

# example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247&hs_gamma=1.0
class MainPage(webapp2.RequestHandler):
  def get(self):                             # pylint: disable=g-bad-name

    ee.Initialize(config.EE_CREDENTIALS, config.EE_URL) # authenticates via .pem file
    #print self.request.GET # all args

    DEM_name = self.request.get("DEM_name")
    map_lat = self.request.get("map_lat")
    map_lon = self.request.get("map_lon")
    map_zoom = self.request.get("map_zoom")
    trlat = self.request.get("trlat")
    trlon = self.request.get("trlon")
    bllat = self.request.get("bllat")
    bllon = self.request.get("bllon")
    hillshade_gamma = self.request.get("hs_gamma")
    printres =  self.request.get("printres")
    ntilesx, ntilesy = self.request.get("ntilesx"), self.request.get("ntilesy")
    tilewidth = self.request.get("tilewidth")
    basethick = self.request.get("basethick")
    zscale = self.request.get("zscale")
    fileformat = self.request.get("fileformat")

    # default args, are only used the very first time, after that the URL will have the values encoded
    # these must be strings and match the SELECT values!
    if DEM_name not in TouchTerrainEarthEngine.DEM_sources: DEM_name = 'USGS/NED' # 10m NED as default
    if map_lat == "": map_lat = "44.59982"  # Sheep Mtn, Greybull, WY
    if map_lon == "": map_lon ="-108.11695"
    if map_zoom == "": map_zoom ="11"
    if hillshade_gamma == "": hillshade_gamma = "1.0"
    if printres == "": printres = "0.5"
    if ntilesx == "": ntilesx = "1"
    if ntilesy == "": ntilesy = "1"
    if tilewidth == "": tilewidth = "80"
    if basethick == "": basethick = "2"
    if zscale == "": zscale = "1.0"
    if fileformat not in ["obj", "STLa", "STLb"]: fileformat = "STLb"

    # for ETOPO1 we need to first select one of the two bands as elevation
    if DEM_name == """NOAA/NGDC/ETOPO1""":
        img = ee.Image(DEM_name)
        elev = img.select('bedrock') # or ice_surface
        terrain = ee.Terrain.products(elev)
    else:
        terrain = ee.Algorithms.Terrain(ee.Image(DEM_name))

    hs = terrain.select('hillshade')

    mapid = hs.getMapId( {'gamma':float(hillshade_gamma)}) # opacity is set in JS

    # jinja will inline these variables and their values into the template and create index.html
    template_values = {
        'mapid': mapid['mapid'],
        'token': mapid['token'],
    'DEM_name': DEM_name,

     # defines map location
        'map_lat': map_lat,
        'map_lon': map_lon,
        'map_zoom': map_zoom,

         # defines area box
        'trlat' : trlat,
        'trlon' : trlon,
        'bllat' : bllat,
        'bllon' : bllon,

        # 3D print parameters
        "printres": printres,
        "ntilesx" : ntilesx,
        "ntilesy" : ntilesy,
        "tilewidth" : tilewidth,
        "basethick" : basethick,
        "zscale" : zscale,
        "fileformat" : fileformat,

        "hsgamma": hillshade_gamma,
    }

    # this creates a index.html "file" with mapid, token, etc. inlined
    template = jinja_environment.get_template('index.html')
    self.response.out.write(template.render(template_values))



# preflight page: showing some notes on how there's no used feedback until processing is done
# as I don't know how to carry over the args I get here to the export page handler's post() method,
# I store the entire request in the registry and write it back later.
class preflight(webapp2.RequestHandler):
    def __init__(self, request, response):
        # Set self.request, self.response and self.app.
        self.initialize(request, response)
        app = webapp2.get_app()
        app.registry['preflightrequest'] = self.request
        print "preflight app.registry is", app.registry
        print app.registry['preflightrequest'] #Levi I don't know why, but without this, complains about expired request


    def post(self):
        #print self.request.POST # all args
        self.response.headers['X-Content-Type-Options'] = 'nosniff' # Prevent browsers from MIME-sniffing the content-type:
        self.response.headers["X-Frame-Options"] = "SAMEORIGIN"   # prevent clickjacking
        self.response.out.write('<html><body>')
        self.response.out.write("<h2>Processing started:</h2>")
        self.response.out.write("Press the Start button to process the DEM into 3D model files.<br>")
        self.response.out.write("Note that there's NO progress indicator (yet), you will only see this page trying to connect. That's OK, just be patient!<br>")
        self.response.out.write("Pressing Start again during processing has no effect.<br>")
        self.response.out.write("Once your 3D model is created, you will get a new page (Processing finished) for downloading a zip file.<br><br>")
        self.response.out.write('<form action="/export" method="POST" enctype="multipart/form-data">')
        self.response.out.write('<input type="hidden" maxlength="50" size="20" name="Note" id="Note" value="NULL">') # for user comment
        #self.response.out.write('<input type="hidden" name="prog_pct" id="prog_pct" value="0">') # progress percentage
        self.response.out.write('<input type="submit" value="Start"> </form>')
        self.response.out.write('</body></html>')

# Page that creates the 3D models (tiles) in a in-memory zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file. The args are the same as in the
# main page (via preflight by using app.registry.get('preflightrequest'))
class ExportToFile(webapp2.RequestHandler):
    def __init__(self, request, response):
        self.initialize(request, response)
        app = webapp2.get_app()
        self.request = app.registry.get('preflightrequest')

    def post(self): # make tiles in zip file and write
        #print self.request.arguments() # should be the same as given to preflight
        self.response.headers['X-Content-Type-Options'] = 'nosniff' # Prevent browsers from MIME-sniffing the content-type:
        self.response.headers["X-Frame-Options"] = "SAMEORIGIN"   # prevent clickjacking
        self.response.out.write('<html><body>')
        self.response.out.write('<h2>Processing finished:</h2>')

        # debug: print/log all args and then values
        args = {} # put arg name and value in a dict as key:value
        for k in ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres", "ntilesx", "ntilesy", "tilewidth",
                  "basethick", "zscale", "fileformat"):
            v = self.request.get(k) # key = name of arg
            args[k] = v # value
            if k not in ["DEM_name", "fileformat"]: args[k] = float(args[k]) # floatify non-string args
            #print k, args[k]
            self.response.out.write("%s = %s <br>" % (k, str(args[k])))
            logging.info("%s = %s" % (k, str(args[k])))

        args["CPU_cores_to_use"] = NUM_CORES

        # name of zip file is time since 2000 in 0.01 seconds
        fname = str(int((datetime.now()-datetime(2000,1,1)).total_seconds() * 1000))
        args["zip_file_name"] = fname

        # if this number of cells to process is exceeded, use a temp file instead of memory only
        args["max_cells_for_memory_only"] = MAX_CELLS


        try:
            # create zip and write to tmp
            totalsize, full_zip_zile_name = TouchTerrainEarthEngine.get_zipped_tiles(**args) # all args are in a dict
        except Exception, e:
            logging.error(e)
            print(e)
            self.response.out.write(e)
            return

        logging.info("finished processing " + full_zip_zile_name)
        self.response.out.write("total zipped size: %.2f Mb<br>" % totalsize)

        self.response.out.write('<br><form action="tmp/%s.zip" method="GET" enctype="multipart/form-data">' % (fname))
        self.response.out.write('<input type="submit" value="Download zip File " title="">   (will be deleted in 24 hrs)</form>')
        #self.response.out.write('<form action="/" method="GET" enctype="multipart/form-data">')
        #self.response.out.write('<input type="submit" value="Go back to selection map"> </form>')
        self.response.out.write("<br>To return to the selection map, click the back button in your browser twice")
        self.response.out.write(
        """<br>After downloading you can preview a STL/OBJ file at <a href="http://www.viewstl.com/" target="_blank"> www.viewstl.com ) </a>  (limit: 35 Mb)""")

# the pages that can be requested from the browser and the handler that will respond (get or post method)
app = webapp2.WSGIApplication([('/', MainPage), # index.html
                              ('/export', ExportToFile), # results page, generated by: <form action="/export" ....>
                              ('/preflight', preflight)],
                              debug=True)

if SERVER_TYPE == "paste":
    from paste import httpserver
    print "running local httpserver ,",
    httpserver.serve(app, host='127.0.0.1', port='8080') # run the server
print "end of TouchTerrain_app.py"
