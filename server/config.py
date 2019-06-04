"""config.py for ISU"""
import os

from oauth2client.service_account import ServiceAccountCredentials
from ee import oauth
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
EE_PRIVATE_KEY_FILE = os.getenv('TOUCHTERRAIN_EE_PRIVATE_KEY_FILE', 'server/privatekey.pem')

# Location of the file containing the google maps key
GOOGLE_MAPS_KEY_FILE = os.getenv('TOUCHTERRAIN_GOOGLE_MAPS_KEY_FILE', 'GoogleMapsKey.txt')

# DEBUG_MODE will be True if running in a local development environment.
DEBUG_MODE = ('SERVER_SOFTWARE' in os.environ and
              os.environ['SERVER_SOFTWARE'].startswith('Dev'))

# Set up the appropriate credentials based on the new oauth serviceaccount method since oauthclient 2.0
EE_CREDENTIALS = ServiceAccountCredentials.from_p12_keyfile(EE_ACCOUNT, EE_PRIVATE_KEY_FILE, scopes=oauth.SCOPES)
