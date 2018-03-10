# TouchTerrain server config settings


# Defaults

# type of server:
SERVER_TYPE = "Apache" # "paste" or "Apache"
#SERVER_TYPE = "paste" # so I can run the server inside a debugger, needs to run with single core!

# multiprocessing:
NUM_CORES = 0 # 0 means: use all cores
if SERVER_TYPE == "paste": NUM_CORES = 1 # 1 means don't use multi-core at all

# when to use tempfiles instead of memory to store processed tiles
MAX_CELLS =   1000 * 1000  # if DEM has > this number of cells, use tempfile instead of memory

MAX_LOAD_FACTOR = 1000 # if width / printres * num tiles is > than this processing is not started

TMP_FOLDER = "tmp" # local to this folder! for temp files and final zip
#--------------------------------------------------------------------------------

# Overrides
#MAX_CELLS = 0  # CH: test to force using tempfiles
