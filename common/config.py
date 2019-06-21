"""config.py for ISU"""
import os

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_DIR = os.path.join(PACKAGE_DIR, "common")
SERVER_DIR = os.path.join(PACKAGE_DIR, "server")

#import ee
#from oauth2client.appengine import AppAssertionCredentials

# The URL of the Earth Engine API.
EE_URL = os.getenv('TOUCHTERRAIN_EE_URL', 'https://earthengine.googleapis.com')

# The service account email address authorized by your Google contact.
# Set up a service account as described here:
# https://sites.google.com/site/earthengineapidocs/creating-oauth2-service-account
EE_ACCOUNT = os.getenv('TOUCHTERRAIN_EE_ACCOUNT', 'earthengine@touchterrain.iam.gserviceaccount.com')

# The private key associated with your service account in Privacy Enhanced
# Email format (.pem suffix).  To convert a private key from the RSA format
# (.p12 suffix) to .pem, run the openssl command like this:
# openssl pkcs12 -in downloaded-privatekey.p12 -nodes -nocerts > privatekey.pem
EE_PRIVATE_KEY_FILE = os.getenv('TOUCHTERRAIN_EE_PRIVATE_KEY_FILE', os.path.join(SERVER_DIR, 'privatekey.pem'))

