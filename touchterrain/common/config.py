"""config.py for ISU"""
import os
from pathlib import Path

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_DIR = os.path.join(PACKAGE_DIR, "common")
SERVER_DIR = os.path.join(PACKAGE_DIR, "server")

# The URL of the Earth Engine API.
EE_URL = os.getenv('TOUCHTERRAIN_EE_URL', 'https://earthengine.googleapis.com')

# The service account email address authorized by your Google contact.
# Set up a service account as described here:
# https://sites.google.com/site/earthengineapidocs/creating-oauth2-service-account
EE_ACCOUNT = os.getenv('TOUCHTERRAIN_EE_ACCOUNT', 'earthengine@touchterrain.iam.gserviceaccount.com')

EE_CREDS = os.getenv('TOUCHTERRAIN_EE_SA_CREDS', os.path.join(Path.home(), "earthengine", ".config", ".private-key.json"))
EE_PROJECT = os.getenv('TOUCHTERRAIN_EE_PROJECT', 'touchterrainstandalone2022') 


# OSGeo/GDAL PROJ variable override (folder that contains proj.db, used for projections)
# see addGPXToModel in TouchTerrainGPX.py for more on that unholy mess ...
PROJ_DIR = None # None => don't override or something like r"C:\Users\charding\anaconda3_3.7\Lib\site-packages\osgeo\data\proj"
                # make sure to use a raw (r"...") string on Windows!

#PROJ_DIR = r"C:\Users\charding\anaconda3_3.7\Lib\site-packages\osgeo\data\proj"
