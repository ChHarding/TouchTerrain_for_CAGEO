from touchterrain.common import config
import os
import platform

# TouchTerrain server config settings

#
# 5/2025: changed recaptcha file location to /tmp to make them not web accessible. 
# Miles made /tmp read-only so it doesn't get wiped on rebuilds
#

#
# file for Recptcha v3 keys
#

# Win debug server
_system_name = platform.system().lower()
if _system_name == "windows":
    RECAPTCHA_V3_KEYS_FILE = os.path.join(config.SERVER_DIR, "Recaptcha_v3_keys.txt")
elif _system_name in ("linux", "darwin"): # linux or MaxOS
    RECAPTCHA_V3_KEYS_FILE = "/tmp/Recaptcha_v3_keys.txt"
else: # Neither
    print(f"ERROR: Unsupported OS '{platform.system()}'; using local server directory for Recaptcha keys.")
    RECAPTCHA_V3_KEYS_FILE = os.path.join(config.SERVER_DIR, "Recaptcha_v3_keys.txt")

# log for recaptcha v3, — set to None to disable logging
#RECAPTCHA_V3_LOG_FILE = None
RECAPTCHA_V3_LOG_FILE = os.path.join(config.SERVER_DIR, 'Recaptcha_v3_log.txt')


# DEBUG_MODE will be True if running in a local development environment.
DEBUG_MODE = ('SERVER_SOFTWARE' in os.environ and
              os.environ['SERVER_SOFTWARE'].startswith('Dev'))

# Defaults

# type of server:
#SERVER_TYPE = "flask_local" # so I can run the server inside a debugger, needs to run with single core!
SERVER_TYPE = "gnunicorn"

# multiprocessing: This will not work under gnunicorn but does work on my local Win10 dev server
# It should also work whe using standalone mode.
NUM_CORES = 1 # 0 means: use all cores, 1 means: use one core, etc. None mean 1 core
if SERVER_TYPE == "flask_local": NUM_CORES = 1 # 1 means don't use multi-core at all


# limits for ISU server

# for STL/OBJ don't even start with a DEM bigger than that number. GeoTiff export is this * 100!
# Note: Must not exceed 8,000,000!
# MAX_CELLS_PERMITED =   1000 * 1000 * 4  # private
MAX_CELLS_PERMITED =   1000 * 1000 * 0.7

# if DEM has > this number of cells, use tempfile instead of memory
MAX_CELLS = MAX_CELLS_PERMITED / 4

# folders
TMP_FOLDER = os.getenv('TOUCHTERRAIN_TMP_FOLDER', os.path.join(config.SERVER_DIR, "tmp"))
DOWNLOADS_FOLDER = os.getenv('TOUCHTERRAIN_DOWNLOADS_FOLDER', os.path.join(config.SERVER_DIR, "downloads"))
PREVIEWS_FOLDER = os.getenv('TOUCHTERRAIN_PREVIEWS_FOLDER', os.path.join(config.SERVER_DIR, "previews"))

# ESRI/ArcGIS Location Platform API key.
# None  = use the free public tile CDN (server.arcgisonline.com) — no account needed,
#         but officially unsupported for production use.
# <key> = use the official ArcGIS Location Platform CDN (ibasemaps-api.arcgis.com)
#         with proper attribution and usage analytics.
#
# To get a free key:
#   1. Create a developer account at https://developers.arcgis.com
#   2. Dashboard -> New Application -> create app
#   3. API Keys -> Generate key, enable "Basemaps" and "Geocoding" scopes
#   4. Paste the key string below
#ESRI_API_KEY = None
ESRI_API_KEY = "AAPTaE3l9gdOIfb3Lahd7EcDySw..FsU5ZGzkCfTYJsYfCRfQHQDUaRTLhXm-LJMjEqwPcUyBKANFtC-kXx_cejQZmUvfFTNSREVrBOm3-gDYo3szp_P-LyGUaNYYe-UmdzRlioTlLHvCXHzfrHaeWHaaDiZDjnoV5uD3yef-laJ2358EUefeF_mz481dUbGnS0Sf3vWGBOzCwlHvovG1ikQ-n4qfsXTGladVPiHSFi54L66foBfHJLb7wqUiP-Zr2IZ1OVBjckA35Znkc__VluaBK-V8GvHVqxlLaUilAT1_yNPrasRz"
# CH Note: public but limited to our domain. It will need to be renewed on Mar. 4, 2027

# Threshold area (km²) used by the hillshade scale cap:
# viewports larger than this get the hillshade rendered at GEE_HILLSHADE_SCALE_M
# instead of full native resolution, to reduce GEE tile-rendering quota usage.
GEE_HIRES_AREA_LIMIT_KM2 = 50.0

# Maximum resolution (metres/pixel) used to render the hillshade map preview.
# GEE renders tiles at full native resolution by default; capping at 10 m is
# visually indistinguishable for a preview but greatly reduces compute quota
# for 1 m / 5 m DEMs.  Set to 0 or None to disable the cap entirely.
GEE_HILLSHADE_SCALE_M = 10.0

# This will be inlined in index.html to enable Google Analytics, However, this is
# my tracking id, so if you use google analytics, make sure to use your own Tracking ID!
GOOGLE_ANALYTICS_TRACKING_ID = "G-EGX5Y3PBYH"
# If you don't wan to use GA, set this to "" !
