# TouchTerrain server config settings


# Defaults

# type of server:
SERVER_TYPE = "Apache" # "paste" or "Apache"
#SERVER_TYPE = "paste" # so I can run the server inside a debugger, needs to run with single core!

# multiprocessing:
NUM_CORES = 0 # 0 means: use all cores
if SERVER_TYPE == "paste": NUM_CORES = 1 # 1 means don't use multi-core at all

# for STL/OBJ don't even start with a DEM bigger than that number. GeoTiff export is this * 50!
MAX_CELLS_PERMITED =   1000 * 1000 * 0.4   

# if DEM has > this number of cells, use tempfile instead of memory
MAX_CELLS = MAX_CELLS_PERMITED / 4  


TMP_FOLDER = "tmp" # local to this folder! for temp files and final zip
#--------------------------------------------------------------------------------

# Overrides
#MAX_CELLS = 0  # CH: test to force using tempfiles
~                                                                                                                  
~                                                       