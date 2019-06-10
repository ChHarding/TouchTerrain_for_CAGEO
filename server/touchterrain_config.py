# TouchTerrain server config settings


# Defaults

# type of server:
SERVER_TYPE = "flask_local" # so I can run the server inside a debugger, needs to run with single core!

# multiprocessing:
NUM_CORES = 0 # 0 means: use all cores
if SERVER_TYPE == "flask_local": NUM_CORES = 1 # 1 means don't use multi-core at all


# limits for ISU server (Mar. 2019)

# for STL/OBJ don't even start with a DEM bigger than that number. GeoTiff export is this * 100!
MAX_CELLS_PERMITED =   1000 * 1000 * 0.4   

# if DEM has > this number of cells, use tempfile instead of memory
MAX_CELLS = MAX_CELLS_PERMITED / 4  


TMP_FOLDER = "tmp" # for temp files, also for zips in standalone.
                   # for server/flask, static is always used for the zips!
#--------------------------------------------------------------------------------

# Overrides
#MAX_CELLS = 0  # CH: test to force using tempfiles
