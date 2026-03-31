# This script runs a local Flask server, useful for debugging.
# Must be run from the project root folder.

#import debugpy
# Listen on port 5678 for an incoming connection
#debugpy.listen(("localhost", 5678))
#print("Waiting for debugger attach...")
# Optionally, uncomment the next line to pause execution until the debugger attaches
#debugpy.wait_for_client()

# Note: this will run the server from the folder set in common\config.py, either
# "server"              = ESRI/Leaflet version (current default) or
# "server_google_maps"  = legacy Google Maps version (kept for reference)
# to change this you need to edit common\config.py
 
from touchterrain.server.TouchTerrain_app import app
from multiprocessing import freeze_support
if __name__ == "__main__":
    freeze_support()
    app.run(debug=False, port=8080, use_reloader=False)