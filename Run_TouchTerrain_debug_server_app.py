# This simply runs TouchTerrain_app.py in the server folder
# Use this for debugging only! (Should not even be on github!)

from server.TouchTerrain_app import app
app.run(debug=False, port=8080)
print("done with TouchTerrain_server_app.py")