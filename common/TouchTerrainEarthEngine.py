"""
TouchTerrainEarthEngine  - creates 3D model tiles from DEM (via Google Earth Engine or from local file)
"""

'''
@author:     Chris Harding
@license:    GPL
@contact:    charding@iastate.edu

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import sys
import os



import datetime
from StringIO import StringIO
import urllib2
import socket
import io
from zipfile import ZipFile

import httplib

from grid_tesselate import grid      # my own grid class, creates a mesh from DEM raster
from Coordinate_system_conv import * # arc to meters conversion

import numpy
from PIL import Image

import logging
import time
import random
import os.path

logging.Formatter.converter = time.gmtime

# Use zig-zag magic?
use_zigzag_magic = False

# this is my own log file, has nothing to to with the official server logging module!
#USE_LOG = False # prints to stdout instead into a log file
USE_LOG = True #

#  List of DEM sources  Earth engine offers
DEM_sources = ["""USGS/NED""", """USGS/GMTED2010""", """NOAA/NGDC/ETOPO1""", """USGS/SRTMGL1_003"""]

'''
def make_bottom_raster(width_pix, height_pix):
    """ Make a bottom image (numpy array) to b used in the stl model
        in:  tile width and height in pixels    
        out: numpy raster with mm offset from bottom
    """

    canvas = Image.new("L", (width_pix, height_pix), color=0) # black 8 bit image (0-255)  
    bg = Image.open("QR_high_redundancy.png")
    bg = bg.transpose(Image.FLIP_LEFT_RIGHT)
    
    # find upper left corner in canvas so that bg is centered
    # assume it's smaller(!) than the tile
    # 8 bit with 255 as white pixels
    bg_w, bg_h = bg.size
    w_diff = width_pix - bg_w
    h_diff = height_pix - bg_h
    
    offset_w = int(w_diff / 2)
    offset_h = int(h_diff / 2)
    
    canvas.paste(bg, (offset_w, offset_h))
    canvas.save("canvas.png") #DEBUG

    
    
    # convert to milimeters, 255 ->  one layer height
    bottom_raster = numpy.asarray(canvas).astype(numpy.float)
    bottom_raster /= 255 # normalize
    bottom_raster *= 0.2 # layer height
     
    return bottom_raster
'''

# utility function to unwrap each tile from a tile list into its info and numpy array
# if multicore processing is used, this is called via multiprocessing.map()
# tile_info["temp_file"] may contain file name to open and write into,
# otherwise a string is used as buffer.
# In both cases, the buffer and its size are returned
def process_tile(tile):
    tile_info = tile[0] # this is one individual tile!
    tile_elev_raster = tile[1]
    h,w = tile_elev_raster.shape
    #bottom_raster = make_bottom_raster(w,h)
    bottom_raster = None # None means Bottom is flat
    
    g = grid(tile_elev_raster, bottom_raster, tile_info)
    printres = tile_info["pixel_mm"]

    # zigzag processing to slow down the speed when printing the shell
    if use_zigzag_magic:
        printres = tile_info["pixel_mm"]
        width_of_1_zig_zag_mm = 50
        num_cells_per_zig = int(width_of_1_zig_zag_mm / float(tile_info["pixel_mm"]))
        zig_dist_mm, zig_undershoot_mm = 0.1, 0.02
        print "zigzag magic: num_cells_per_zig %d (%.2f mm), zig_dist_mm %.2f, zig_undershoot_mm %.2f" % (num_cells_per_zig,
                    num_cells_per_zig * printres, zig_dist_mm, zig_undershoot_mm)
        g.create_zigzag_borders(num_cells_per_zig, zig_dist_mm, zig_undershoot_mm)

    del tile_elev_raster

    # convert 3D model to a (in-memory) file (buffer)
    fileformat = tile_info["fileformat"]

    if tile_info.get("temp_file") != None:  # contains None or a file name.
        # open temp file for writing
        print >> sys.stderr, "Using temp. file", os.path.realpath(tile_info["temp_file"])
        try:
            b = open(tile_info["temp_file"], "wb+")
        except Exception as e:
            print >> sys.stderr, "Error openening:",tile_info["temp_file"], e
    else:
        b = None # means: use memory

    if  fileformat == "obj":
        b = g.make_OBJfile_buffer(temp_file=b)
        # TODO: add a header for obj
    elif fileformat == "STLa":
        b = g.make_STLfile_buffer(ascii=True, temp_file=b)
    elif fileformat == "STLb":
        b = g.make_STLfile_buffer(ascii=False, temp_file=b)
    else:
        raise ValueError("invalid file format:", fileformat)

    if tile_info.get("temp_file") != None:
        fsize = os.stat(b.name).st_size / float(1024*1024)
        b.close()
    else:
        fsize = len(b) / float(1024*1024)

    tile_info["file_size"] = fsize
    print >> sys.stderr, "tile", tile_info["tile_no_x"], tile_info["tile_no_y"], fileformat, fsize, "Mb " #, multiprocessing.current_process()
    return (tile_info, b) # return info and buffer/temp_file


# from http://scipy-cookbook.readthedocs.io/items/Rebinning.html
# Note that this seems to be the same as a nearest neightbor "interpolation" and will likely result in aliasing artifacts.
# this is only used for DEM files as GEE does the resampling already
# TODO: should try running a 3x3 gaussian kernel prior to resampling, which is supposed to lessen aliasing artifacts
def resampleDEM(a, factor ):
    ''' resample the DEM raster a by a factor
        a: 2D numpy array
        factor: down(!) sample factor, 2.0 will reduce the number of cells in x and y to 50%
    '''
    
    # get new shape of raster
    cursh = a.shape
    newsh = ( int(int(cursh[0]) / float(factor)), int(cursh[1] / float(factor)) )

    # Use PIL resize with bilinear interpolation to avoid aliasing artifacts
    orig_im = Image.fromarray(a, 'F')
    resized_im = orig_im.resize(newsh[::-1], resample=Image.BILINEAR) # x and y are swapped in numpy
    res_array = numpy.asarray(resized_im)

    return res_array


def get_zipped_tiles(DEM_name=None, trlat=None, trlon=None, bllat=None, bllon=None, # all args are keywords, so I can use just **args in calls ...
                         importedDEM=None,
                         printres=1.0, ntilesx=1, ntilesy=1, tilewidth=100,
                         basethick=2, zscale=1.0, fileformat="STLb",
                         tile_centered=False, CPU_cores_to_use=0,
                         max_cells_for_memory_only=500*500*4,
                         temp_folder = "tmp",
                         zip_file_name=None):
    """
    args:
    - DEM_name:  name of DEM layer used in Google Earth Engine, see DEM_sources
    - trlat, trlon: lat/lon of top right corner
    - bllat, bllon: lat/lon of bottom left corner
    - importedDEM: None (means get DEM from GEE) or local file name with DEM to be used instead
    - printres: resolution (horizontal) of 3D printer (= size of one pixel) in mm
    - ntilesx, ntilesy: number of tiles in x and y
    - tilewidth: width of each tile in mm (<- !!!!!), tile height is calculated automatically
    - basethick: thickness (in mm) of printed base
    - zscale: elevation (vertical scaling)
    - fileformat: format of 3D model files: "obj"  = wavefront obj (ascii)
                                            "STLa" = ascii STL
                                            "STLb" = binary STL
    - tile_centered: True-> all tiles are centered around 0/0, False, all tiles "fit together"
    - CPU_cores_to_use: 0 means use all available cores, set to 1 to force single processor use (needed for Paste) TODO: change to True/False
    - max_cells_for_memory_only: if total number of cells is bigger, use temp_file instead using memory only
    - temp_folder: the folder to put the temp files and the final zip file into
    - zip_file_name: name of zipfile containing the tiles (st/obj) and helper files
    
    returns the total size of the zip file in Mb

    """

    # Sanity checks:   TODO: should do this for all args as there might be a typo in the JSON parameter file
    if importedDEM == None:
        assert DEM_name in DEM_sources, "Error: DEM must be on of " + str(DEM_sources)
    else:
        assert os.path.exists(importedDEM), "Error: local DEM file " + importedDEM + " does not exist"

    assert fileformat in ("obj", "STLa", "STLb"), "Error: unknown 3D geometry file format:"  + fileformat + ", must be obj, STLa or STLb"

    # redirect to logfile written inside the zip file
    if USE_LOG:
        # redirect stdout to mystdout
        regular_stdout = sys.stdout
        mystdout = StringIO()
        sys.stdout = mystdout


    # number of tiles in EW (x,long) and NS (y,lat), must be ints
    num_tiles = [int(ntilesx), int(ntilesy)]

    # horizontal size of "cells" on the 3D printed model (realistically the size of the extruder)
    print3D_resolution = printres

    # use Google Earth Engine to get DEM
    if importedDEM == None:

        try:
            import ee
        except Exception as e:
            print >> sys.stderr, "Google Earth Engine module not installed", e

        region = [[bllon, trlat],#WN  NW
                  [trlon, trlat],#EN  NE
                  [trlon, bllat],#ES  SE
                  [bllon, bllat]]#WS  SW

        # get center of region as lon/lat, needed for conversion to meters
        center = [(region[0][0] + region[1][0])/2.0, (region[0][1] + region[2][1])/2.0]

        # Make a more descriptive name for the selected DEM from it's official (ee) name and the center
        # if there's a / (e.g. NOAA/NGDC/ETOPO1), just get the last, ETOPO1
        DEM_title = DEM_name
        if '/' in DEM_name:
            DEM_title = DEM_title.split('/')[-1]
        DEM_title = "%s_%.2f_%.2f" % (DEM_title, center[0], center[1])

        print "Log for creating 3D model tile(s) for ", DEM_title


        # print args to log
        args = locals() # dict of local variables
        dict_for_url = {} # dict with only those args that are valid for a URL query string
        for k in ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                     "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat"):
            v = args[k]
            if k in ("basethick", "ntilesx", "ntilesx"):
                v = int(v) # need to be ints to work with the JS UI
            print k, "=", v
            dict_for_url[k] = v

        # print full query string:
        from urllib import urlencode  #from urllib.parse import urlencode <- python 3
        print "\n", urlencode(dict_for_url),"\n"

        print "process started:", datetime.datetime.now().time().isoformat()
        logging.info("process started: " + datetime.datetime.now().time().isoformat())

        print "Region (lat/lon):\n  ", trlat, trlon, "(top right)\n  ", bllat, bllon, "(bottom left)"

        # get UTM zone of center to project into
        utm,h = LatLon_to_UTM(center)
        utm_zone_str = "UTM %d%s" % (utm,h)
        epsg = UTM_zone_to_EPSG_code(utm, h)
        epsg_str = "EPSG:%d" % (epsg)
        print "center at", center, " UTM",utm, h, ", ", epsg_str

        #get extent in meters (depending on lat of center)
        #print "center (lon/lat) at", center
        (latitude_in_m, longitude_in_m) = arcDegr_in_meter(center[1]) # returns: (latitude_in_m, longitude_in_m)
        region_size_in_degrees = [abs(region[0][0]-region[1][0]), abs(region[0][1]-region[2][1]) ]
        region_ratio_for_degrees =  region_size_in_degrees[1] / float(region_size_in_degrees[0])
        region_size_in_meters = [region_size_in_degrees[0] * longitude_in_m, # 0 -> EW, width
                                 region_size_in_degrees[1] * latitude_in_m]  # 1 -> NS, height
        region_ratio =  region_size_in_meters[1] / float(region_size_in_meters[0])

        print "lon/lat size in degrees:",region_size_in_degrees
        print "x/y size in meters:", region_size_in_meters


        # width/height (in 2D) of 3D model of ONE TILE to be printed, in mm
        print3D_width_per_tile = tilewidth # EW
        print3D_height_per_tile = (print3D_width_per_tile * num_tiles[0] * region_ratio) / float(num_tiles[1]) # NS

        # width/height of full 3D model (all tiles together)
        print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0] # width => EW
        print3D_height_total_mm = print3D_width_total_mm * region_ratio   # height => NS

        # number of samples needed to cover ALL tiles
        num_samples_lat = print3D_width_total_mm  / float(print3D_resolution) # width
        num_samples_lon = print3D_height_total_mm / float(print3D_resolution) # height
        print print3D_resolution,"mm print resolution => requested num samples (width x height):", num_samples_lat, "x",  num_samples_lon

        # get cell size (in meters) for request from ee # both should be the same
        cell_size_meters_lat = region_size_in_meters[0] / num_samples_lat # width
        cell_size_meters_lon = region_size_in_meters[1] / num_samples_lon # height

        #print  cell_size_meters_lon, "(lon) m,", cell_size_meters_lat, "(lat) m on", DEM_name, "from earth engine"
        # Note: the resolution of the ee raster does not quite match the requested raster at this cell size;
        # it's not bad, req: 1200 x 2235.85 i.e. 19.48 m cells => 1286 x 2282 which is good enough for me.
        # With this, the actually printed cell size is not exactly the print resolution but it's only ~5% off ...
        cell_size = cell_size_meters_lat # will later be used to calc the scale of the model
        print "requesting", cell_size, "m resolution "


        #
        # Get a download URL for DEM from Earth Engine
        #

        # CH: re-init should not be needed, but without it we seem to get a 404 from GEE once in a while
        import config
        try:
            ee.Initialize(config.EE_CREDENTIALS, config.EE_URL) # authenticates via .pem file
        except Exception, e:
            print e
            logging.error("ee.Initialize(config.EE_CREDENTIALS, config.EE_URL) failed: " + str(e))

        # TODO: this can probably go, the exception was prb always caused by ee not staying inited
        got_eeImage = False
        while not got_eeImage:
            try:
                image1 = ee.Image(DEM_name)
            except Exception, e:
                print e
                logging.error("ee.Image(DEM_name) failed: " + str(e))
                time.sleep(random.randint(1,10))
            else:
                break


        info = image1.getInfo() # this can go wrong for some sources, but we don't really need the info as long as we get the actual data
        print "Google Earth Engine raster:", info["id"],
        try:# 
            print info["properties"]["title"],  
        except Exception, e:
            #print e
            pass
        try: 
            print info["properties"]["link"],
        except Exception, e:
            #print e
            pass    
        print

        # https://developers.google.com/earth-engine/resample
        # projections (as will be done ingetDownload())  default to nearest neighbor, which introduces artifacts,
        # so I set the resampling mode here to bilinear or bicubic
        #image1 = image1.resample("bicubic") # only very small differences to bilinear
        image1 = image1.resample("bilinear")

        # make the request dict
        request = image1.getDownloadUrl({
            #'scale': 10, # cell size
            'scale': cell_size, # cell size in meters
            #'crs': 'EPSG:4326',
            'crs': epsg_str, # projection
            #'region': '[[-120, 35], [-119, 35], [-119, 34], [-120, 34]]',
            'region': str(region),
            #'format': 'png',
            'format': 'tiff'
            #'format': 'jpeg'
        })
        logging.info("request URL is: " + request)



        # This should retry until the request was successfull
        web_sock = None
        to = 2
        while web_sock == None:
            #
            # download zipfile from url
            #
            try:
                web_sock = urllib2.urlopen(request, timeout=20) # 20 sec timeout
            except socket.timeout, e:
                raise logging.error("Timeout error %r" % e)
            except urllib2.HTTPError, e:
                logging.error('HTTPError = ' + str(e.code))
                if e.code == 429:  # 429: quota reached
                    time.sleep(random.randint(1,10)) # wait for a couple of secs
            except urllib2.URLError, e:
                logging.error('URLError = ' + str(e.reason))
            except httplib.HTTPException, e:
                logging.error('HTTPException')
            except Exception:
                import traceback
                logging.error('generic exception: ' + traceback.format_exc())

            # at any exception wait for a couple of secs
            if web_sock == None:
                time.sleep(random.randint(1,10))

        # read the zipped folder into memory
        buf = web_sock.read()
        GEEZippedGeotiff = io.BytesIO(buf)
        GEEZippedGeotiff.flush() # not sure if this is needed ...
        #print GEEZippedGeotiff

        # pretend we've got a .zip folder (it's just in memory instead of on disk) and read the tif inside
        zipdir = ZipFile(GEEZippedGeotiff)

        # Debug: unzip both files into a folder so I can look at the geotiff and world file
        #zipdir.extractall("DEM_from_GEE")

        # get the entry for the tif file from the zip (there's usually also world file in the zip folder)
        nl = zipdir.namelist()
        tifl = [f for f in nl if f[-4:] == ".tif"]
        assert tifl != [], "zip from ee didn't contain a tif: " +  str(nl)

        # ETOPO will have bedrock and ice_surface tifs
        if DEM_name == """NOAA/NGDC/ETOPO1""":
            tif = [f for f in tifl if "ice_surface" in f][0]   # get the DEM tif that has the ice surface
        else:
            tif = tifl[0] # for non ETOPO, there's just one DEM tif in that list

        # Debug: print out the data from the world file
        #worldfile = zipdir.read(zipfile.namelist()[0]) # world file as textfile
        #raster_info = [float(l) for l in worldfile.splitlines()]  # https://en.wikipedia.org/wiki/World_file

        str_data = zipdir.read(tif)
        
        # write the GEE geotiff into the temp folder and add it to the zipped d/l folder later
        GEE_dem_filename =  temp_folder + os.sep + zip_file_name + "_dem.tif"
        with open(GEE_dem_filename, "wb+") as out:
            out.write(str_data)
            
        print "d/l geotiff size:", len(str_data) / 1048576.0, "Mb"
        imgdata = io.BytesIO(str_data) # PIL doesn't want to read the raw string from unzip
        GEEZippedGeotiff.close()
        
      
    

        # delete zipped file
        del zipdir, str_data



        # open tif with PIL
        PILimg = Image.open(imgdata)
        print PILimg
        #PILimg.save("DEM.tif") # DEBUG: save dem as local file TODO: put that also into the zip folder the user gets?

        # PIL cannot deal with mode I;16s i.e. 16 bit signed integers, and throws ValueError: unrecognized mode http://stackoverflow.com/questions/7247371/python-and-16-bit-tiff
        if PILimg.mode == "I;16S": # HACK for integer DEMs (GMTED2010/SRTM and ETOPO1)
            PILimg.mode = "I"  # with this hack, getdata(), etc. works!
            npim = numpy.asarray(PILimg, dtype=numpy.int16).astype(numpy.float32) # force to 32-bit float
        else:
            npim = numpy.asarray(PILimg).astype(numpy.float32) # make a numpy array from PIL image # TODO(?): use float32? 64?
        #print npim, npim.shape, npim.dtype
        print "full raster (height,width): ", npim.shape, npim.dtype
              
        

         # for all onshore-only sources, set water cells (undefined elevation) to 0
        if DEM_name == """USGS/NED""" or DEM_name == """USGS/SRTMGL1_003""" or DEM_name == """USGS/GMTED2010""":
            if npim.min() < -16384:  # I'm using -16384 because that's lower that any real elevation/depth, so
                                      # it's reasonable to assume that such cells are in fact just flagged as undefined
                npim = numpy.where(npim <  -16384, 0, npim) # set to 0 where < -16384
                print "set some undefined elevation values to 0"

        #end of getting DEM via GEE

    #
    # DEM comes from a local raster file (geotiff, etc.)
    #
    else:

        filename = os.path.basename(importedDEM)
        print "Log for creating", num_tiles[0], "x", num_tiles[1], "3D model tile(s) from", filename, "\n"


        print "started:", datetime.datetime.now().time().isoformat()

        import gdal # for reading writing geotiffs
        dem = gdal.Open(importedDEM)
        band = dem.GetRasterBand(1)
        npim = band.ReadAsArray()
        


        # I use PROJCS[ to get a projection name, e.g. PROJCS["NAD_1983_UTM_Zone_10N",GEOGCS[....
        # I'm grabbing the text between the first and second double-quote.
        utm_zone_str = dem.GetProjection()
        i = utm_zone_str.find('"')+1
        utm_zone_str = utm_zone_str[i:]
        i = utm_zone_str.find('"')
        utm_zone_str = utm_zone_str[:i]
        epsg_str = "N/A"

        print "projection:", utm_zone_str
        
        gdal_undef_val = band.GetNoDataValue()
        print "undefined GDAL value:", gdal_undef_val
        
        # set cells with GDAL undef to numpy NaN
        npim = numpy.where(npim == gdal_undef_val, numpy.nan, npim)
        if numpy.isnan(numpy.sum(npim)): # see if we indeed now have NaNs
            print "some cells are undefined and will be skipped in output file"
        
        # As it could happen that "undef" cells are not properly flagged,
        # I just set anything beyond a resonable elvation to NaN as well
        if npim.min() < -30000:
            npim = numpy.where(npim < -30000, numpy.nan, npim) # set to NaN where < -30000
            print "set < -30000 elevation values to NaN"        
        if npim.min() > 30000:
            npim = numpy.where(npim > 30000, numpy.nan, npim) # set to NaN where > 30000
            print "set > 30000 elevation values to NaN"                
        

        # grab the cell size in x (width)
        tf = dem.GetGeoTransform()  # In a north up image, padfTransform[1] is the pixel width, and padfTransform[5] is the pixel height. The upper left corner of the upper left pixel is at position (padfTransform[0],padfTransform[3]).
        cell_size = tf[1]
        print "real-world cell size:", cell_size

        print "z-scale:", zscale
        print "basethickness:", basethick
        print "fileformat:", fileformat
        print "tile_centered:", tile_centered


        # tile height
        whratio = npim.shape[0] / float(npim.shape[1])
        tileheight = tilewidth  * whratio
        print "tile_width:", tilewidth
        print "tile_height:", tileheight
        print3D_width_per_tile = tilewidth
        print3D_height_per_tile = tileheight   

        print3D_width_total_mm =  tilewidth * num_tiles[0]

        # given the physical width and the number of raster cells, what would be the 3D resolution?
        initial_print3D_resolution = print3D_width_total_mm / float(npim.shape[0])

        # if printres is negative, don't resample, use whatever resolution would be with the given raster
        if print3D_resolution < 0:
            print "no resampling, using the original raster resolution"

        else:
            # factor to resample initial DEM raster in order to get the user requested print3D_resolution
            print "requested printres is", print3D_resolution, "mm"

            scale_factor = print3D_resolution / float(initial_print3D_resolution)
            if scale_factor < 1.0: print "Warning: you are re-sampling below the original resolution. This is pointless. Use a larger printres value to avoid this."

            # re-sample DEM
            print "re-sampling", filename, "from", npim.shape,
            npim =  resampleDEM(npim, scale_factor)  # bi-linear inyerpolation using PIP resize
            print "to", npim.shape
            npim.flags.writeable = True # not sure why it's not writeable after the PIL interpolation but this fixes it


        DEM_title = filename[:filename.rfind('.')]

        # end local raster file

    # get horizontal map scale (1:x) so we know how to scale the elevation later
    print3D_scale_number =  (npim.shape[1] * cell_size) / (print3D_width_total_mm / 1000.0) # map scale ratio (mm -> m)

    print "map scale is 1 :", print3D_scale_number # EW scale
    #print (npim.shape[0] * cell_size) / (print3D_height_total_mm / 1000.0) # NS scale
    print3D_resolution_adjusted = (print3D_width_total_mm / float(npim.shape[0]))  # adjusted print resolution
    #print print3D_height_total_mm / float(npim.shape[0])
    print "Actual 3D print resolution (1 cell):", print3D_resolution_adjusted, "mm"

    # Adjust raster to nice multiples of tiles. If needed, crop raster from right and bottom
    remx = npim.shape[1] % num_tiles[0]
    remy = npim.shape[0] % num_tiles[1]
    if remx > 0 or  remy > 0:
        print "Cropping for %d (width) x %d (height) tiles, removing: x=%d, y=%d" % (num_tiles[0], num_tiles[1], remx, remy),
        npim = npim[0:npim.shape[0]-remy, 0:npim.shape[1]-remx]
        print " -> cropped to (y,x):",npim.shape

    # min/max elev (all tiles)
    print "elev min/max : %.2f to %.2f" % (numpy.nanmin(npim), numpy.nanmax(npim)) # use nanmin() so we can use (NaN) undefs

    # apply z-scaling
    if zscale != 1.0:
        npim *= zscale
        print "elev min/max after x%.2f z-scaling: %.2f to %.2f" % (zscale, numpy.nanmin(npim), numpy.nanmax(npim))

    """
    # plot dem
    import matplotlib.pyplot as plt
    plt.ion()
    fig = plt.figure(figsize=(7,10))
    imgplot = plt.imshow(npim, aspect=u"equal", interpolation=u"none")
    cmap_name = 'gist_earth' # gist_earth or terrain or nipy_spectral
    imgplot.set_cmap(cmap_name)
    #a = fig.add_axes()
    plt.title(DEM_name + " " + str(center))
    plt.colorbar(orientation="horizontal")
    fig.canvas.draw()
    plot_buf = fig.canvas.tostring_rgb()

    # histogram with colored bars
    rng = (npim.flatten().min(), npim.flatten().max())
    numcols = imgplot.cmap.N
    cmap = imgplot.cmap(numpy.arange(numcols)) # will only have 256 colors
    mult = 1/4.0
    numbins = numcols * mult
    bns = numpy.linspace(rng[0], rng[1], num=numbins) # => i/4 when setting colors!
    fig = plt.figure(figsize=(8,4))
    n,bins,patches = plt.hist(npim.flatten(),bins=bns, lw=0)
    maxy=max(n)
    #xext = (rng[1]-rng[0])
    #asp = xext/maxy # current aspect
    #a.set_aspect(asp/4) # make smaller in y
    for i in range(numpy.size(patches)): # set each bar's color
            plt.setp(patches[i], color=cmap[int(i/mult)])
    plt.tight_layout()
    plt.show()
    """

    #
    # create tile info dict
    #
    if importedDEM == None:
        DEM_name = DEM_name.replace("/","-") # replace / with - to be safe
    else:
        DEM_name = filename

    tile_info = {
        "DEMname": DEM_name, # name of raster requested from earth eng.
        "crs" : epsg_str, # EPSG name for UTM zone
        "UTMzone" : utm_zone_str, # UTM zone eg  UTM13N
        "scale"  : print3D_scale_number, # horizontal scale number, defines the size of the model (= 3D map): eg 1000 means 1m in model = 1000m in reality
        "pixel_mm" : print3D_resolution_adjusted, # lateral (x/y) size of a 3D printed "pixel" in mm
        "max_elev" : numpy.nanmax(npim), # tilewide minimum/maximum elevation (in meter)
        "min_elev" : numpy.nanmin(npim),
        "z_scale" :  zscale,     # z (vertical) scale (elevation exageration) factor
        "base_thickness_mm" : basethick,
        "bottom_relief_mm": 1.0,  # thickness of the bottom relief image (float), must be less than base_thickness
        "folder_name": DEM_title,  # folder/zip file name for all tiles
        "tile_centered" : tile_centered, # True: each tile's center is 0/0, False: global (all-tile) 0/0
        "tile_no_x": -1, # current(!) tile number along x
        "tile_no_y": -1, # current(!) tile number along y
        "tile_width":   print3D_width_per_tile, # in mmm
        "tile_height":  print3D_height_per_tile, # in mmm
        "full_raster_width": -1, # in pixels
        "full_raster_height": -1,
        "fileformat": fileformat,
        "temp_file": None,
    }

    #
    # Make tiles (subsets) of the full raster and generate 3D grid model
    #

    # num_tiles[0], num_tiles[1]: x, y !
    cells_per_tile_x = npim.shape[1] / num_tiles[0] # tile size in pixels
    cells_per_tile_y = npim.shape[0] / num_tiles[1]
    print "Cells per tile (x/y)", cells_per_tile_x, "x", cells_per_tile_y


    # pad full raster by one at the fringes
    npim = numpy.pad(npim, (1,1), 'edge') # will duplicate edges, including nan


    # store size of full raster
    tile_info["full_raster_height"], tile_info["full_raster_width"]  = npim.shape
    #print tile_info

    # within the padded full raster, grab tiles - but each with a 1 cell fringe!
    tile_list = [] # list of tiles to be processed via multiprocessing.map()
    for tx in range(num_tiles[0]):
        for ty in range(num_tiles[1]):

            # extract current tile from full raster
            start_x = tx * cells_per_tile_x
            end_x = start_x + cells_per_tile_x + 1 + 1
            start_y = ty * cells_per_tile_y
            end_y = start_y + cells_per_tile_y + 1 + 1

            # as STL will use float32 anyway, I cast it here to float32 instead of float (=64 bit)
            tile_elev_raster = npim[start_y:end_y, start_x:end_x].astype(numpy.float32) #  [y,x]

            # add to tile_list
            tile_info["tile_no_x"] = tx + 1
            tile_info["tile_no_y"] = ty + 1
            my_tile_info = tile_info.copy() # make a copy of the global info, so we can store tile specific info during processing


            # if raster is too large, use temp files to create the tile STL/obj files
            if tile_info["full_raster_height"] * tile_info["full_raster_width"]  > max_cells_for_memory_only:
                # open a temp file in local tmp folder
                # Note: yes, I tried using a named tempfile, which works nicely except for MP and it's too hard to figure out the issue with MP
                mytempfname =  temp_folder + os.sep + zip_file_name + str(tile_info["tile_no_x"]) + str(tile_info["tile_no_y"]) + ".tmp"

                # store temp file names (not file objects), MP will create file objects during processing
                my_tile_info["temp_file"]  = mytempfname
            tile = [my_tile_info, tile_elev_raster]   # leave it to process_tile() to unwrap the info and data parts
            tile_list.append(tile)

    #temp_folder + os.sep + zip_file_name 
    
    
    # delete large DEM array to save memory
    del npim

    if tile_info["full_raster_height"] * tile_info["full_raster_width"]  > max_cells_for_memory_only:
        print >> sys.stderr, "number of pixels:", tile_info["full_raster_height"] * tile_info["full_raster_width"], ">", max_cells_for_memory_only, " => using temp file"

    # single processing:
    if CPU_cores_to_use == 1:  # just work on the list sequentially, don't use multi-core processing
        print >> sys.stderr, "using single-core only"
        processed_list = []
        # Convert each tile into a list: [0]: updated tile info, [1]: grid object
        for t in tile_list:
            pt = process_tile(t)
            processed_list.append(pt) # append to list of processed tiles
    
    # use multi-core processing
    else:  
        print >> sys.stderr, "using multi-core"
        import multiprocessing
        pool = multiprocessing.Pool(processes=None, maxtasksperchild=1) # processes=None means use all available cores

        # Convert each tile in tile_list and return as list of lists: [0]: updated tile info, [1]: grid object
        processed_list = pool.map(process_tile, tile_list)

    # tile size is the same for all tiles
    tile_info = processed_list[0][0]
    
 
    # the tile width/height was written into tileinfo during processing
    print "%d x %d tiles, tile size %.2f x %.2f mm\n" % ( num_tiles[0], num_tiles[1], tile_info["tile_width"], tile_info["tile_height"])

    # concat all processed tiles into a zip file
    logging.info("start of creating zip file")
    total_size = 0

    # zipfile for the user
    full_zip_file_name =  temp_folder + os.sep + zip_file_name + ".zip"
    #print >> sys.stderr, "final zip is in", os.path.abspath(full_zip_file_name)
    zip_file = ZipFile(full_zip_file_name, "w", allowZip64=True)

    # add all tiles
    for p in processed_list:
            tile_info = p[0] # per-tile info
            tn = DEM_title+"_tile_%d_%d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]) + "." + fileformat[:3] # name of file inside zip
            buf= p[1] # either a string or a file object
            logging.info("adding tile %d %d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]))

            if tile_info.get("temp_file") != None: # if buf is a file object
                fname = tile_info["temp_file"]
                zip_file.write( fname , tn) # write temp file into zip
                try:
                    os.remove(fname) # on windows remove closed file manually
                except Exception as e:
                    print >> sys.stderr, "Error removing", fname, e
                else:
                    #print >> sys.stderr, "Removed temp file", fname
                    pass
            else:
                zip_file.writestr(tn, buf) # buf is a string
                del buf

            total_size += tile_info["file_size"]

            # print size and elev range
            print "tile %d %d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]), ": height: ", tile_info["min_elev"], "-", tile_info["max_elev"], "mm", ", file size: %.2f" % tile_info["file_size"], "Mb"

  

    print "\ntotal size for all tiles %.2f Mb" % total_size
    print "\nzip finished:", datetime.datetime.now().time().isoformat()


    # put logfile into zip folder
    if USE_LOG:
        sys.stdout = regular_stdout
        logstr = mystdout.getvalue()
        lines = logstr.splitlines()
        logstr = u"\r\n".join(lines) # otherwise Windows Notepad doesn't do linebreaks (vim does)
        zip_file.writestr(tile_info["folder_name"] + "_log.txt", logstr)

    # add (full) geotiff we got from GEE to zip and remove 
    if importedDEM == None:
        zip_file.write(GEE_dem_filename, "DEM.tif")
        print("added full geotiff as DEM.tiff")
        try:
            os.remove(GEE_dem_filename) 
        except Exception as e:
            print >> sys.stderr, "Error removing", GEE_dem_filename, e    

    zip_file.close() # flushes zip file
    logging.info("processing finished: " + datetime.datetime.now().time().isoformat())

    # return total  size in bytes and location of zip file
    return total_size, full_zip_file_name
#
# MAIN
#
if __name__ == "__main__":

    # Grand Canyon, Franek -109.947664, 37.173425  -> -109.905481, 37.151472
    #r = get_zipped_tiles("USGS/NED", 44.7220, -108.2886, 44.47764, -107.9453, ntilesx=1, ntilesy=1,printres=1.0,
    #                     tilewidth=120, basethick=2, zscale=1.0)

    # test for importing dm raster files
    #fname = "Oso_after_5m_cropped.tif"
    fname = "pyramid.tif" # pyramid with height values 0-255
    r = get_zipped_tiles(importedDEM=fname,  ntilesx=1, ntilesy=1,
                         printres=1,
                         tilewidth=120, basethick=2, zscale= 0.5,
                         CPU_cores_to_use=0)
    zip_string = r[0] # r[0] is a zip folder as string, r[1] is the size of the file
    with open("pyramid.zip", "w+") as f:
        f.write(zip_string)
    print "done"







# CH: as it turns out, having anything but a flat bottom is bad for printing, but I'll leave the code
# for setting a relief into the bottom raster here for now ...
"""
            #
            # make bottom image
            #
            ncols, nrows = tile_elev_raster.shape[::-1] #width/height (shape) needs to be flipped as numpy is [y,x]
            bimg = Image.new("L", (ncols, nrows), color=0) # black 8 bit image (0-255)

            # put a 1 cell wide groove at the fringe
            draw = ImageDraw.Draw(bimg)
            fos = 2 # fringe offset
            draw.rectangle([(fos, fos),  (ncols-fos, nrows-fos)], outline=64, fill=None)
            #bimg.show()

            #
            # put placement diagram in center
            #
            '''
            if num_tiles[0] * num_tiles[1] > 1: # not needed if there's only one tile ...
                w2,h2,w3,h3  = (ncols/2.0, nrows/2.0, ncols/3.0, nrows/3.0) # halfs and thirds
                # for each tile, draw a small empty box, for the current tile (tx,ty), fill the box
                sbw, sbh = w3 / num_tiles[0], h3 / num_tiles[0] # width, height  of small box
                for tnx in range(num_tiles[0]):
                    for tny in range(num_tiles[1]):
                        ul = (w3 + sbw * tnx, h3 + sbh * tny)
                        lr = (ul[0] + sbw, ul[1] + sbh)
                        if tnx == tx and tny == ty: # tx/ty is the current tile index
                            draw.rectangle([ul, lr], fill=255)
                        else:
                            draw.rectangle([ul, lr], outline=64, fill=None)
            bimg.show()
            '''




            # draw text
            fnt = ImageFont.truetype('Consolab.ttf', min(ncols,nrows)/12) # locally installed ttf file (same folder as this .py file). Use a monospaced font!
            #fnt= ImageFont.load_default() # seems to be  10 pixels high
            #lh = 14
            fw,fh = fnt.getsize("X") # font height and font width, if monospaces it's the same for all chars
            fh = fh * 1.5 # account for space between lines

            y = nrows / 6 #
            x = ncols / 5 #

            def text(txt,y,x): # local function, cause I'm lazy
                draw.text((x,y), txt, fill=255, font=fnt)
                return y + fh # simlulate line feed, y will already be at next line


            #lh = text("tile %d/%d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]), lh)
            #dts = datetime.datetime.strftime(datetime.datetime.now(),'%Y-%m-%d')
            #lh = text(tile_info["DEMname"]+" "+tile_info["UTMzone"], lh)
            y = text("tile %d %d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]), y,x)
            y = text("GeoFabLab", y, x)
            y = text("res %.2f mm" % (tile_info["pixel_mm"]), y, x)
            y = text("|", y, x)
            y = text("N", y, x)
            y = text("1:{:,}".format(int(tile_info["scale"])), y, x)
            y = text("zsc %.2f" % (tile_info["z_scale"]), y, x)
            y = text("%s" % (tile_info["UTMzone"]), y, x)



            #small_logo = logo.copy()
            #tn_size = min(tile_elev_raster.shape) / 2
            #small_logo.thumbnail((tn_size, tn_size)) # changes small_logo internally, will preserve aspect
            #upper_left_corner = (tile_elev_raster.shape[1]/2-3, tile_elev_raster.shape[0]/2-3)
            #bimg.paste(small_logo, upper_left_corner)  # paste into center
            #bimg.show()


            #bimg.show()
            bimg = bimg.transpose(Image.FLIP_LEFT_RIGHT) # text needs to be flipped, but seems to screw up draw !
            #bimg.show()

            # Convert bimg to numpy, normalize and scale
            bottom_elev = numpy.asarray(bimg).astype(numpy.float)
            #print bottom_elev.shape, bottom_elev.min(), bottom_elev.max()
            bottom_elev /= 255.0 # normalize from max 8 bit value (255) to 1.0
            #print bottom_elev.min(), bottom_elev.max() # normalized to 0 - 1.0
            bottom_elev *= tile_info["bottom_relief_mm"]   # scale

            #
            # Make holes for magnets "magnet_hole_mm" -> (diameter, height)
            #
            if tile_info["magnet_hole_mm"][1] > tile_info["base_thickness_mm"]:
                print "Warning: base thickness", tile_info["base_thickness_mm"], "is not thicker than height of magnet hole", tile_info["magnet_hole_mm"][1]
            himg = Image.new("L", (ncols, nrows), color=0) # binary "mask"
            draw = ImageDraw.Draw(himg) # draw into it
            dia = math.ceil(tile_info["magnet_hole_mm"][0] / tile_info["pixel_mm"]) # diameter in px
            ofs_mm = 4.0 # offset from border in mm, same in x and y
            of = math.ceil(ofs_mm / tile_info["pixel_mm"])# offset in pixels

            bb_list = [ # list of bounding boxes (ulx,uly, lrx,lry) to draw a hole into
                (of, of, of+dia, of+dia), # ul
                (ncols-of-dia, of, ncols-of, of+dia), # ur
                (of, nrows-of-dia, of+dia, nrows-of), # ll
                (ncols-of-dia, nrows-of-dia, ncols-of, nrows-of), # lr
                (ncols/2-dia/2, nrows/2-dia/2, ncols/2+dia/2, nrows/2+dia/2), # center
                ]

            for bb in bb_list:
                #print bb
                draw.ellipse(bb, fill=255, outline=255)

            #print "Creating", len(bb_list), "holes for magnets, diameter:", tile_info["magnet_hole_mm"][0], "mm, height", tile_info["magnet_hole_mm"][1], "mm"
            #himg.show()

            # Convert himg to numpy and mult by hole height
            hole_elev = numpy.asarray(himg).astype(numpy.float)
            hole_elev /= hole_elev.max() # normalize to 0 - 1.0
            hole_thickness = tile_info["magnet_hole_mm"][1]
            hole_elev *= hole_thickness # mult 1 (=hole) by height
            #print hole_elev.shape, hole_elev.min(), hole_elev.max()

            # integrate into bottom_elev array
            bottom_elev = numpy.maximum(bottom_elev, hole_elev)
            #print bottom_elev.min(), bottom_elev.max()

            # test: set an internal region to Nan
            #for n in range(20,25):
                    #tile_elev_raster[n,n] = numpy.nan
                    #tile_elev_raster[n,n-1] = numpy.nan
                    #tile_elev_raster[n-1,n] = numpy.nan

            """
