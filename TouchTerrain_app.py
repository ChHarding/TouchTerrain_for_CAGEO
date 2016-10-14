"""TouchTerrain-app - a Module for Google App Engine"""

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

# CH 20/06/2016: added ETOPO and changed the DEM source strings, see DEM_sources from TouchTerrainEarthEngine.py
# CH 12/01/2016: MainPage() request handler now uses GET, the querie string contains the coords of the window, the DEM and the coords of the region
# CH 12/22/2015: changes UI for switching (no need to click button) and clipped SRTM data to 0 for offshore (was -32768)
# CH 12/16/2015: added switch between 10m (NED) and 90m (SRTM) DEM
# CH 12/01/2015: created a way to remotely disable the write restrictions on the devserver via a fake __init__
# CH 11/23/2015: went back to no-threading as it didn't seem to work in the devserver
#    added a pre-flight page to warn the user of no feedback. Had to fake the request part via a global var (eeewwww!))

import math
import os
#import threading
from datetime import datetime
import ee      # can be installed under site-packges

# set to False if you want to run/debug this file.
# this will run a httpserver locally instead of using devserver2 but will still require access to the
# GAE modules in google_appengine\lib
USE_GOOGLE_APPENGINE_LAUNCHER = False
#USE_GOOGLE_APPENGINE_LAUNCHER = True # set to True if you use Google App Engine launcher (i.e. using devserver2)

#  set sys.path to include all modules in google_appengine\lib
if USE_GOOGLE_APPENGINE_LAUNCHER == False:

    import sys, glob
    # location of google_appengine\lib on your system

# These modules require that the path to GAE has been set, either via above or via using the GAE laucher
import TouchTerrainEarthEngine # my modules
import config  # config.py must be in this folder, use GAE modules
import webapp2
import jinja2
jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
import logging
import time
logging.Formatter.converter = time.gmtime # set to gmt as GAE uses that,

GLOBAL_request = None # HACK for duplicating request
tmp_folder = "tmp"  # dir to store zip files on the dev server

# functions for computing hillshades in EE (from EE examples)
# currently, I only use the precomputed hs
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

# example query string: ?DEM_name=USGS%2FNED&map_lat=44.59982&map_lon=-108.11694999999997&map_zoom=11&trlat=44.69741706507476&trlon=-107.97962089843747&bllat=44.50185267072875&bllon=-108.25427910156247
class MainPage(webapp2.RequestHandler):
  def get(self):                             # pylint: disable=g-bad-name

    ee.Initialize(config.EE_CREDENTIALS, config.EE_URL)
    #print self.request.GET # all args

    DEM_name = self.request.get("DEM_name")
    map_lat = self.request.get("map_lat")
    map_lon = self.request.get("map_lon")
    map_zoom = self.request.get("map_zoom")
    trlat = self.request.get("trlat")
    trlon = self.request.get("trlon")
    bllat = self.request.get("bllat")
    bllon = self.request.get("bllon")

    # default args:
    if DEM_name not in TouchTerrainEarthEngine.DEM_sources: DEM_name = 'USGS/NED' # 10m NED as default
    if map_lat == "": map_lat = "44.59982"  # Sheep Mtn, Greybull, WY
    if map_lon == "": map_lon ="-108.11695"
    if map_zoom == "": map_zoom ="11"


    # for ETOPO1 we need to first select one of the two bands as elevation
    if DEM_name == """NOAA/NGDC/ETOPO1""":
	img = ee.Image(DEM_name)
	elev = img.select('bedrock') # or ice_surface
	terrain = ee.Terrain.products(elev)
    else:
	terrain = ee.Algorithms.Terrain(ee.Image(DEM_name))

    hs = terrain.select('hillshade')

    mapid = hs.getMapId( {'gamma':1.7}) # opacity is set in JS

    # jinja will inline these variables and their values into the template and create index.html
    template_values = {
        'mapid': mapid['mapid'],
        'token': mapid['token'],
        'DEM_name': DEM_name,
        'map_lat': map_lat,
        'map_lon': map_lon,
        'map_zoom': map_zoom,
        'map_zoom': map_zoom,
        'trlat' : trlat,
        'trlon' : trlon,
        'bllat' : bllat,
        'bllon' : bllon,
    }

    # this creates a index.html "file" with mapid, token, etc. inlined
    template = jinja_environment.get_template('index.html')
    self.response.out.write(template.render(template_values))

    # delete files in tmp that are >24 hrs old is done by a cron shell script rather then by the dev server

# fake fake file init - this allows me to instantiate a FakeFile object with write-only checks disabled.
# Note that I still can't use any other OS functions on files, e.g. get their time or delete them!
# To delete old files, I use a chron job.
from google.appengine.tools.devappserver2.python import stubs
def fake__init__(self, filename, mode='r', bufsize=-1, **kwargs):
	    """Initializer. See file built-in documentation."""

	    '''# CH: disabled checks
	    if mode not in FakeFile.ALLOWED_MODES:
	      raise IOError(errno.EROFS, 'Read-only file system', filename)

	    if not FakeFile.is_file_accessible(filename):
	      raise IOError(errno.EACCES, 'file not accessible', filename)
	    '''
	    pass # debug
	    super(stubs.FakeFile, self).__init__(filename, mode, bufsize, **kwargs)

stubs.FakeFile.__init__ = fake__init__ # overwrite __init__ with fake that doesn't disable writing like the official version

# preflight page: showing some notes on how there's no used feedback until processing is done
# as I don't know how to carry over the args I get here to the export page handler's post() method,
# I store the entire request as a global and write it back later. TODO: find a better way!
class preflight(webapp2.RequestHandler):
    def __init__(self, request, response):
	    global GLOBAL_request
	    # Set self.request, self.response and self.app.
	    self.initialize(request, response)
	    GLOBAL_request = request #  dodgy way of storing request data for later use in ExportToFile()
	    #print GLOBAL_request

    def post(self):
	#print self.request.POST # all args
	self.response.headers['X-Content-Type-Options'] = 'nosniff'	# Prevent browsers from MIME-sniffing the content-type:
	self.response.headers["X-Frame-Options"] = "SAMEORIGIN"   # prevent clickjacking
	self.response.out.write('<html><body>')
	self.response.out.write("<h2>Processing started:</h2>")
	self.response.out.write("Press the Start button to process the DEM into 3D model files.<br>")
	self.response.out.write("Note that there's NO progress indicator (yet), you will only see this page trying to connect. That's OK, just be patient!<br>")
	self.response.out.write("Pressing Start again during processing has no effect.<br>")
	self.response.out.write("Once your 3D model is created, you will get a new page (Processing finished) for downloading them in a zip file.<br><br>")
	self.response.out.write('<form action="/export" method="POST" enctype="multipart/form-data">')
	self.response.out.write('<input type="hidden" maxlength="50" size="20" name="Note" id="Note" value="NULL">') # for user comment
	self.response.out.write('<input type="submit" value="Start"> </form>')
	self.response.out.write('</body></html>')

# Page that creates the 3D models (tiles) in a in-memory zip file, stores it in tmp with
# a timestamp and shows a download URL to the zip file. The args are the same as in the
# main page (via preflight by using the global) The write to tmp dir is only possible
# b/c I disable the write-only checks temporarily. This folder must already exist as it
# cannot be created by the devserver.
class ExportToFile(webapp2.RequestHandler):
    def __init__(self, request, response):
		global GLOBAL_request
		#print GLOBAL_request
		self.initialize(request, response)
		self.request = GLOBAL_request  # dodgy way to get the same query string as given to preflight

    def post(self): # make tiles in zip file and write
	#print self.request.arguments() # should be the same as given to preflight
	self.response.headers['X-Content-Type-Options'] = 'nosniff'	# Prevent browsers from MIME-sniffing the content-type:
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
	    if k[:4] == "tile": args[k] = args[k] * 10 # multiply tilewidth/height by 10 to get from cm to mm
	    #print k, args[k]
	    self.response.out.write("%s = %s <br>" % (k, str(args[k])))
	    logging.info("%s = %s" % (k, str(args[k])))

	# name of file is ms since 2000
	myname = str(int((datetime.now()-datetime(2000,1,1)).total_seconds() * 1000))

        # create zip and write to tmp
	str_buf = TouchTerrainEarthEngine.get_zipped_tiles(**args) # all args are in a dict
	fname = myname + ".zip" # create filename for zipped
	logging.info("About to write: " + tmp_folder + os.sep + fname)
	fname = tmp_folder + os.sep + fname # put in tmp folder
	ff = stubs.FakeFile(fname, "wb+") # make a Fakefile instance with write restriction disabled
	ff.write(str_buf)
	ff.close()
	logging.info("finished writing %s" % (myname))

	#str_buf = TouchTerrain.get_zipped_tiles(**args)
	#str_buf = TouchTerrain.get_zipped_tiles("USGS/NED", ntilesx=2, ntilesy=2, **args)
	#self.response.headers['Content-Type'] = 'text/zip'
	#self.response.write(str_buf)

	self.response.out.write('<br><form action="tmp/%s.zip" method="GET" enctype="multipart/form-data">' % (myname))
	self.response.out.write('<input type="submit" value="Download zip File (will be deleted in 24 hrs)" title=""> </form>')
	#self.response.out.write('<form action="/" method="GET" enctype="multipart/form-data">')
	#self.response.out.write('<input type="submit" value="Go back to selection map"> </form>')
	self.response.out.write("<br>To return to the selection map, click the back button in your browser twice")

# the pages that can be requested from the browser and the handler that will respond (get or post method)
app = webapp2.WSGIApplication([('/', MainPage), # index.html
                              ('/export', ExportToFile), # results page, generated by: <form action="/export" ....>
                              ('/preflight', preflight)],
                              debug=True)
