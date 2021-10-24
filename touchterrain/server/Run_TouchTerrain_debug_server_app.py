# This script runs a local Flask server, which can be usefull for debugging
# Note that this has to be run in the project root folder! (I put it here b/c it's server related)
# To get a proper Google Map you will need to create a GoogleMapsKey.txt file that contains
# a valid API key as a single string
# Note that this won't run multi-core processing (I think ...)

from touchterrain.server.TouchTerrain_app import app
app.run(debug=False, port=8080)
