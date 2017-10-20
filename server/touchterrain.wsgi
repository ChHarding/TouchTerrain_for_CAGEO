import sys
# CH: I don't think we need GAE anymore (?)
#sys.path.insert(0, '/usr/local/bin/google_appengine')
#sys.path.insert(0, '/usr/local/bin/google_appengine/lib')
sys.path.insert(0, '/var/www/html/touchterrain/server')

from TouchTerrain_app import app as application
print "CH: touchterrain.wsgi: imported app from TouchTerrain_app.py"
