"""config.py for ISU"""
import os
from pathlib import Path

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_DIR = os.path.join(PACKAGE_DIR, "common")

# Active server implementation folder.
# "server"              = ESRI/Leaflet version (current default)
# "server_google_maps"  = legacy Google Maps version (kept for reference)
# Override with the TOUCHTERRAIN_SERVER_DIR env variable if needed.
SERVER_DIR = os.getenv('TOUCHTERRAIN_SERVER_DIR', os.path.join(PACKAGE_DIR, "server"))

# The URL of the Earth Engine API.
EE_URL = os.getenv('TOUCHTERRAIN_EE_URL', 'https://earthengine.googleapis.com')

# The service account email address authorized by your Google contact.
# Set up a service account as described here:
# https://sites.google.com/site/earthengineapidocs/creating-oauth2-service-account
EE_ACCOUNT = os.getenv('TOUCHTERRAIN_EE_ACCOUNT', 'touchterrainstandalone2022@touchterrainstandalone2022.iam.gserviceaccount.com')

EE_CREDS = os.getenv('TOUCHTERRAIN_EE_SA_CREDS', os.path.join(Path.home(), "earthengine", ".config", ".private-key.json"))
EE_PROJECT = os.getenv('TOUCHTERRAIN_EE_PROJECT', 'touchterrainstandalone2022') 


