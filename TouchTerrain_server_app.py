# This simply runs TouchTerrain_app.py in the server folder

# for the standalone version, either use the jupyter notebook or
# manually run TouchTerrain_standalone.py (both are in the standalone folder)

import sys
sys.path.insert(0, './server')
sys.path.insert(0, './common')

import server.TouchTerrain_app.py
print("done with TouchTerrain_server_app.py")