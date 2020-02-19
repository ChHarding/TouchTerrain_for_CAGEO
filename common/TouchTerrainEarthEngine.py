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
from io import StringIO
import urllib.request, urllib.error, urllib.parse
import socket
import io
from zipfile import ZipFile

import http.client

import common
from common.grid_tesselate import grid      # my own grid class, creates a mesh from DEM raster
from common.Coordinate_system_conv import * # arc to meters conversion

import numpy
from PIL import Image
import gdal # for reading/writing geotiffs

import time
import random
import os.path


# get root logger, will later be redirected into a logfile
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# utility to print to stdout and to logger.info
def pr(*arglist):
    s = ""
    for a in arglist:
        s = s + str(a) + " "
    print(s)
    logger.info(s)


# Use zig-zag magic? 
use_zigzag_magic = False

#  List of DEM sources  Earth engine offers and their nominal resolutions (only used for guessing the size of a geotiff ...)
DEM_sources = ["""USGS/NED""", """USGS/GMTED2010""", """NOAA/NGDC/ETOPO1""", """USGS/SRTMGL1_003"""]

#
def make_bottom_raster(image_file_name, shape):
    """ Make a bottom image (numpy array) to be used in the stl model

        in: image_file_name. Must be 1 band/greyscale image, 
            will be scaled to fit the tile with at least a 5% fringe  
            shape: width [0] and height [1] of TOP ! raster
        out: numpy raster with 0 - 255 (with 0 = buildplate, 1 = max relieft) or None on error
    """
    try:
        bg = Image.open(image_file_name)
    except Exception as e:
        print("Warning:", image_file_name, "not found, using flat bottom",  e)    

    bg = bg.transpose(Image.FLIP_LEFT_RIGHT)
    w,h = bg.size
    
    # resize bg so it is at least 10% less in height and width
    top_w = shape[1] - shape[1]/10.0 # shape is numpy and has [0]=y, [1]=x
    top_h = shape[0] - shape[0]/10.0
    ratio = max(w / float(top_w), h / float(top_h))  
    scaled_size = int(w / ratio), int(h / ratio)  
    #bg = bg.resize(scaled_size, Image.LANCZOS)
    bg = bg.resize(scaled_size) # nearest neighbor
    #bg.save("bg_resized.png")
    print("Used", image_file_name, "for bottom relief, rescaled to", scaled_size, end=' ') 
    
    # white 8 bit image (0-255) (flip shape as it's from numpy)
    canvas = Image.new("L", shape[::-1], color=255)  \
    
    # find upper left corner in canvas so that bg is centered
    bg_w, bg_h = scaled_size
    w_diff = shape[1] - bg_w
    h_diff = shape[0] - bg_h
    offset = int(w_diff / 2), int(h_diff / 2)
    
    canvas.paste(bg, offset)
    #canvas.save("canvas.png") #DEBUG
    
    # convert to 0 (bottom = buildplate) to 1 (top)
    bottom_raster = numpy.asarray(canvas).astype(numpy.float)
    bottom_raster /= 255.0 # normalize
    bottom_raster *= -1
    bottom_raster += 1
     
    return bottom_raster



# utility function to unwrap a tile tuple into its info and numpy array parts
# if multicore processing is used, this is called via multiprocessing.map()
# tile_info["temp_file"] contains the file name to open and write into (creating a file object)
# but if it's None, a buffer is made instead.
# the tile info dict (with the file/buffer size) and the buffer (or the file's name) are returns as a tuple
def process_tile(tile_tuple):
    tile_info = tile_tuple[0] # has info for this individual tile
    tile_elev_raster = tile_tuple[1]
    
    print("processing tile:", tile_info['tile_no_x'], tile_info['tile_no_y'])
    #print numpy.round(tile_elev_raster,1)
    
    # create a bottom relief raster (values 0.0 - 1.0)
    if tile_info["bottom_image"] != None and tile_info["no_bottom"] != None:
        logger.debug("using " + tile_info["bottom_image"] + " as relief on bottom")
        bottom_raster = make_bottom_raster(tile_info["bottom_image"], tile_elev_raster.shape)
        #print "min/max:", numpy.nanmin(bottom_raster), numpy.nanmax(bottom_raster)
        bottom_raster *= (tile_info["base_thickness_mm"] * 0.8) # max relief is 80% of base thickness to still have a bit of "roof" 
        print("min/max:", numpy.nanmin(bottom_raster), numpy.nanmax(bottom_raster)) # range of bottom raster
    else:
        bottom_raster = None # None means Bottom is flat
    
    g = grid(tile_elev_raster, bottom_raster, tile_info)
    printres = tile_info["pixel_mm"]

    del tile_elev_raster

    # convert 3D model to a (in-memory) file (buffer)
    fileformat = tile_info["fileformat"]

    
    if tile_info.get("temp_file") != None:  # contains None or a file name.
        print("Writing tile into temp. file", os.path.realpath(tile_info["temp_file"]), file=sys.stderr)
        temp_fn = tile_info.get("temp_file")
    else:
        temp_fn = None # means: use memory

    # Create triangle "file" either in a buffer or in a tempfile
    # if file: open, write and close it, b will be temp file name
    if  fileformat == "obj":
        b = g.make_OBJfile_buffer(temp_file=temp_fn)
        # TODO: add a header for obj
    elif fileformat == "STLa":
        b = g.make_STLfile_buffer(ascii=True, no_bottom=tile_info["no_bottom"], 
                                  no_normals=tile_info["no_normals"], temp_file=temp_fn)
    elif fileformat == "STLb":
        b = g.make_STLfile_buffer(ascii=False, no_bottom=tile_info["no_bottom"], 
                                  no_normals=tile_info["no_normals"], temp_file=temp_fn)
    else:
        raise ValueError("invalid file format:", fileformat)

    if temp_fn != None:
        fsize = os.stat(temp_fn).st_size / float(1024*1024)
    else:
        fsize = len(b) / float(1024*1024)


    tile_info["file_size"] = fsize
    print("tile", tile_info["tile_no_x"], tile_info["tile_no_y"], fileformat, fsize, "Mb ", file=sys.stderr) #, multiprocessing.current_process()
    return (tile_info, b) # return info and buffer/temp_file NAME


""" 
CH: converting to PIL, rotating it and back to numpy works but that changes the real-world cell size and
I don't yet know how to calculate that cell size from the rotation angle. Revisit later ...
 
def rotateDEM(a, rot_degs):
    ''' rotate DEM by rot_deg (in degrees ccw)
        returned numpy array will be size adjusted to the rotation 
        Does not use bilinear interpolation to ensure that the values used for 
        undefined (e.g. -9999999) are not used, as this may lead to weird new values between min and undef
    '''
    
    #print "rotate1 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))
 
    img = Image.fromarray(a, 'F')
    print "prerot", img.size
    #img = img.rotate(rot_degs, resample=Image.BILINEAR, expand=True) # expand so that the rotated version is fully captured
    img = img.rotate(rot_degs, resample=Image.NEAREST, expand=True) # don't use bilinear here as that might not work with undefined/NaN values!
    print "prerot", img.size
    a = numpy.asarray(img)
    
    #print "rotate2 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))
    
    return a
"""

def resampleDEM(a, factor):
    ''' resample the DEM raster a by a factor
        a: 2D numpy array
        factor: down(!) sample factor, 2.0 will reduce the number of cells in x and y to 50%
        Should(?) deal with undef/NaN ...
    '''    
    
    # get new shape of raster
    cursh = a.shape
    newsh = ( int(int(cursh[0]) / float(factor)), int(cursh[1] / float(factor)) )
    
    #print "resample1 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))
    has_nan = False
    if numpy.isnan(numpy.sum(a)):  
        has_nan = True
        nanmin = numpy.nanmin(a)
        a = numpy.where(numpy.isnan(a), nanmin-1, a) # swap NaN to a bit smaller than valid min, so the interpolation works
        #print "resample2 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))

    # Use PIL resize with bilinear interpolation to avoid aliasing artifacts
    img = Image.fromarray(a)  # was using fromarray(a, 'F') but that affected the elevation value, which were much lower!
    #print "pre-resam", img.size
    #print "resamp 2.5 min/max", img.getextrema()

    img  = img.resize(newsh[::-1], resample=Image.BILINEAR) # x and y are swapped in numpy
    #print "post-resam", img.size
    a = numpy.asarray(img)
    #print "resample3 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))
    
    if has_nan:  # swap NaN back in
        a = numpy.where(a < nanmin, numpy.nan, a)
        #print "resample4 min/max : %.2f to %.2f" % (numpy.nanmin(a), numpy.nanmax(a))
    
    # fix CH Jan 2, 20: needs to be a copy, PIL locks it to read only!
    # Thanks to ljverge for finding this!
    a = numpy.copy(a) 
    return a


def get_zipped_tiles(DEM_name=None, trlat=None, trlon=None, bllat=None, bllon=None, # all args are keywords, so I can use just **args in calls ...
                         importedDEM=None,
                         printres=1.0, ntilesx=1, ntilesy=1, tilewidth=100,
                         basethick=2, zscale=1.0, fileformat="STLb",
                         tile_centered=False, CPU_cores_to_use=0,
                         max_cells_for_memory_only=500*500*4,
                         temp_folder = "tmp",
                         zip_file_name=None,
                         no_bottom=False,
                         bottom_image=None,
                         ignore_leq=None,
                         unprojected=False,
                         only=None,
                         original_query_string=None,
                         no_normals=True,
                         projection=None,
                         **otherargs):
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
                                            "GeoTiff" = DEM raster only, no 3D geometry
    - tile_centered: True-> all tiles are centered around 0/0, False, all tiles "fit together"
    - CPU_cores_to_use: 0 means use all available cores, set to 1 to force single processor use (needed for Paste) TODO: change to True/False
    - max_cells_for_memory_only: if total number of cells is bigger, use temp_file instead using memory only
    - temp_folder: the folder to put the temp files and the final zip file into
    - zip_file_name: name of zipfile containing the tiles (st/obj) and helper files
    - no_bottom: don't create any bottom triangles. The STL file is not watertight but should still print fine with most slicers (e.g. Cura) and is much smaller
    - bottom_image: 1 band greyscale image to use as bottom relief raster, same for _each_ tile! see make_buttom_raster)
    - ignore_leq: ignore elevation values <= this value, good for removing offshore data 
    - unprojected: don't apply UTM projectin, can only work when exporting a Geotiff as the mesh export needs x/y in meters
    - only: 2-list with tile index starting at 1 (e.g. [1,2]), which is the only tile to be processed 
    - original_query_string: the query string from the app, including map info. Put into log only. Good for making a URL that encodes the app view
    - no_normals: True -> all normals are 0,0,0, which speeds up processing. Most viewers will calculate normals themselves anyway
    - projection: EPSG number (as int) of projection to be used. Default (None) use the closest UTM zone
    returns the total size of the zip file in Mb

    """
    # Sanity checks:   TODO: use better exit on error instead of throwing an assert exception
    assert fileformat in ("obj", "STLa", "STLb", "GeoTiff"), "Error: unknown 3D geometry file format:"  + fileformat + ", must be obj, STLa, STLb (or GeoTiff when using local raster)"
    
    if importedDEM == None: # GEE as DEM source
        assert DEM_name in DEM_sources, "Error: DEM source must be one of: " + ", ".join(DEM_sources)
        if fileformat != "GeoTiff": 
            assert unprojected == False, "Error: STL/OBJ export cannot use unprojected, only available for GeoTiff export"
    else: # local raster file as DEM source
        assert os.path.exists(importedDEM), "Error: local DEM raster file " + importedDEM + " does not exist"
        assert fileformat != "GeoTiff", "Error: it's silly to make a Geotiff from a local DEM file (" + importedDEM + ") instead of a mesh file format ..."

    assert not (bottom_image != None and no_bottom == True), "Error: Can't use no_bottom=True and also want a bottom_image (" + bottom_image + ")"
    assert not (bottom_image != None and basethick <= 0.5), "Error: base thickness (" + str(base_thick) + ") must be > 0.5 mm when using a bottom relief image"


    # set up log file
    log_file_name = temp_folder + os.sep + zip_file_name + ".log"
    log_file_handler = logging.FileHandler(log_file_name, mode='w+')
    formatter = logging.Formatter("%(message)s")
    log_file_handler.setFormatter(formatter)
    logger.addHandler(log_file_handler)     

    # number of tiles in EW (x,long) and NS (y,lat), must be ints
    num_tiles = [int(ntilesx), int(ntilesy)]
    
    if only != None:
        assert only[0] > 0 and only[0] <= num_tiles[0], "Error: x index of only tile out of range"
        assert only[1] > 0 and only[1] <= num_tiles[1], "Error: y index of only tile out of range"
    

    # horizontal size of "cells" on the 3D printed model (realistically the size of the extruder)
    print3D_resolution = printres  


    #
    # A) use Google Earth Engine to get DEM
    #
    if importedDEM == None:
        try:
            import ee
        except Exception as e:
            print("Earth Engine module (ee) not installed", e, file=sys.stderr)

        region = [[bllon, trlat],#WS  NW
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

        pr("Log for creating 3D model tile(s) for ", DEM_title, "\n")

        # print args to log
        args = locals() # dict of local variables
        dict_for_url = {} # dict with only those args that are valid for a URL query string
        for k in ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                     "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat"):
            v = args[k]
            if k in ("basethick", "ntilesx", "ntilesx"):
                v = int(v) # need to be ints to work with the JS UI
            pr(k, "=", v)
            dict_for_url[k] = v

        for k in ("no_bottom", "bottom_image", "ignore_leq", "unprojected", "only", 
                  "original_query_string", "no_normals", "projection"):
            if args.get(k) != None: # may not exist ...
                v = args[k]
                pr(k, "=", v)            
                dict_for_url[k] = v
        
        
        # print full query string: 
        # TODO: would not actually work as a URL b/c it misses the google map data!
        #from urllib import urlencode  #from urllib.parse import urlencode <- python 3
        #print "\n", urlencode(dict_for_url),"\n"

        pr("\nprocess started: " + datetime.datetime.now().time().isoformat())

        pr("\nRegion (lat/lon):\n  ", trlat, trlon, "(top right)\n  ", bllat, bllon, "(bottom left)")
        
        
        #
        # Figure out which projection to use when getting DEM from GEE
        #
        if unprojected == False:
            if projection != None:
                epsg = projection
                epsg_str = "EPSG:%d" % (epsg)
                utm_zone_str = epsg_str
                pr("using " + epsg_str + " as projection")
            elif bllat > 70: # too far north for UTM, use Arctic Polar Stereographic
                utm_zone_str = "WGS 84 / Arctic Polar Stereographic"
                epsg = 3995
                epsg_str = "EPSG:%d" % (epsg)
                pr("Too far north for UTM - using Arctic Polar Stereographic projection (EPSG 3995)")
                
            elif trlat < -55: # too far south for UTM, use Arctic Polar Stereographic
                utm_zone_str = "WGS 84 / Arctic Polar Stereographic"
                epsg = 3031
                epsg_str = "EPSG:%d" % (epsg)
                pr("Too far south for UTM - using Antarctic Polar Stereographic projection (EPSG 3031)")               
            else:       
                # get UTM zone of center to project into
                utm,h = LatLon_to_UTM(center)
                utm_zone_str = "UTM %d%s" % (utm,h)
                epsg = UTM_zone_to_EPSG_code(utm, h)
                epsg_str = "EPSG:%d" % (epsg)
                pr("center at", center, " UTM",utm, h, ", ", epsg_str)
        else:
            epsg_str = "unprojected"
            utm_zone_str = "unprojected"
            
        # Although pretty good, this is still an approximation and the cell resolution to be
        # requested is therefore also not quite exact, so we need to adjust after the EE raster is downloaded, 
        (latitude_in_m, longitude_in_m) = arcDegr_in_meter(center[1]) # returns: (latitude_in_m, longitude_in_m)
        region_size_in_degrees = [abs(region[0][0]-region[1][0]), abs(region[0][1]-region[2][1]) ]
        pr("lon/lat size in degrees:",region_size_in_degrees)        
        region_ratio_for_degrees =  region_size_in_degrees[1] / float(region_size_in_degrees[0])
        
        #
        # figure out an (approximate) cell size to request from GEE
        # Once we got the GEE raster, we can redo the print res and tile height (for a given tile width) properly
        # 
        region_size_in_meters = [region_size_in_degrees[0] * longitude_in_m, # 0 -> EW, width
                                 region_size_in_degrees[1] * latitude_in_m]  # 1 -> NS, height
        region_ratio =  region_size_in_meters[1] / float(region_size_in_meters[0])
   
        # width/height (in 2D) of 3D model of ONE TILE to be printed, in mm
        print3D_width_per_tile = tilewidth # EW
        print3D_height_per_tile = (print3D_width_per_tile * num_tiles[0] * region_ratio) / float(num_tiles[1]) # NS

        # width/height of full 3D model (all tiles together)
        print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0] # width => EW
        print3D_height_total_mm = print3D_width_total_mm * region_ratio   # height => NS

        if print3D_resolution > 0:
            
            # Get a cell size for EE
            
            # number of samples needed to cover ALL tiles
            num_samples_lat = print3D_width_total_mm  / float(print3D_resolution) # width
            num_samples_lon = print3D_height_total_mm / float(print3D_resolution) # height
            #pr(print3D_resolution,"mm print resolution => requested num samples (width x height):", num_samples_lat, "x",  num_samples_lon)
    
            # get cell size (in meters) for request from ee # both should be the same
            cell_size_meters_lat = region_size_in_meters[0] / num_samples_lat # width
            cell_size_meters_lon = region_size_in_meters[1] / num_samples_lon # height
    
            
            # Note: the resolution of the ee raster does not quite match the requested raster at this cell size;
            # it's not bad, req: 1200 x 2235.85 i.e. 19.48 m cells => 1286 x 2282 which is good enough for me.
            # This also affects the total tile width in mm, which I'll also adjust later
            cell_size_m = cell_size_meters_lat # will later be used to calc the scale of the model
            print("requesting", cell_size_m, "m resolution from EarthEngine")
        else:
            # print3D_resolution  <= 0 means: get whatever GEEs default is. 
            cell_size_m = 0  

        #
        # Get a download URL for DEM from Earth Engine
        #

        # CH: re-init should not be needed, but without it we seem to get a 404 from GEE once in a while ...
        # Try both ways of authenticating
        try:
            pr("******* BEFORE init")
            ee.Initialize() # uses .config/earthengine/credentials
            pr("******* AFTER  init")
        except Exception as e:
            pr("EE init() error (with .config/earthengine/credentials), trying .pem file ...", e)
     
            try:
                # try authenticating with a .pem file
                from common import config  # sets location of .pem file, config.py must be in this folder
                from oauth2client.service_account import ServiceAccountCredentials
                from ee import oauth
                credentials = ServiceAccountCredentials.from_p12_keyfile(config.EE_ACCOUNT, config.EE_PRIVATE_KEY_FILE, scopes=oauth.SCOPES)
                ee.Initialize(credentials, config.EE_URL)
            except Exception as e:
                pr("EE init() error (with config.py and .pem file)", e)       

        # TODO: this can probably go, the exception was prb always caused by ee not staying inited
        got_eeImage = False
        while not got_eeImage:
            try:
                image1 = ee.Image(DEM_name)
            except Exception as e:
                print(e)
                logger.error("ee.Image(DEM_name) failed: " + str(e))
                time.sleep(random.randint(1,10))
            else:
                break

        info = image1.getInfo() # this can go wrong for some sources, but we don't really need the info as long as we get the actual data
        
        pr("Earth Engine raster:", info["id"])
        try:# 
            pr(" " + info["properties"]["title"])  
        except Exception as e:
            #print e
            pass
        try: 
            pr(" " + info["properties"]["link"])
        except Exception as e:
            #print e
            pass    

        # https://developers.google.com/earth-engine/resample
        # projections (as will be done in getDownload()) defaults to nearest neighbor, which introduces artifacts,
        # so I set the resampling mode here to bilinear or bicubic
        #image1 = image1.resample("bicubic") # only very small differences to bilinear
        image1 = image1.resample("bilinear")
    
        
        region_extent = [trlon, bllat, bllon, trlat] # Min, yMin, xMax, yMax
        
        
        # ee.Geometry
        reg_poly = ee.Geometry.Polygon([[-120, 35], [-119, 35], [-119, 34], [-120, 34]])
        reg_rect = ee.Geometry.Rectangle([[-120, 35], [-119, 34]]) # opposite corners
        reg_poly_str = reg_poly.toGeoJSONString()
        reg_rect_str = reg_rect.toGeoJSONString()
        

        # make the request dict
        request_dict = {
            #'scale': 10, # cell size
            'scale': cell_size_m, # cell size in meters
            #'region': '[[-120, 35], [-119, 35], [-119, 34], [-120, 34]]', <- not working anymore?
            #'region': str(region_extent),
            'region': reg_rect_str ,
            'crs': 'EPSG:4326',
            #'crs': epsg_str, # projection
            #'format': 'png',
            'format': 'tiff'
            #'format': 'jpeg'
        }
        
        
        # if cellsize is <= 0, just get whatever GEE's default cellsize is
        if cell_size_m <= 0: del request_dict["scale"]
        
        # don't apply UTM projection, can only work for Geotiff export
        if unprojected == True: del request_dict["crs"]
        
        pr("***************************************")
        pr("request dict is: ", request_dict)
        pr("***************************************")
        request = image1.getDownloadUrl(request_dict)
        pr("request URL is: ", request)
        pr("***************************************")


        # This should retry until the request was successfull
        web_sock = None
        to = 2
        while web_sock == None:
            #
            # download zipfile from url
            #
            try:
                web_sock = urllib.request.urlopen(request, timeout=20) # 20 sec timeout
            except socket.timeout as e:
                raise logger.error("Timeout error %r" % e)
            except urllib.error.HTTPError as e:
                logger.error('HTTPError = ' + str(e.code))
                if e.code == 429:  # 429: quota reached
                    time.sleep(random.randint(1,10)) # wait for a couple of secs
            except urllib.error.URLError as e:
                logger.error('URLError = ' + str(e.reason))
            except http.client.HTTPException as e:
                logger.error('HTTPException')
            except Exception:
                import traceback
                logger.error('generic exception: ' + traceback.format_exc())

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

        # use GDAL to get cell size and undef value of geotiff
        dem = gdal.Open(GEE_dem_filename) 
        band = dem.GetRasterBand(1)
        gdal_undef_val = band.GetNoDataValue()  
        gt = dem.GetGeoTransform()
        GEE_cell_size_m =  (gt[1], gt[5])
        
        # if we requested the true resolution of the source, use the cellsize of the gdal/GEE geotiff
        if cell_size_m <= 0: 
            cell_size_m = gt[1]   
        
        pr(" geotiff size:", len(str_data) / 1048576.0, "Mb")
        pr(" cell size", cell_size_m, "m, upper left corner (x/y): ", gt[0], gt[3])  
        
        if fileformat == "GeoTiff": # for Geotiff output, we don't need to make a numpy array, etc, just close the GDAL dem so we can move it into the zip later
            dem = None #  Python GDAL's way of closing/freeing the raster 
            del band    
            
        else:  # mesh file export
            assert abs(gt[1]) == abs(gt[5]), "Error: raster cells are not square!" # abs() b/c one can be just the negative of the other in GDAL's geotranform matrix
            
            # typically, GEE serves does not use proper undefined values in the geotiffs it serves, but just in case ...
            if gdal_undef_val != None: 
                logger.debug("undefined GDAL value used by GEE geotiff: ", +star(gdal_undef_val))  
     
          
            # delete zip file and buffer from memory
            GEEZippedGeotiff.close()
            del zipdir, str_data
     
            # cast to 32 bit floats as STL can only write in 32 bit precision anyway
            npim = band.ReadAsArray().astype(numpy.float32) 
            #print npim, npim.shape, npim.dtype, numpy.nanmin(npim), numpy.nanmax(npim)
            
            min_elev = numpy.nanmin(npim)
            
            # clip values?
            if ignore_leq != None:
                npim = numpy.where(npim <= ignore_leq, numpy.nan, npim)
                pr("ignoring elevations <= ", ignore_leq, " (were set to NaN)")             
            
            # sanity check: for all onshore-only sources, set very large values 
            # (which must actually mean NoData) as NaN so they get omitted.
            # Note: the GeoTiffs from GEE don't seem to have any notion of undefined either as an offcial value
            # or as the very large number thing we check against here ... so this check is prb not needed
            if DEM_name == """USGS/NED""" or DEM_name == """USGS/SRTMGL1_003""" or DEM_name == """USGS/GMTED2010""":
                if min_elev < -16384:                                           
                    npim = numpy.where(npim <  -16384, numpy.nan, npim)  
                    pr("omitting cells with elevation < -16384")
                if numpy.nanmax(npim) > 16384:                                           
                    npim = numpy.where(npim >  16384, numpy.nan, npim)  
                    pr("omitting cells with elevation > 16384")               

            pr("full (untiled) raster (height,width): ", npim.shape, npim.dtype)
            #print "elev. min/max:", min_elev, numpy.nanmax(npim)
            
            #
            # based on the full raster's shape and given the model width, recalc the model height
            #
            region_ratio =  npim.shape[0] / float(npim.shape[1])
       
            # width/height (in 2D) of 3D model of ONE TILE to be printed, in mm
            print3D_width_per_tile = tilewidth # EW
            print3D_height_per_tile = (print3D_width_per_tile * num_tiles[0] * region_ratio) / float(num_tiles[1]) # NS
    
            # width/height of full 3D model (all tiles together)
            print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0] # width => EW
            print3D_height_total_mm = print3D_width_total_mm * region_ratio   # height => NS            

            #
            # (re) calculate print res needed to make that width/height from the given raster
            #
            adjusted_print3D_resolution = print3D_width_total_mm / float(npim.shape[1])
                        
            
            if printres > 0: # did NOT use source resolution
                pr("cell size:", cell_size_m, "m ")
                pr("adjusted print res from the requested", print3D_resolution, "mm to", adjusted_print3D_resolution, "mm to ensure correct model dimensions")
                print3D_resolution = adjusted_print3D_resolution   
            else:
                print3D_resolution = adjusted_print3D_resolution 
                pr("cell size:", cell_size_m, "m (<- native source resolution)")
                pr("print res for native source resolution is", print3D_resolution, "mm")

            pr("total model size in mm:", print3D_width_total_mm, "x", print3D_height_total_mm)          
    # end of getting DEM data via GEE


    #
    # B) DEM data comes from a local raster file (geotiff, etc.)
    #
    else:

        filename = os.path.basename(importedDEM)
        pr("Log for creating", num_tiles[0], "x", num_tiles[1], "3D model tile(s) from", filename, "\n")


        pr("started:", datetime.datetime.now().time().isoformat())
        dem = gdal.Open(importedDEM)
        band = dem.GetRasterBand(1)
        npim = band.ReadAsArray().astype(numpy.float32)  
        
        # get the GDAL cell size in x (width), assumes cells are square!
        tf = dem.GetGeoTransform()  # In a north up image, padfTransform[1] is the pixel width, and padfTransform[5] is the pixel height. The upper left corner of the upper left pixel is at position (padfTransform[0],padfTransform[3]).
        pw,ph = abs(tf[1]), abs(tf[5])
        if pw != ph: 
            logger.warning("Warning: raster cells are not square (" + str(pw) + "x" + str(ph) + ") , using" + str(pw))
        cell_size_m = pw   
        pr("source raster upper left corner (x/y): ",tf[0], tf[3])
        pr("source raster cells size", cell_size_m, "m ", npim.shape)


        # I use PROJCS[ to get a projection name, e.g. PROJCS["NAD_1983_UTM_Zone_10N",GEOGCS[....
        # I'm grabbing the text between the first and second double-quote.
        utm_zone_str = dem.GetProjection()
        i = utm_zone_str.find('"')+1
        utm_zone_str = utm_zone_str[i:]
        i = utm_zone_str.find('"')
        utm_zone_str = utm_zone_str[:i]
        epsg_str = "N/A"

        pr( "projection:", utm_zone_str)
        
        
        pr( "z-scale:", zscale)
        pr( "basethickness:", basethick)
        pr( "fileformat:", fileformat)
        pr( "tile_centered:", tile_centered)
        pr( "no_bottom:", no_bottom)
        pr( "no_normals:", no_normals)
        pr( "ignore_leq:", ignore_leq)
        
        #
        # set Cells with GDAL undef to numpy NaN
        #
        
        gdal_undef_val = band.GetNoDataValue()
        pr("undefined GDAL value:", gdal_undef_val)
             
        # Instead of == use numpy.isclose to flag undef cells as True
        if gdal_undef_val != None:  # None means the raster is not a geotiff
            undef_cells = numpy.isclose(npim, gdal_undef_val) # bool
            npim = numpy.where(undef_cells, numpy.nan, npim)                   

        # clip values?
        if ignore_leq != None:
            npim = numpy.where(npim <= ignore_leq, numpy.nan, npim)
            pr("ignoring elevations <= ", ignore_leq, " (were set to NaN)")

       
        # tile height
        whratio = npim.shape[0] / float(npim.shape[1])
        tileheight = tilewidth  * whratio
        pr("tile_width:", tilewidth)
        pr("tile_height:", tileheight)
        print3D_width_per_tile = tilewidth
        print3D_height_per_tile = tileheight   
        print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0]
        real_world_total_width_m = npim.shape[1] * cell_size_m
        pr("source raster width", real_world_total_width_m, "m,", "cell size:", cell_size_m, "m, elev. min/max is", numpy.nanmin(npim), numpy.nanmax(npim), "m")

        # What would be the 3D print resolution using the original/unresampled source resolution?
        source_print3D_resolution =  (tilewidth*ntilesx) / float(npim.shape[1])
        pr("source raster 3D print resolution would be", source_print3D_resolution, "mm")

        # Resample raster to get requested printres?
        if printres <= 0: # use of source resolution was requested          
                pr("no resampling, using source resolution of ", source_print3D_resolution, "mm for a total model width of", print3D_width_total_mm, "mm")
                if source_print3D_resolution < 0.2 and fileformat != "GeoTiff":
                    pr("Warning: this print resolution of", source_print3D_resolution, "mm is pretty small for a typical nozzle size of 0.4 mm. You might want to use a printres that's just a bit smaller than your nozzle size ...")
                print3D_resolution = source_print3D_resolution
                
        else: # yes, resample 
            scale_factor = print3D_resolution / float(source_print3D_resolution)
            if scale_factor < 1.0: 
                pr("Warning: will re-sample to a resolution finer than the original source raster. Consider instead a value for printres >", source_print3D_resolution)
                
            # re-sample DEM using PIL
            pr("re-sampling", filename, ":\n ", npim.shape[::-1], source_print3D_resolution, "mm ", cell_size_m, "m ", numpy.nanmin(npim), "-", numpy.nanmax(npim), "m to")
            npim =  resampleDEM(npim, scale_factor)
            
            
            #
            # based on the full raster's shape and given the model width, recalc the model height
            # and the adjusted printres that will give that width from the resampled raster
            #
            region_ratio =  npim.shape[0] / float(npim.shape[1])
            print3D_width_per_tile = tilewidth # EW
            print3D_height_per_tile = (print3D_width_per_tile * num_tiles[0] * region_ratio) / float(num_tiles[1]) # NS
            print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0] # width => EW
            print3D_height_total_mm = print3D_width_total_mm * region_ratio   # height => NS            
            adjusted_print3D_resolution = print3D_width_total_mm / float(npim.shape[1])
            
            cell_size_m *= scale_factor
            pr(" ",npim.shape[::-1], adjusted_print3D_resolution, "mm ", cell_size_m, "m ", numpy.nanmin(npim), "-", numpy.nanmax(npim), "m")
                        
            if adjusted_print3D_resolution != print3D_resolution:
                pr("after resampling, requested print res was adjusted from", print3D_resolution, "to", adjusted_print3D_resolution, "to ensure correct model dimensions")
                print3D_resolution = adjusted_print3D_resolution
            else: 
                pr("print res is", print3D_resolution, "mm")
             
        DEM_title = filename[:filename.rfind('.')]
        # end local raster file




    total_size = 0 # size of stl/objs/geotiff file(s) in byes 
    full_zip_file_name =  temp_folder + os.sep + zip_file_name + ".zip"     
    #print >> sys.stderr, "zip is in", os.path.abspath(full_zip_file_name)
    zip_file = ZipFile(full_zip_file_name, "w", allowZip64=True) # create empty zipfile   
    
    #
    # Create and store geometry (triangles)
    #

    if fileformat != "GeoTiff":    # Mesh export
    
        if importedDEM == None:
            DEM_name = DEM_name.replace("/","-") # replace / with - to be safe
        else:
            DEM_name = filename

        # Adjust raster to nice multiples of tiles. If needed, crop raster from right and bottom
        remx = npim.shape[1] % num_tiles[0]
        remy = npim.shape[0] % num_tiles[1]
        if remx > 0 or  remy > 0:
            pr("Cropping for nice fit of %d (width) x %d (height) tiles, removing: %d columns, %d rows" % (num_tiles[0], num_tiles[1], remx, remy))
            old_shape = npim.shape
            npim = npim[0:npim.shape[0]-remy, 0:npim.shape[1]-remx]
            pr(" cropped", old_shape[::-1], "to", npim.shape[::-1]   )     
            
            # adjust tile width and height to reflect the smaller, cropped raster
            ratio = old_shape[0] / float(npim.shape[0]), old_shape[1] / float(npim.shape[1])
            pr(" cropping changed physical size from", print3D_width_per_tile, "mm x", print3D_height_per_tile, "mm") 
            print3D_width_per_tile = print3D_width_per_tile / ratio[1]
            print3D_height_per_tile = print3D_height_per_tile / ratio[0]
            pr(" to", print3D_width_per_tile, "mm x", print3D_height_per_tile, "mm")
            print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0]            
            
        # get horizontal map scale (1:x) so we know how to scale the elevation later
        print3D_scale_number =  (npim.shape[1] * cell_size_m) / (print3D_width_total_mm / 1000.0) # map scale ratio (mm -> m)
        
        pr("map scale is 1 :", print3D_scale_number) # EW scale
        #print (npim.shape[0] * cell_size_m) / (print3D_height_total_mm / 1000.0) # NS scale
         
        # min/max elev (all tiles)
        print(("elev min/max : %.2f to %.2f" % (numpy.nanmin(npim), numpy.nanmax(npim)))) # use nanmin() so we can use (NaN) undefs
    
        # apply z-scaling
        if zscale != 1.0:
            npim *= zscale
            #print "elev min/max after x%.2f z-scaling: %.2f to %.2f" % (zscale, numpy.nanmin(npim), numpy.nanmax(npim))
    
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
        tile_info = {
            "DEMname": DEM_name, # name of raster requested from earth eng.
            "crs" : epsg_str, # EPSG name for UTM zone
            "UTMzone" : utm_zone_str, # UTM zone eg  UTM13N
            "scale"  : print3D_scale_number, # horizontal scale number, defines the size of the model (= 3D map): eg 1000 means 1m in model = 1000m in reality
            "pixel_mm" : print3D_resolution, # lateral (x/y) size of a 3D printed "pixel" in mm
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
            "no_bottom": no_bottom,
            "bottom_image": bottom_image,
            "ntilesy": ntilesy, # number of tiles in y
            "only": only, # if nont None, process only this tile e.g. [1,2]
            "no_normals": no_normals,
        }        
        
        #
        # Make tiles (subsets) of the full raster and generate 3D grid model
        #
    
        # num_tiles[0], num_tiles[1]: x, y !
        cells_per_tile_x = int(npim.shape[1] / num_tiles[0]) # tile size in pixels
        cells_per_tile_y = int(npim.shape[0] / num_tiles[1])
        pr("Cells per tile (x/y)", cells_per_tile_x, "x", cells_per_tile_y)
    
    
        # pad full raster by one at the fringes
        #print npim, npim.shape
        npim = numpy.pad(npim, (1,1), 'edge') # will duplicate edges, including nan
        #print npim.astype(int)
    
        # store size of full raster
        tile_info["full_raster_height"], tile_info["full_raster_width"]  = npim.shape
        #print tile_info
        
        # Warn that we're only processing one tile
        process_only = tile_info["only"]      
        if process_only != None:
            pr("Only processing tile:", process_only)
            CPU_cores_to_use = 1 # set to SP
            
        # within the padded full raster, grab tiles - but each with a 1 cell fringe!
        tile_list = [] # list of tiles to be processed via multiprocessing.map()
        for tx in range(num_tiles[0]):
            for ty in range(num_tiles[1]):
                #print tx,ty
    
                # extract current tile from full raster
                start_x = tx * cells_per_tile_x
                end_x = start_x + cells_per_tile_x + 1 + 1
                start_y = ty * cells_per_tile_y
                end_y = start_y + cells_per_tile_y + 1 + 1
    
                tile_elev_raster = npim[start_y:end_y, start_x:end_x] #  [y,x]
                #print tile_elev_raster.astype(int)
                
                # Jan 2019: for some reason, changing one tile's raster in process_tile also changes parts of another
                # tile's raster (???) So I'm making the elev arrays r/o here and make a copy in process_raster
                tile_elev_raster.flags.writeable = False       
    
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
                tile = (my_tile_info, tile_elev_raster)   # leave it to process_tile() to unwrap the info and data parts
                
                # if we only process one tile ...
                if process_only == None: # no only was given
                    tile_list.append(tile)
                else:
                    if process_only[0] == tile_info['tile_no_x'] and process_only[1] == tile_info['tile_no_y']:
                        tile_list.append(tile) # got the only tile
                    else:
                        print("process only is:", process_only, ", skipping tile", tile_info['tile_no_x'], tile_info['tile_no_y']) 
        
        if tile_info["full_raster_height"] * tile_info["full_raster_width"]  > max_cells_for_memory_only:
            logger.debug("tempfile or memory? number of pixels:" + str(tile_info["full_raster_height"] * tile_info["full_raster_width"]) + ">" + str(max_cells_for_memory_only) + " => using temp file")
    

                   
    
        # single processing: just work on the list sequentially, don't use multi-core processing
        # us if only one tile or one CPU or CPU_cores_to_use is still at default None 
        # processed list will contain tuple(s): [0] is always the tile info dict, if its 
        # "temp_file" is None, we got a buffer, but if "temp_file" is a string, we got a file of that name
        # [1] can either be the buffer or again the name of the temp file we just wrote (which is redundant, i know ...)  
        if num_tiles[0]*num_tiles[1] == 1 or CPU_cores_to_use == 1 or CPU_cores_to_use == None:  
            pr("using single-core only")
            processed_list = []
            # Convert each tile into a list: [0]: updated tile info, [1]: grid object
            for i,t in enumerate(tile_list):
                #print "processing", i, numpy.round(t[1], 1), t[0]
                pt = process_tile(t)
                processed_list.append(pt) # append to list of processed tiles
        
        # use multi-core processing 
        else:  
            
            #if CPU_cores_to_use is 0(!) us all cores, otherwise use that number
            if CPU_cores_to_use == 0: 
                num_cores = None
            else: 
                num_cores = CPU_cores_to_use
            # TODO: Using 0 here that needs to become None is confusing, but too esoteric to clean up ..
            # Better: make default 1, else use MP with None (meaning all)
            
            pr("using multi-core (no logging info available while processing)  ...")
            import multiprocessing
            #import dill as pickle
            pool = multiprocessing.Pool(processes=num_cores, maxtasksperchild=1) # processes=None means use all available cores
    
            # Convert each tile in tile_list and return as list of lists: [0]: updated tile info, [1]: grid object
            try:
                processed_list = pool.map(process_tile, tile_list)
            except Exception as e:
                pr(e)   
            else:
                pool.close()
                pool.terminate()                
                
            pr("... multi-core processing done, logging resumed")

    
        
        # the tile width/height was written into tileinfo during processing
        _ = "\n%d x %d tiles, tile size %.2f x %.2f mm\n" % ( num_tiles[0], num_tiles[1], tile_info["tile_width"], tile_info["tile_height"])
        pr(_)
    
        # delete tile list, as the elevation arrays are no longer needed
        del tile_list

        # concat all processed tiles into a zip file
        #print "start of putting tiles into zip file")
        for p in processed_list:
                tile_info = p[0] # per-tile info
                tn = DEM_title+"_tile_%d_%d" % (tile_info["tile_no_x"],tile_info["tile_no_y"]) + "." + fileformat[:3] # name of file inside zip
                buf= p[1] # either a string or a file object
                
    
                if tile_info.get("temp_file") != None: # if buf is a file object
                    fname = tile_info["temp_file"]
                    zip_file.write( fname , tn) # write temp file into zip
                    try:
                        os.remove(fname) # on windows remove closed file manually
                    except Exception as e:
                        logger.error("Error removing" + str(fname) + " " + str(e))
                    else:
                        #print >> sys.stderr, "Removed temp file", fname
                        pass
                else:
                    zip_file.writestr(tn, buf) # buf is a string
                    del buf
    
                total_size += tile_info["file_size"]
                logger.debug("adding tile %d %d, total size is %d" % (tile_info["tile_no_x"],tile_info["tile_no_y"], total_size))
                
                # print size and elev range
                pr("tile", tile_info["tile_no_x"], tile_info["tile_no_y"], ": height: ", tile_info["min_elev"], "-", tile_info["max_elev"], "mm",
                   ", file size:", round(tile_info["file_size"]), "Mb")
                
        pr("\ntotal size for all tiles:", round(total_size), "Mb")


        
        # delete all the GDAL geotiff stuff
        del npim
        del band 
        dem = None #  Python GDAL's way of closing/freeing the raster, needed to be able to delete the inital geotiff  
         
    # end of: if fileformat != "GeoTiff"
    
    print("zip finished:", datetime.datetime.now().time().isoformat())

    # add (full) geotiff we got from EE to zip 
    if importedDEM == None:
        total_size += os.path.getsize(GEE_dem_filename) / 1048576.0
        zip_file.write(GEE_dem_filename, DEM_title + ".tif")
        pr("added full geotiff as " + DEM_title + ".tif")
        

    pr("\nprocessing finished: " + datetime.datetime.now().time().isoformat())
    
    # add logfile to zip
    log_file_handler.flush()
    log_file_handler.close()    
    logger.removeHandler(log_file_handler)
    zip_file.write(log_file_name, "logfile.txt")
    zip_file.close() # flushes zip file
    
    # remove geotiff d/led from EE
    if importedDEM == None:
        try:
            os.remove(GEE_dem_filename) 
        except Exception as e:   
             print("Error removing " + str(GEE_dem_filename) + " " + str(e), file=sys.stderr)
             
             
    # remove logfile
    try:    
        os.remove(log_file_name) 
    except Exception as e:   
         print("Error removing logfile " + str(log_file_name) + " " + str(e), file=sys.stderr)     
             
    # return total  size in Mega bytes and location of zip file
    return total_size, full_zip_file_name
#
# MAIN
#
if __name__ == "__main__":

    # Grand Canyon: -109.947664, 37.173425  -> -109.905481, 37.151472
    #r = get_zipped_tiles("USGS/NED", 44.7220, -108.2886, 44.47764, -107.9453, ntilesx=1, ntilesy=1,printres=1.0,
    #                     tilewidth=120, basethick=2, zscale=1.0)

    # test for importing dem raster files
    #fname = "Oso_after_5m_cropped.tif"
    fname = "pyramid_wide.tif" # pyramid with height values 0-255
    r = get_zipped_tiles(importedDEM=fname,  
                         ntilesx=1, ntilesy=1,
                         printres=0.5,
                         tilewidth=100, 
                         basethick=0.5, 
                         zscale=0.5,
                         CPU_cores_to_use=1,
                         tile_centered=False,
                         fileformat="STLb",
                         max_cells_for_memory_only=0,
                         zip_file_name="pyramid")
    zip_string = r[1] # r[1] is a zip folder as string, r[0] is the size of the file in Mb
    with open(fname+".zip", "w+") as f:
        f.write(zip_string)
    print("done")







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
