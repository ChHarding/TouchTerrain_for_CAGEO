"""config.py for ISU"""
import os

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_DIR = os.path.join(PACKAGE_DIR, "common")
SERVER_DIR = os.path.join(PACKAGE_DIR, "server")

# The URL of the Earth Engine API.
EE_URL = os.getenv('TOUCHTERRAIN_EE_URL', 'https://earthengine.googleapis.com')

# The service account email address authorized by your Google contact.
# Set up a service account as described here:
# https://sites.google.com/site/earthengineapidocs/creating-oauth2-service-account
EE_ACCOUNT = os.getenv('TOUCHTERRAIN_EE_ACCOUNT', 'earthengine@touchterrain.iam.gserviceaccount.com')
