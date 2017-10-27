import sys
sys.path.insert(0, '/var/www/html/touchterrain/server')

from TouchTerrain_app import app as application
print "CH: touchterrain.wsgi: imported app from TouchTerrain_app.py"
