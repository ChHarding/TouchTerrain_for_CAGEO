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
import numpy
from touchterrain.common.config import EE_ACCOUNT,EE_CREDS,EE_PROJECT

DEV_MODE = False
#DEV_MODE = True  # will use modules in local touchterrain folder instead of installed ones

if DEV_MODE:
    oldsp = sys.path
    sys.path = ["."] + sys.path # force imports form local touchterain folder

import touchterrain.common
from touchterrain.common.grid_tesselate import grid      # my own grid class, creates a mesh from DEM raster
from touchterrain.common.Coordinate_system_conv import * # arc to meters conversion
from touchterrain.common.utils import save_tile_as_image, clean_up_diags, fillHoles, add_to_stl_list, k3d_render_to_html, dilate_array, plot_DEM_histogram
if DEV_MODE:
    sys.path = oldsp # back to old sys.path

import kml2geojson # https://rawgit.com/araichev/kml2geojson/master/docs/_build/singlehtml/index.html
import defusedxml.minidom as md

from PIL import Image

# just needed for debugging numpy arrays
numpy.set_printoptions(linewidth=300)
numpy.set_printoptions(precision=1)


# for reading/writing geotiffs
# Later versions of gdal may be bundled into osgeo so check there as well.
try:
    import gdal
except ImportError as err:
    from osgeo import gdal

import osgeo.osr as osr  # projection stuff

import time
import random
import os.path
import httplib2
from glob import glob

# get root logger, will later be redirected into a logfile
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)



# CH test Aug 18: do EE init here only
# this seems to prevent the file_cache is unavailable when using oauth2client >= 4.0.0 or google-auth
# crap from happening. It assumes that any "main" file imports TouchTerrainEarthEngine anyway.
# But, as this could also be run in a standalone scenario where EE should not be involved,
# the failed to EE init messages are just warnings
try:
    import ee
    # uses .config/earthengine/credentials, since Nov. 2024 this must be a service account json file not a p12 file!
    # Set the path to your JSON key file
    # Authenticate using the service account
    credentials = ee.ServiceAccountCredentials(EE_ACCOUNT, EE_CREDS)
    ee.Initialize(credentials, project=EE_PROJECT)
except Exception as e:
    logging.warning(f"EE init() error (with {EE_CREDS}) {e} (This is OK if you don't use earthengine anyway!)")
else:
    logging.info(f"EE init() worked with {EE_CREDS}")

# utility to print to stdout and to logger.info
def pr(*arglist):
    s = ""
    for a in arglist:
        s = s + str(a) + " "
    print(s)
    logger.info(s)


# Use zig-zag magic?
use_zigzag_magic = False

#  List of DEM sources  Earth engine offers and their nominalresolutions (only used for guessing the size of a geotiff ...)
DEM_sources = ["USGS/3DEP/10m",
               "USGS/GMTED2010",
               "NOAA/NGDC/ETOPO1",
               "USGS/SRTMGL1_003",
               "JAXA/ALOS/AW3D30/V2_2",
               "NRCan/CDEM",
               "AU/GA/AUSTRALIA_5M_DEM",
               "USGS/GTOPO30",
               "CPOM/CryoSat2/ANTARCTICA_DEM",
               "MERIT/DEM/v1_0_3"
              ]


# Define default parameters
# Print settings that can be used to initialize the actual args
initial_args = {
    "DEM_name": 'USGS/3DEP/10m',# DEM_name:    name of DEM source used in Google Earth Engine
    "bllat": 39.32205105794382,   # bottom left corner lat
    "bllon": -120.37497608519418, # bottom left corner long
    "trlat": 39.45763749030933,   # top right corner lat
    "trlon": -120.2002248034559, # top right corner long
    "importedDEM": None, # if not None, the raster file to use as DEM instead of using GEE (null in JSON)
    "printres": 0.4,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
    "ntilesx": 1,      # number of tiles in x and y
    "ntilesy": 1,
    "tilewidth": 120, # width of each tile in mm (<- !!!!!), tile height is calculated
    "basethick": 0.6, # thickness (in mm) of printed base
    "zscale": 2.0,      # elevation (vertical) scaling
    "fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
    "tile_centered": False, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
    "zip_file_name": "terrain",   # base name of zipfile, .zip will be added
    #"CPU_cores_to_use" : 0,  # 0 means all cores, None (null in JSON!) => don't use multiprocessing
    "CPU_cores_to_use" : None,  # Special case for setting to SP that cannot be overwritten later
    "max_cells_for_memory_only" : 5000 * 5000, # if raster has more cells, use temp_files instead of memory (slower, but can be huge)

    # these are the args that could be given "manually" via the web UI
    "no_bottom": False, # omit bottom triangles?
    #"rot_degs": 0, # rotate by degrees ccw  # CH disabled for now
    "bottom_image": None,  # 1 band 8-bit greyscale image used for bottom relief
    "ignore_leq": None, # set values <= this to NaN, so they are ignored
    "lower_leq": None,  # e.g. [0.0, 2.0] values <= 0.0 will be lowered by 2mm in the final model
    "unprojected": False, # project to UTM? only useful when using GEE for DEM rasters
    "only": None,# list of tile index [x,y] with is the only tile to be processed. None means process all tiles (index is 1 based)
    "importedGPX": [], # list of gpx path file(s) to be use
    "smooth_borders": True, # smooth borders  by removing a border triangle?
    "offset_masks_lower": None, # [[filename, offset], [filename2, offset2], ...] offset masks to apply to map
    "fill_holes": None, # [rounds, threshold] hole filling filter iterations and threshold to fill a hole
    "poly_file": None, # local kml file for mask
    "min_elev": None, # min elev to use, None means set by min of all tiles
    "tilewidth_scale": None, # set x/y scale, with None, scale is set automatically by the selected area (region)
    "clean_diags":False, # clean of corner diagonal 1 x 1 islands?
    "bottom_elevation":None,
    "dirty_triangles:":False, # allow degenerate triangles for water
}


def make_bottom_raster_from_image(image_file_name, shape):
    """Make a bottom image (numpy array) to be used in the stl model

        in: image_file_name. Must be 1 band/greyscale image,
            will be scaled to fit the tile with at least a 5% fringe
            shape: width [0] and height [1] of TOP ! raster
        out: numpy raster with 0 - 255 (with 0 = buildplate, 1 = max relief) or None on error"""
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
    canvas = Image.new("L", shape[::-1], color=255)

    # find upper left corner in canvas so that bg is centered
    bg_w, bg_h = scaled_size
    w_diff = shape[1] - bg_w
    h_diff = shape[0] - bg_h
    offset = int(w_diff / 2), int(h_diff / 2)

    canvas.paste(bg, offset)
    #canvas.save("canvas.png") #DEBUG

    # convert to 0 (bottom = buildplate) to 1 (top)
    bottom_raster = numpy.asarray(canvas).astype(numpy.float64)
    bottom_raster /= 255.0 # normalize
    bottom_raster *= -1
    bottom_raster += 1
    return bottom_raster



# utility function to unwrap a tile tuple into its info and numpy array parts
# if multicore processing is used, this is called via multiprocessing.map()
# tile_info["temp_file"] contains the file name to open and write into (creating a file object)
# but if it's None, a buffer is made instead.
# the tile info dict (with the file/buffer size) and the buffer (or the file's name) are returns as a tuple
#@profile
def process_tile(tile_tuple):
    tile_info = tile_tuple[0] # has info for this individual tile
    tile_elev_raster = tile_tuple[1] # the actual (top) raster
    tile_bottom_raster = tile_tuple[2] # the actual (bottom) raster (or None)
    tile_elev_orig_raster = tile_tuple[3] # the original (top) raster (or None)

    print("processing tile:", tile_info['tile_no_x'], tile_info['tile_no_y'])
    #print numpy.round(tile_elev_raster,1)

    # create a bottom relief raster (values 0.0 - 1.0)
    if tile_info["bottom_image"] != None and tile_info["no_bottom"] != None:
        logger.debug("using " + tile_info["bottom_image"] + " as relief on bottom")
        bottom_raster = make_bottom_raster_from_image(tile_info["bottom_image"], tile_elev_raster.shape)
        #print "min/max:", numpy.nanmin(bottom_raster), numpy.nanmax(bottom_raster)
        bottom_raster *= (tile_info["base_thickness_mm"] * 0.8) # max relief is 80% of base thickness to still have a bit of "roof"
        print("bottom image (in meters!) min/max:", numpy.nanmin(bottom_raster), numpy.nanmax(bottom_raster)) # range of bottom raster
    elif tile_bottom_raster is not None:
        bottom_raster = tile_bottom_raster # bottom elevation(!) raster
    else:
        bottom_raster = None # None means bottom is flat

    '''
    # DEBUG: make some simple rasters  (CH: hack)
    nn = numpy.NaN
    tile_elev_raster =  numpy.array([
                         [ 10, 13,],
                         [ 10, 13,],
                         [ 10, 13,],
                         [ 10, 13,],
                   ])

    tile_elev_raster =  numpy.array([
                         [ nn, 13,],
                         [ 10, nn,],
                         [ nn, 13,],
                         [ nn, 13,],
                   ])



    tile_elev_raster =   numpy.pad(tile_elev_raster, (1,1), 'edge')

    bottom_raster =  numpy.array([
                         [ nn, 13,],
                         [ 10, nn,],
                         [ nn, 13,],
                         [ nn, 13,],
                   ])

    bottom_raster =  numpy.array([
                         [ 10, 13,],
                         [ 10, 13,],
                         [ 10, 13,],
                         [ 10, 13,],
                   ])
    bottom_raster =   numpy.pad(bottom_raster, (1,1), 'edge')
    tile_info["bottom_as_aux"] = True
    '''

    '''
    tile_elev_raster =  numpy.array([
                         [ 1, 5, 10, 50, 20, 10, 1],
                         [ 1, 10, 10, 50, 20, 10, 2],
                         [ 1, 11, 15, 20, 30, 10, 5],
                         [ 1, 23, 30, 40, 20, 10, 2 ],
                         [ 1, 20, 10, 10, 20, 10 , 1 ],

                   ])
    tile_elev_raster =   numpy.pad(tile_elev_raster, (1,1), 'edge')

    bottom_raster = numpy.array([
                         [ 1, nn, nn, 50, 20, 10, 1],
                         [ 1, nn, nn, nn, nn, 10, 2],
                         [ 1, nn, nn, nn, nn, nn, 5],
                         [ 1, 23, nn, nn, nn, 10, 2 ],
                         [ 1, 20, 10, nn, 20, 10 , 1 ],

                   ])
    bottom_raster =   numpy.pad(bottom_raster, (1,1), 'edge')

    tile_info["bottom_as_aux"] = True
    '''

    '''
    # bottom as top with water as mask
    nan = numpy.NaN
    tile_elev_raster = numpy.array([
                         [ 1, nan, 10, 50, 20, 10, 1],
                         [ 1, nan, nan, 50, 20, 10, 2],
                         [ 1, nan, nan, 20, 30, 10, 5],
                         [ 1, 23, 30, nan, 20, 10, 2 ],
                         [ 1, 20, 10, 10, 20, 10 , 1 ],

                   ])
    #bottom_raster = bottom_raster - 0.5
    '''
    '''
    nan = numpy.NaN
    if 1: # top only
        tile_elev_raster = numpy.array([
                         [ 1, nan, 10, 50, 20, 10, 1],
                         [ 1, nan,nan, 50, 20, 10, 2],
                         [ 1, nan, 50 ,nan, 30, 10, 5],
                         [ 1, 23, nan,nan, 20, 10, 2 ],
                         [ 1, 20, 10, 10, 20, 10 , 1 ],
                   ])
        tile_elev_raster =   numpy.pad(tile_elev_raster, (1,1), 'edge')

    else:
        tile_elev_raster = numpy.array([
                         [ 1, 5,  10, 50, 20, 10, 1],
                         [ 1, 5,  20, 50, 20, 10, 2],
                         [ 1, 10, 15, 20, 30, 10, 5],
                         [ 1, 23, 30, 25, 20, 10, 2],
                         [ 1, 20, 10, 10, 20, 10, 1],

                   ])
        tile_elev_raster = numpy.pad(tile_elev_raster, (1,1), 'edge')

        bottom_raster =  numpy.array([
                         [ 1, nan, 10, 50, 20, 10, 1],
                         [ 1, nan,nan, 50, 20, 10, 2],
                         [ 1, nan,nan,nan, 30, 10, 5],
                         [ 1, 23, nan,nan, 20, 10, 2],
                         [ 1, 20, 10, 10, 20, 10 , 1],

                   ])
        bottom_raster = numpy.pad(bottom_raster, (1,1), 'edge')
    '''
    '''
    nan = numpy.NaN
    if 0: # top only
        tile_elev_raster = numpy.array([
                         [ 1, nan, 10, 50, 20, 10, 1],
                         [ 1, nan,nan, 50, 20, 10, 2],
                         [ 1, nan,nan,nan, 30, 10, 5],
                         [ 1, 23, nan,nan, 20, 10, 2 ],
                         [ 1, 20, 10, 10, 20, 10 , 1 ],
                   ])
        tile_elev_raster = numpy.array([
                            [nan, 200, 200, 100, nan, 100, 100, 200,200, nan],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [nan, 200, 200, 100, nan, 100, 100, 200,200, nan]
                   ])
        tile_elev_raster =   numpy.pad(tile_elev_raster, (1,1), 'edge')

    else:
        tile_elev_raster = numpy.array([
                            [200, 200, 200, 200, 200, 200, 200, 200,200, 200],
                            [200, 200, 200, 200, 200, 200, 200, 200,200, 200],
                            [200, 200, 200, 200, 200, 200, 200, 200,200, 200],
                            [200, 200, 200, 200, 200, 200, 200, 200,200, 200],
                            [200, 200, 200, 200, 200, 200, 200, 200,200, 200],
                   ])
        tile_elev_raster = numpy.pad(tile_elev_raster, (1,1), 'edge')

        bottom_raster =  numpy.array([
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200],
                            [200, 200, 200, 100, 100, 100, 100, 200,200, 200]
                   ])
        bottom_raster = numpy.pad(bottom_raster, (1,1), 'edge')
        tile_info["bottom_elevation"] = True #fake, should be filename
    '''
    
    
    # create a grid object from the raster(s), which later converted into a triangle mesh
    g = grid(tile_elev_raster, bottom_raster, tile_elev_orig_raster, tile_info)
    del tile_elev_raster
    if bottom_raster is not None: del bottom_raster
    if tile_elev_orig_raster is not None: del tile_elev_orig_raster

    #
    # convert grid object into a triangle mesh file
    #
    fileformat = tile_info["fileformat"]

    # info on buffer/temp file
    if tile_info.get("temp_file") != None:  # contains None or a file name.
        print("Writing tile into temp. file", os.path.realpath(tile_info["temp_file"]), file=sys.stderr)
        temp_fn = tile_info.get("temp_file")
    else:
        print("Writing tile into memory buffer", file=sys.stderr)
        temp_fn = None # means: use memory

    # Create triangle "file" either in a buffer or in a tempfile, of requested fileformat
    # if file: open, write and close it, b will be temp file name
    b = g.make_file_buffer()

    # When using top and bottom and multiple tiles it is possible that a water tile is empty
    # b/c no water cells cross it. In this case we return the tile_info and None so it gets ignored
    if g.num_triangles == 0:
        return tile_info, None

    # get size of file/buffer
    if temp_fn != None:
        fsize = os.stat(temp_fn).st_size / float(1024*1024)
    else:
        fsize = len(b) / float(1024*1024)


    tile_info["file_size"] = fsize
    print("tile", tile_info["tile_no_x"], tile_info["tile_no_y"], fileformat, fsize, "Mb ", file=sys.stderr) #, multiprocessing.current_process()
    return tile_info, b # return info and buffer/temp_file NAME


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

    # deleting the PIL image will also free up the read-only numpy array
    # CHECK THIS
    del img

    return a

def get_KML_poly_geometry(kml_doc):
    ''' Parses a kml document (string) via xml.dom.minidom
        finds the geometry of the first(!) polygon feature encountered otherwise returns None
        returns a tuple of
            - list of double floats: [[-112.0, 36.1], [-113.0, 36.0], [-113.5, 36.5]] or None on Error/Warning
            - Error/Warning string (or None if OK)

        Note that KML uses 3D points, so I discard z

        Setup:
        layers: just a list at root: [<layer0>, <layer1>, ... ]
        features:  {'type': 'FeatureCollection', 'features': [ ...
        single feature: {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[-
        geometry: {'type': 'Polygon', 'coordinates': [[[-106.470, 38.9711, 0.0], ... ]]
    '''

    root = md.parseString(kml_doc)
    layers = kml2geojson.build_layers(root)
    #print(root)

    # try to find a polygon
    for layer in layers:
        #print(layer)
        features = layer["features"]
        for feature in features:
            #print(feature)
            geometry = feature["geometry"]
            #print(geometry)
            geom_type = geometry["type"]
            coords = geometry["coordinates"]
            if geom_type == "Polygon":
                coords_2d = [[c3[0], c3[1]] for c3 in coords[0]] # [0] -> ignore holes, which would be in 1,2, ...
                return coords_2d, None

        # didn't find a Polygon, try again and look for a LineString
        for feature in features:
            #print(feature)
            geometry = feature["geometry"]
            #print(geometry)
            geom_type = geometry["type"]
            coords = geometry["coordinates"]
            if geom_type == "LineString":
                coords_2d = [[c3[0], c3[1]] for c3 in coords]
                return coords_2d, "Warning: no Polygon found, used a (closed) Line instead"

    # found neither polygon nor line
    return None, "Error: no Polygon or LineString found, falling back to region box"

def check_poly_with_bounds(coords, trlat, trlon, bllat, bllon):
    ''' check if all coords are inside the bounds'''
    lat = [c[1] for c in coords] # extract last and lons
    lon = [c[0] for c in coords]
    if min(lat) < bllat or max(lat) > trlat or min(lon) < bllon or max(lon) > trlon:
        return False # something was out of bounds!
    return True

def get_bounding_box(coords):
    ''' return list with trlat, trlon, bllat, bllon based on list of coords
        will grow the box by 1/100th of the box width/height'''
    lat = [c[1] for c in coords] # extract last and lons
    lon = [c[0] for c in coords]
    trlat = max(lat)
    trlon = max(lon)
    bllat = min(lat)
    bllon = min(lon)
    height = trlat - bllat
    width = trlon - bllon
    trlat += height/100
    bllat -= height/100
    trlon += width/100
    bllon -= width/100
    return trlat, trlon, bllat, bllon



def get_zipped_tiles(DEM_name=None, trlat=None, trlon=None, bllat=None, bllon=None, # all args are keywords, so I can use just **args in calls ...
                         polygon=None,
                         polyURL=None,
                         poly_file=None,
                         importedDEM=None,
                         bottom_elevation=None,
                         top_thickness=None,
                         printres=1.0, ntilesx=1, ntilesy=1, tilewidth=100,
                         basethick=2, zscale=1.0, fileformat="STLb",
                         tile_centered=False, CPU_cores_to_use=0,
                         max_cells_for_memory_only=500*500*4,
                         temp_folder = "tmp",
                         zip_file_name="terrain",
                         no_bottom=False,
                         bottom_image=None,
                         ignore_leq=None,
                         lower_leq=None,
                         unprojected=False,
                         only=None,
                         original_query_string=None,
                         no_normals=True,
                         projection=None,
                         use_geo_coords=None,
                         importedGPX=None,
                         gpxPathHeight=25,
                         gpxPixelsBetweenPoints=10,
                         gpxPathThickness=1,
                         map_img_filename=None,
                         smooth_borders=True,
                         offset_masks_lower=None,
                         fill_holes=None,
                         min_elev=None,
                         tilewidth_scale=None,
                         clean_diags=False,
                         dirty_triangles=False,
                         kd3_render=False,
                         **otherargs):
    """
    args:
    - DEM_name:  name of DEM layer used in Google Earth Engine, see DEM_sources
    - trlat, trlon: lat/lon of top right corner of bounding box
    - bllat, bllon: lat/lon of bottom left corner of bounding box
    - polygon: optional geoJSON polygon
    - importedDEM: None (means: get the DEM from GEE) or local file name with (top) DEM to be used instead
    - bottom_elevation (None): elevation raster for the bottom of the model. Must exactly match the sizes and cell resolution of importedDEM
    - top_thickness (None): thickness of the top of the model, i.e. top - thickness = bottom. Must exactly match the sizes and cell resolution of importedDEM
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
    - lower_leq: [threshold, offset] if elevation is lower than threhold, lower it by offset mm. Good for adding emphasis to coastlines. Unaffected by z_scale.
    - unprojected: don't apply UTM projection, can only work when exporting a Geotiff as the mesh export needs x/y in meters
    - only: 2-list with tile index starting at 1 (e.g. [1,2]), which is the only tile to be processed
    - original_query_string: the query string from the app, including map info. Put into log only. Good for making a URL that encodes the app view
    - no_normals: True -> all normals are 0,0,0, which speeds up processing. Most viewers will calculate normals themselves anyway
    - projection: EPSG number (as int) of projection to be used. Default (None) use the closest UTM zone
    - use_geo_coords: None, centered, UTM. not-None forces units to be in meters, centered will put 0/0 at model center for all tiles. Not-None will interpret basethickness to be in multiples of 10 meters (0.5 mm => 5 m)
    - importedGPX: None or List of GPX file paths that are to be plotted on the model
    - gpxPathHeight: Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon, therefore this is in meters. Negative numbers are ok and put a dent in the model
    - gpxPixelsBetweenPoints:  GPX Files can have a lot of points. This argument controls how many pixel distance there should be between points, effectively causing fewing lines to be drawn. A higher number will create more space between lines drawn on the model and can have the effect of making the paths look a bit cleaner at the expense of less precision
    - gpxPathThickness: Stack parallel lines on either side of primary line to create thickness. A setting of 1 probably looks the best
    - polyURL: Url to a KML file (with a polygon) as a publically read-able cloud file (Google Drive)
    - poly_file: local KML file to use as mask
    - map_image_filename: image with a map of the area
    - smooth_borders: should borders be optimized (smoothed) by removing triangles?
    - min_elev: overwrites minimum elevation for all tiles
    - tilewidth_scale: divdes m width of selection box by this to get tilewidth (supersedes tilewidth setting)
    - clean_diags: if True, repair diagonal patterns which cause non-manifold edges
    - dirty_triangles: if True creates a technically better fit fit of the water into the terrain but will create triangles that are collapsed into a line or a point. This should not be a problem for a modern slicer but will lead to issues when using the model in a 3D mesh modeling program. It will NOT affect any simple (i.e. non-water) models.
    - k3d_render: if True will create a html file containing the model as a k3d object. 


    returns the total size of the zip file in Mb

    """
    # Sanity checks:   TODO: use better exit on error instead of throwing an assert exception
    assert fileformat in ("obj", "STLa", "STLb", "GeoTiff"), "Error: unknown 3D geometry file format:"  + fileformat + ", must be obj, STLa, STLb (or GeoTiff when using local raster)"

    if bottom_elevation != None:
        assert importedDEM != None, "Error: importDEM local DEM raster file needed for bottom_elevation"

    if importedDEM == None: # GEE as DEM source
        assert DEM_name in DEM_sources, "Error: DEM source must be one of: " + ", ".join(DEM_sources)
        if fileformat != "GeoTiff":
            assert unprojected == False, "Error: STL/OBJ export cannot use unprojected, only available for GeoTiff export"
    else: # local raster file as DEM source
        assert os.path.exists(importedDEM), "Error: local DEM raster file " + importedDEM + " does not exist"
        assert fileformat != "GeoTiff", "Error: it's silly to make a Geotiff from a local DEM file (" + importedDEM + ") instead of a mesh file format ..."
        if bottom_elevation != None:
            assert os.path.exists(bottom_elevation), "Error: bottom elevation raster file " + bottom_elevation + " does not exist"


    assert not (bottom_image != None and no_bottom == True), "Error: Can't use no_bottom=True and also want a bottom_image (" + bottom_image + ")"
    assert not (bottom_image != None and basethick <= 0.5), "Error: base thickness (" + str(basethick) + ") must be > 0.5 mm when using a bottom relief image"

    assert not (bottom_elevation != None and bottom_image != None), "Error: Can't use both bottom_elevation and bottom_image"
    assert not (bottom_image != None and top_thickness != None), "Error: Can't use both bottom_image and top_thickness"
    assert not (bottom_elevation != None and no_bottom == True), "Error: Can't use no_bottom=True and also want a bottom_elevation (" + bottom_elevation + ")"
    assert not (bottom_elevation != None and top_thickness != None), "Error: Can't use both bottom_elevation and top_thickness"

    assert not (bottom_elevation != None and use_geo_coords != None), "Error: use_geo_coords is currently not supported with a bottom_elevation raster"

    # Check offset mask file
    if offset_masks_lower != None:
        for offset_pair in offset_masks_lower:
            print(offset_pair[0])
            assert os.path.exists(offset_pair[0]), "Error: local offset mask raster file " + offset_pair[0] + " does not exist"


    if not os.path.exists(temp_folder): # do we have a temp folder?
        try:
            os.mkdir(temp_folder)
        except:
            assert False, temp_folder + "doesn't exists but could also not be created"


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

    # horizontal size of "cells" on the 3D printed model (realistically: the diameter of the nozzle)
    print3D_resolution_mm = printres


    # Nov 19, 2021: As multi processing is still broken, I'm setting CPU to 1 for now ...
    #CPU_cores_to_use = 1

    #
    # get polygon data, either from GeoJSON (or just it's coordinates as a list) or from kml URL or file
    #
    clip_poly_coords = None # list of lat/lons, will create ee.Feature used for clipping the terrain image
    if polygon != None:

        # If we have a GeoJSON and also a kml
        if polyURL != None and polyURL != '':
            pr("Warning: polygon via Google Drive KML will be ignored b/c a GeoJSON polygon was also given!")
        elif poly_file != None and poly_file != '':
             pr("Warning: polygon via KML file will be ignored b/c a GeoJSON polygon was also given!")

        # Check if we have a GeoJSON polygon (i.e. a dict)  or at least a coordinate list
        # ex: {"coordinates": [[[60.48766, -81.597101], [60.571116, -81.598891], ...]], "type": "Polygon"}
        if isinstance(polygon, dict):
            assert polygon["type"] == 'Polygon', f"Error: dict is not a GeoJSON polygon: {polygon}"

            # Extract polygon coordinates (throw away [1] which would be a doughnut hole)
            clip_poly_coords = polygon["coordinates"][0] # ignore holes, which would be in 1,2, ...
        elif isinstance(polygon, list): # maybe it's just the coordinates? [[60.48766, -81.597101], [60.571116, -81.598891], ...]
            clip_poly_coords = polygon[0]
        else:
            assert False, f"Error: coordinate format must be: [[[x,y], [x,y], ...]] not {polygon}"

        logging.info("Using GeoJSON polygon for masking with " + str(len(clip_poly_coords)) + " points")

        # make area selection box from bounding box of polygon
        trlat, trlon, bllat, bllon = get_bounding_box(clip_poly_coords)

        # Hack: If we only have 5 points forming a rectangle just use the bounding box and forget about the polyon
        # Otherwise a rectangle digitized via gee ends up as a slightly sheared rectangle
        # This does assume a certain order, which seems to be the same for gee rectangles no matter how they are digitized:
        # Feb 2023: geemap appearently changed the order of the points, so I re-wrote this

        # [-98.951111, 27.505835],  p0 0 1
        # [-98.503418, 27.505835],  p1 0 1
        # [-98.503418, 27.678664],  p2 0 1
        # [-98.951111, 27.678664],  p3 0 1
        # [-98.951111, 27.505835],  ignored, same as p0

        if len(clip_poly_coords) == 5: # is it a 5 point geemap box polygon: 4 points + overlap with first
            #print("5 point clip polygon is", clip_poly_coords)
            p = clip_poly_coords  # p[0], p[1],  etc., p[x][0] is lat p[x][1] is lon
            if p[0][0] == p[3][0] and p[1][0] == p[2][0] and p[0][1] == p[1][1] and p[2][1] == p[3][1]:
                print("ignoring geemap box polygon, using bounding box", trlat, trlon, bllat, bllon)
                clip_poly_coords = None

    # Get poly from a KML file via google drive URL
    #TODO: TEST THIS!!!!!!
    elif polyURL != None and polyURL != '':
        import re, requests
        pattern = r".*[^-\w]([-\w]{25,})[^-\w]?.*" # https://stackoverflow.com/questions/16840038/easiest-way-to-get-file-id-from-url-on-google-apps-script
        matches = re.search(pattern, polyURL)
        if matches and len(matches.groups()) == 1: # need to have exactly one group match
            file_URL = "https://docs.google.com/uc?export=download&id=" + matches.group(1)
        else:
            assert False, "Error: polyURL is invalid: " + polyURL

        try:
            r = requests.get(file_URL)
            r.raise_for_status()
        except Exception as e:
            pr("Error: GDrive kml download failed", e, " - falling back to region box", trlat, trlon, bllat, bllon)
        else:
            t = r.text
            clip_poly_coords, msg = get_KML_poly_geometry(t)
            if msg != None: # Either go a line instead of polygon (take but warn) or nothing (ignore)
                logging.warning(msg + "(" + str(len(clip_poly_coords)) + " points)")
            else:
                logging.info("Read GDrive KML polygon with " + str(len(clip_poly_coords)) + " points from " + polyURL)

    elif poly_file != None and poly_file != '':
        try:
            with open(poly_file, "r") as pf:
                poly_file_str = pf.read()
        except Exception as e:
            pr("Read Error with kml file", poly_file, ":", e, " - falling back to region box", trlat, trlon, bllat, bllon)
        else:
            clip_poly_coords, msg = get_KML_poly_geometry(poly_file_str)
            if msg != None: # Either got a line instead of polygon (take but warn) or nothing (ignore)
                logging.warning(msg + "(" + str(len(clip_poly_coords)) + " points)")
            else:
                logging.info("Read file KML polygon with " + str(len(clip_poly_coords)) + " points from " + poly_file)

                # make area selection box from bounding box of polygon
                trlat, trlon, bllat, bllon = get_bounding_box(clip_poly_coords)


    # end of polygon stuff



    # This is needed to avoid python unbound error since offset_npim is currently only available for local DEMs in standalone python script
    offset_npim = []

    #
    # A) use Earth Engine to download DEM geotiff
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
        center = [(region[0][0] + region[1][0]) / 2, (region[0][1] + region[2][1]) / 2]

        # Make a more descriptive name for the selected DEM from it's official (ee) name and the center
        # if there's a / (e.g. NOAA/NGDC/ETOPO1), just get the last, ETOPO1
        DEM_title = DEM_name
        if '/' in DEM_name:
            DEM_title = DEM_title.split('/')[-1]
        DEM_title = "%s_%.2f_%.2f" % (DEM_title, center[0], center[1])

        #
        # print args to log
        #
        pr("Log for creating 3D model tile(s) for ", DEM_title, "\n")
        args = locals() # dict of local variables
        dict_for_url = {} # dict with only those args that are valid for a URL query string
        for k in ("DEM_name", "trlat", "trlon", "bllat", "bllon", "printres",
                     "ntilesx", "ntilesy", "tilewidth", "basethick", "zscale", "fileformat"):
            v = args[k]
            if k in ("basethick", "ntilesx", "ntilesx"):
                v = int(v) # need to be ints to work with the JS UI
            pr(k, "=", v)
            dict_for_url[k] = v

        # optional manual args
        for k in ("no_bottom", "bottom_image", "ignore_leq", "lower_leq", "unprojected",
        		  "only", "original_query_string", "no_normals", "projection", "use_geo_coords"):
            if args.get(k) != None: # may not have been used ...
                v = args[k]
                pr(k, "=", v)
                dict_for_url[k] = v


        pr("\nprocess started: " + datetime.datetime.now().time().isoformat())

        pr("\nRegion (lat/lon):\n  ", trlat, trlon, "(top right)\n  ", bllat, bllon, "(bottom left)")


        #
        # Figure out which projection to use when getting DEM from GEE
        #
        
        if unprojected == False:
            if projection != None:
                epsg = projection
                crs_str = f"EPSG:{epsg}"
                #utm_zone_str = crs_str
                pr("using " + crs_str + " as projection")
            elif bllat > 70: # too far north for UTM, use Arctic Polar Stereographic
                #utm_zone_str = "WGS 84 / Arctic Polar Stereographic"
                epsg = 3995
                crs_str = f"EPSG:{epsg}"
                pr("Too far north for UTM - using Arctic Polar Stereographic projection (EPSG 3995)")

            elif trlat < -55: # too far south for UTM, use Arctic Polar Stereographic
                #tm_zone_str = "WGS 84 / Arctic Polar Stereographic"
                epsg = 3031
                crs_str = f"EPSG:{epsg}"
                pr("Too far south for UTM - using Antarctic Polar Stereographic projection (EPSG 3031)")
            else:
                # get UTM zone of center to project into
                utm, hemi = LatLon_to_UTM(center)
                epsg = UTM_zone_to_EPSG_code(utm, hemi)
                crs_str = f"EPSG:{epsg}"
                pr(f"center at {center}, UTM{utm}{hemi}, {crs_str}")
        else:
            crs_str = "unprojected"

        # Although pretty good, this is still an approximation and the cell resolution to be
        # requested is therefore also not quite exact, so we need to adjust it after the EE raster is downloaded
        latitude_in_m, longitude_in_m = arcDegr_in_meter(center[1]) # returns: (latitude_in_m, longitude_in_m)
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

        # if tilewidth_scale is given, overwrite tilewidth by region width / tilewidth_scale
        if tilewidth_scale != None:
            tilewidth = region_size_in_meters[1] / tilewidth_scale * 1000 # new tilewidth in mm
            pr("Overriding tilewidth using a tilewidth_scale of 1 :", tilewidth_scale, ", region width is", region_size_in_meters[1], "m, new tilewidth is", tilewidth, "(Note that the final scale may be slighly different!)")

        # width/height (in 2D) of 3D model of ONE TILE to be printed, in mm
        print3D_width_per_tile = tilewidth # EW
        print3D_height_per_tile = (print3D_width_per_tile * num_tiles[0] * region_ratio) / float(num_tiles[1]) # NS

        # width/height of full 3D model (all tiles together)
        print3D_width_total_mm =  print3D_width_per_tile * num_tiles[0] # width => EW
        print3D_height_total_mm = print3D_width_total_mm * region_ratio   # height => NS

        if print3D_resolution_mm > 0:

            # Get a cell size for EE

            # number of samples needed to cover ALL tiles
            num_samples_lat = print3D_width_total_mm  / float(print3D_resolution_mm) # width
            num_samples_lon = print3D_height_total_mm / float(print3D_resolution_mm) # height
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
        if DEM_name in ("NRCan/CDEM", "AU/GA/AUSTRALIA_5M_DEM"):  # Image collection?
            coll = ee.ImageCollection(DEM_name)
            info = coll.getInfo()
            elev = coll.select('elevation')
            proj = elev.first().select(0).projection() # must use common projection(?)
            image1 = elev.mosaic().setDefaultProjection(proj) # must mosaic collection into single image
        else:
            image1 = ee.Image(DEM_name)
            info = image1.getInfo()


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


        # if we got clip_poly_coords, clip the image, using -32768 as NoData value
        if clip_poly_coords != None:
            clip_polygon = ee.Geometry.Polygon([clip_poly_coords])
            clip_feature = ee.Feature(clip_polygon)
            image1 = image1.clip(clip_feature).unmask(-32768, False)

        # Make a geoJSON polygon to define the area to be printed
        reg_rect = ee.Geometry.Rectangle([[bllon, bllat], [trlon, trlat]]) # opposite corners
        if polygon == None:
            polygon_geojson = reg_rect.toGeoJSONString() # polyon is just the bounding box
        else:
            polygon_geojson = polygon # actual polygon used as mask

        # make the request dict
        request_dict = {
            #'scale': 10, # cell size
            'scale': cell_size_m, # cell size in meters
            #'region': "{\"type\":\"Polygon\",\"coordinates\":[[[-120,34],[-120,35],[-119,35],[-119,34]]],\"evenOdd\":true}"
            'region': polygon_geojson, # geoJSON polygon
            #'crs': 'EPSG:4326',
            'crs': crs_str, # projection
        }

        # if cellsize is <= 0, just get whatever GEE's default cellsize is (printres = -1)
        if cell_size_m <= 0: del request_dict["scale"]

        # force to use unprojected (lat/long) instead of UTM projection, can only work for Geotiff export
        if unprojected == True: del request_dict["crs"]

        request = image1.getDownloadUrl(request_dict)
        pr("URL for geotiff is: ", request)

        # Retry download zipfile from url until request was successfull
        web_sock = None
        while web_sock == None:
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

            # at any exception, wait for a couple of secs
            if web_sock == None:
                time.sleep(random.randint(1,10))

        # read the zipped folder into memory
        buf = web_sock.read()
        web_sock.close()
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

        # geotiff as data string
        str_data = zipdir.read(tif)

        # write the GEE geotiff into the temp folder and add it to the zipped d/l folder later
        GEE_dem_filename =  temp_folder + os.sep + zip_file_name + "_dem.tif"
        with open(GEE_dem_filename, "wb+") as out:
            out.write(str_data)

        # use GDAL to get cell size and undef value of geotiff
        dem = gdal.Open(GEE_dem_filename)
        ras_x_sz = dem.RasterXSize # number of pixels in x
        ras_y_sz = dem.RasterYSize
        band = dem.GetRasterBand(1)
        dem_undef_val = band.GetNoDataValue()
        geo_transform = dem.GetGeoTransform()
        GEE_cell_size_m =  (geo_transform[1], geo_transform[5])

        # if we requested the true resolution of the source with -1, use the cellsize of the gdal/GEE geotiff
        if cell_size_m <= 0:
            cell_size_m = geo_transform[1]

        pr(" geotiff size:", len(str_data) / 1048576.0, "Mb")
        pr(" cell size", cell_size_m, "m, upper left corner (x/y): ", geo_transform[0], geo_transform[3])

        if fileformat == "GeoTiff": # for Geotiff output, we don't need to make a numpy array, etc, just close the GDAL dem so we can move it into the zip later
            dem = None #  Python GDAL's way of closing/freeing the raster
            del band

        else:  # mesh file export
            assert abs(geo_transform[1]) == abs(geo_transform[5]), "Error: raster cells are not square!" # abs() b/c one can be just the negative of the other in GDAL's geotranform matrix

            # typically, EE does not use proper undefined values in the geotiffs it serves, but just in case ...
            if dem_undef_val != None:
                logger.debug("undefined DEM value used by GEE geotiff: " + str(dem_undef_val))

            # delete zip file and buffer from memory
            GEEZippedGeotiff.close()
            del zipdir, str_data

            # although STL can only use 32-bit floats, we need to use 64 bit floats
            # for calculations, otherwise we get non-manifold vertices!
            npim = band.ReadAsArray().astype(numpy.float64)
            #npim = band.ReadAsArray().astype(numpy.longdouble)
            #print(npim, npim.shape, npim.dtype, numpy.nanmin(npim), numpy.nanmax(npim)) #DEBUG

            # Do a quick check if all the values are the same, which happens if we didn't get
            # any actual elevation data i.e. the area was not covered by the DEM
            if numpy.all(npim == npim[0,0]): # compare to first cell value
                s = "All(!) elevation values are " + str(npim[0,0]) + "! "
                s += "This may happen if the DEM source does not cover the selected area.\n"
                s += "For the web app, ensure that your red selection box is at least partially covered by the grey hillshade overlay "
                s += "or try using AW3D30 as DEM source."
                assert False, s # bail out

            # For AU/GA/AUSTRALIA_5M_DEM, replace all exact 0 value with NaN
            # b/c there are spots on land that have no pixels, but these are encoded as 0 and
            # need to be marked as NaN otherwise they screw up the thickness of the base
            if DEM_name == "AU/GA/AUSTRALIA_5M_DEM":
                npim = numpy.where(npim == 0.0, numpy.nan, npim)

            # Add GPX points to the model (thanks KohlhardtC!)
            if importedGPX != None and importedGPX != []:
                from touchterrain.common.TouchTerrainGPX import addGPXToModel
                addGPXToModel(pr, npim, dem, importedGPX,
                              gpxPathHeight, gpxPixelsBetweenPoints, gpxPathThickness,
                              trlat, trlon, bllat, bllon)

            # clip values?
            if ignore_leq != None:
                npim = numpy.where(npim <= ignore_leq, numpy.nan, npim)
                pr("ignoring elevations <= ", ignore_leq, " (were set to NaN)")

            # Polygon masked pixels will have been set to -32768, so turn
            # these into NaN. Huge values can also occur outside
            # polygon masking (e.g. offshore pixels in GTOPO or non US pixels in NED)
            min_elevation = numpy.nanmin(npim) # independent from arg min_elev!
            if min_elevation < -16384:
                npim = numpy.where(npim <  -16384, numpy.nan, npim)
                pr("omitting cells with elevation < -16384")
            if numpy.nanmax(npim) > 16384:
                npim = numpy.where(npim >  16384, numpy.nan, npim)
                pr("omitting cells with elevation > 16384")
            pr("full (untiled) raster (height,width) ", npim.shape, npim.dtype, "elev. min/max:", numpy.nanmin(npim), numpy.nanmax(npim))

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
                pr("adjusted print res from the requested", print3D_resolution_mm, "mm to", adjusted_print3D_resolution, "mm to ensure correct model dimensions")
                print3D_resolution_mm = adjusted_print3D_resolution
            else:
                print3D_resolution_mm = adjusted_print3D_resolution
                pr("cell size:", cell_size_m, "m (<- native source resolution)")
                pr("print res for native source resolution is", print3D_resolution_mm, "mm")

            pr("total model size in mm:", print3D_width_total_mm, "x", print3D_height_total_mm)
    # end of getting DEM data via GEE (A)


    #
    # B) DEM data comes from a local raster file (geotiff, etc.)
    #
    # TODO: deal with clip polygon?  Done for KML (poly_file)

    else:
        filename = os.path.basename(importedDEM)

        if bottom_elevation != None:
            btxt = "and " + bottom_elevation
        elif top_thickness != None:
            btxt = "and " + top_thickness
        else:
            btxt = ""
        pr("Log for creating", num_tiles[0], "x", num_tiles[1], "3D model tile(s) from", filename, btxt, "\n")
        pr("started:", datetime.datetime.now().time().isoformat())

        # If we have a KML file, use it to mask (clip) and crop the importedDEM
        if poly_file != None and poly_file != '':
            clipped_geotiff = "clipped_" + filename

            try:
                gdal.Warp(clipped_geotiff, filename,
                    format='GTiff',
                    warpOptions=['CUTLINE_ALL_TOUCHED=TRUE'],
                    cutlineDSName=poly_file,
                    cropToCutline=True,
                    dstNodata=-32768)
            except Exception as e:
                pr("clipping", filename, "with", poly_file, "failed, using unclipped geotiff. ", e)
            else:
                pr("clipped", filename, "with", poly_file, "now using", clipped_geotiff, "instead")
                folder = os.path.split(importedDEM)[0]
                importedDEM = os.path.join(folder, clipped_geotiff)

        # Make numpy array from imported geotiff
        dem = gdal.Open(importedDEM)
        band = dem.GetRasterBand(1)
        npim = band.ReadAsArray().astype(numpy.float64) # top elevation values

        # Read in offset mask file (Anson's stuff ...)
        if offset_masks_lower is not None:
            offset_dem = gdal.Open(offset_masks_lower[0][0])
            offset_band = offset_dem.GetRasterBand(1)
            offset_npim.append(offset_band.ReadAsArray().astype(numpy.float64))
            del offset_band
            offset_dem = None

        # get the GDAL cell size in x (width), assumes cells are square!
        tf = dem.GetGeoTransform()  # In a north up image, padfTransform[1] is the pixel width, and padfTransform[5] is the pixel height
        # The upper left corner of the upper left pixel is at position (padfTransform[0],padfTransform[3]).
        pw,ph = abs(tf[1]), abs(tf[5])
        if pw != ph:
            logger.warning("Warning: raster cells are not square (" + str(pw) + "x" + str(ph) + ") , using" + str(pw))
        cell_size_m = pw
        pr("source raster upper left corner (x/y): ",tf[0], tf[3])
        pr("source raster cells size", cell_size_m, "m ", npim.shape)
        geo_transform = tf

        def get_GDAL_projection_and_datum(raster):
            ''' from a valid GDAL raster, get the projection and datum as strings
            returns: projection, datum
            '''
            #local function b/c I need to do this for top and possible bottom raster
            spatial_ref = raster.GetProjection()

            # Create an OSR SpatialReference object from the spatial reference string
            sr = osr.SpatialReference()
            sr.ImportFromWkt(spatial_ref)

            # Get the projection information (projection name)
            projection = sr.GetAttrValue("PROJECTION")

            # Get the datum information (datum name)
            datum = sr.GetAttrValue("DATUM")

            return projection, datum

        proj_str, datum_str = get_GDAL_projection_and_datum(dem)
        crs_str = proj_str # for local rasters, we use the projection string

        # if we have a GDAL undefined value, set all cells with that value to NaN
        dem_undef_val = band.GetNoDataValue()
        pr("undefined DEM value:", dem_undef_val)
        if dem_undef_val != None:  # None means the raster is not a geotiff, so no undef values
            undef_cells = numpy.isclose(npim, dem_undef_val) # bool with cells that are close to the GDAL undef value
            npim = numpy.where(undef_cells, numpy.nan, npim) # replace GDAL undef values with nan


        # for a bottom raster or a thickness raster, check that it matches the top raster
        if bottom_elevation != None or top_thickness != None:
            if bottom_elevation != None:
                ras = gdal.Open(bottom_elevation) # using ras here b/c it can be one of two rasters
            else:
                ras = gdal.Open(top_thickness)
            ras_band = ras.GetRasterBand(1)
            ras_npim = ras_band.ReadAsArray().astype(numpy.float64) # bottom elevation or thickness values as numpy array
            ras_tf = ras.GetGeoTransform()
            ras_pw, ras_ph = abs(ras_tf[1]), abs(ras_tf[5]) # pixel width and height
            if ras_pw != pw or ras_ph != ph:
                logger.warning("Warning: bottom_elevation or top_thickness raster cells are not square (" + str(ras_pw) + "x" + str(ras_ph) + ") , using" + str(ras_pw))
            ras_cell_size_m = ras_pw

            if dem.RasterXSize != ras.RasterXSize or dem.RasterYSize != ras.RasterYSize:
                assert False, f"Error: bottom_elevation or top_thickness raster sizes ({ras.RasterXSize} x {ras.RasterYSize}) does not match (top) DEM size ({dem.RasterXSize} x {dem.RasterYSize})"

            if ras_cell_size_m != cell_size_m: # do bottom/thickness cells match top cells?
                assert False, f"Error: bottom_elevation or top_thickness raster cell size ({ras_cell_size_m}) does not match (top) DEM cell size ({cell_size_m})"

            # get and compare projection and datum
            ras_proj_str, ras_datum_str = get_GDAL_projection_and_datum(ras)
            if ras_proj_str != proj_str or ras_datum_str != datum_str:
                assert False, f"Error: bottom_elevation or top_thickness raster projection ({ras_proj_str}) or datum ({ras_datum_str}) does not match (top) DEM projection ({proj_str}) or datum ({datum_str})"

            # get undef value and write it into the numpy array
            ras_undef_val = ras_band.GetNoDataValue()
            pr("undefined bottom elevation or thickness value:", ras_undef_val)
            if ras_undef_val != None:  # None means the raster is not a geotiff so we don't support undef values
                undef_cells = numpy.isclose(ras_npim, ras_undef_val) # bool with cells that are close to the undef value
                ras_npim = numpy.where(undef_cells, numpy.nan, ras_npim) # replace undef values with nan

            # get bottom elevation as numpy array or create it be subtracting thickness from top elevation
            if bottom_elevation != None:
                bot_npim = ras_npim # numpy array to be used later
            else:
                bot_npim = npim - ras_npim   # bottom = top - thickness
                del ras_npim # don't need it anymore
                # Pretend we have a bottom elevation raster of that name so all further checks for bottom will work
                bottom_elevation = top_thickness

            # close/delete the GDAL raster and band here, b/c I only need the numpy array from now on (and meta data has been stored)
            ras = None # close the GDAL raster on disk
            del ras_band


        # Print out some info about the raster
        pr("DEM (top) raster file:", importedDEM)
        if top_thickness != None and top_thickness != '':
            pr("Top thickness raster file:", top_thickness)
        elif bottom_elevation != None:
            pr("Bottom elevation raster file:", bottom_elevation)
        pr("DEM projection & datum:", proj_str, datum_str)
        pr("z-scale:", zscale)
        pr("basethickness:", basethick)
        pr("fileformat:", fileformat)
        pr("tile_centered:", tile_centered)
        pr("no_bottom:", no_bottom)
        pr("no_normals:", no_normals)
        pr("ignore_leq:", ignore_leq)
        pr("lower_leq:", lower_leq)
        pr("importedGPX:", importedGPX)
        #pr("polyURL:", polyURL)

        # Warn that anything with polygon will be ignored with a local raster (other than offset_masks!)
        if polygon != None or  (polyURL != None and polyURL != ''):
            pr("Warning: Given outline polygon will be ignored when using local raster file!")

        # Add GPX points to the model (thanks KohlhardtC and ansonl!)
        if importedGPX != None and importedGPX != []:
            from touchterrain.common.TouchTerrainGPX import addGPXToModel
            addGPXToModel(pr, npim, dem, importedGPX,
                          gpxPathHeight, gpxPixelsBetweenPoints, gpxPathThickness,
                          trlat, trlon, bllat, bllon)

        # clip values?
        if ignore_leq != None:
            npim = numpy.where(npim <= ignore_leq, numpy.nan, npim)
            pr("ignoring elevations <= ", ignore_leq, " (were set to NaN)")


        # if tilewidth_scale is given, overwrite mm tilewidth by region width / tilewidth_scale
        if tilewidth_scale != None:
            tilewidth = region_size_in_meters[1] / tilewidth_scale * 1000 # new tilewidth in mm
            pr("Overriding tilewidth using a tilewidth_scale of 1 :", tilewidth_scale, ", region width is", region_size_in_meters[1], "m, new tilewidth is", tilewidth, "mm. (Note that the final scale may be slighly different!)")


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
        if printres <= 0: # use of source resolution was requested (typically set as -1)
                pr("no resampling, using source resolution of ", source_print3D_resolution, "mm for a total model width of", print3D_width_total_mm, "mm")
                if source_print3D_resolution < 0.2 and fileformat != "GeoTiff":
                    pr("Warning: this print resolution of", source_print3D_resolution, "mm is pretty small for a typical nozzle size of 0.4 mm. You might want to use a printres that's just a bit smaller than your nozzle size ...")
                print3D_resolution_mm = source_print3D_resolution

        else: # yes, resample
            scale_factor = print3D_resolution_mm / float(source_print3D_resolution)
            if scale_factor < 1.0:
                pr("Warning: will re-sample to a resolution finer than the original source raster. Consider instead a value for printres >", source_print3D_resolution)

            # re-sample DEM (and bottom_elevation) using PIL
            pr("re-sampling", filename, ":\n ", npim.shape[::-1], source_print3D_resolution, "mm ", cell_size_m, "m ", numpy.nanmin(npim), "-", numpy.nanmax(npim), "m")
            npim =  resampleDEM(npim, scale_factor)
            if bottom_elevation != None:
                pr("re-sampling", bottom_elevation, ":\n ", bot_npim.shape[::-1], source_print3D_resolution, "mm ", cell_size_m, "m ", numpy.nanmin(bot_npim), "-", numpy.nanmax(bot_npim), "m")
                bot_npim =  resampleDEM(bot_npim, scale_factor)

            # re-sample offset mask
            for index, offset_layer in enumerate(offset_npim):
                pr("re-sampling offset layer",index, ":\n ", offset_layer.shape[::-1], source_print3D_resolution, "mm ", cell_size_m, "m ", numpy.nanmin(offset_layer), "-", numpy.nanmax(offset_layer), "m")
                offset_npim[index] = resampleDEM(offset_layer, scale_factor)

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

            if adjusted_print3D_resolution != print3D_resolution_mm:
                pr("after resampling, requested print res was adjusted from", print3D_resolution_mm, "to", adjusted_print3D_resolution, "to ensure correct model dimensions")
                print3D_resolution_mm = adjusted_print3D_resolution
            else:
                pr("print res is", print3D_resolution_mm, "mm")

        DEM_title = filename[:filename.rfind('.')]
    # end of B: (local raster file)

    # Make empty zip file in temp_folder, add files into it later
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
        if remx > 0 or remy > 0:
            pr(f"Cropping for nice fit of {num_tiles[0]} (width) x {num_tiles[1]} (height) tiles, removing: {remx} columns, {remy} rows")
            old_shape = npim.shape
            npim = npim[0:npim.shape[0] - remy, 0:npim.shape[1] - remx]
            pr("cropped", old_shape[::-1], "to", npim.shape[::-1])

            if bottom_elevation != None:
                bot_npim = bot_npim[0:bot_npim.shape[0]-remy, 0:bot_npim.shape[1]-remx]
                pr("cropped bottom elevation raster to", bot_npim.shape[::-1])

            for index, offset_layer in enumerate(offset_npim):
                offset_npim[index] = offset_layer[0:offset_layer.shape[0]-remy, 0:offset_layer.shape[1]-remx]

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

        # if scale X is negative, assume it means scale up to X mm high and calculate required z-scale for that height
        if zscale < 0:
            unscaled_elev_range_m = numpy.nanmax(npim) - numpy.nanmin(npim) # range at 1 x scale
            scaled_elev_range_m = unscaled_elev_range_m / print3D_scale_number # convert range from real m to model/map m
            pos_zscale = -zscale
            requested_elev_range_m = -zscale / 1000 # requested range as m (given as mm)
            zscale = requested_elev_range_m / scaled_elev_range_m # z-scale needed to get to a model with the requested range
            pr("From requested model height of", pos_zscale, "mm, calculated a z-scale of", zscale)

        # lower cells less/equal a certain elevation?
        if lower_leq is not None:
            assert len(lower_leq) == 2, \
                f"lower_leq should have the format [threshold, offset]. Got {lower_leq}"
            #sf = (print3D_height_total_mm / 1000) / region_size_in_meters[1] # IdenC
            #offset = (lower_leq[1] / 1000) / sf

            threshold = lower_leq[0]
            offset = lower_leq[1] / 1000 * print3D_scale_number  # scale mm up to real world meters
            offset /= zscale # => unaffected by zscale

            # Instead of lowering, shift elevations greater than the threshold up to avoid negatives
            npim = numpy.where(npim > threshold, npim + offset, npim)
            pr("Lowering elevations <= ", threshold, " by ", offset, "m, equiv. to", lower_leq[1],  "mm at map scale")

        # offset (lower) cells highlighted in the offset_masks files
        if offset_masks_lower is not None:
            count = 0
            for offset_layer in offset_npim:
                offset = offset_masks_lower[count][1] / 1000 * print3D_scale_number  # scale mm up to real world meters
                offset /= zscale # account for zscale

                # Invert the mask layer in order to raise all areas not previously masked.
                # Subtracting elevation into negative values will cause an invalid STL to be generated.
                offset_layer = numpy.where(offset_layer > 0, 0, 1)
                offset_layer = numpy.multiply(offset_layer, 1 * offset)
                npim = numpy.add(npim, offset_layer)
                pr("Offset masked elevations by raising all non masked areas of", offset_masks_lower[count][0],"by", offset, "m, equiv. to", offset_masks_lower[count][1],  "mm at map scale")
                npim = numpy.where(npim < 0, 0, npim)
                count += 1

        # fill (< 0 elevation) holes using a 3x3 footprint. Requires scipy. 
        # [0] is number of iterations, [1] is number of neighbors
        if fill_holes is not None and (fill_holes[0] > 0 or fill_holes[0] == -1):
            npim = fillHoles(npim, num_iters=fill_holes[0], num_neighbors=fill_holes[1])

        #
        # if we have a bottom elevation raster do some checks and preparations 
        # This part was originally in grid_tesselate.py and I'm too lasy to refactor its
        # variable names so I'll just do some aliasing here
        #
        np = numpy
        top = npim
        top_orig = None # maybe used later as backup if top gets NaN'd
        have_nan = np.any(np.isnan(npim)) # check if we have NaNs in the top raster
        throughwater = False # special flag for NaNs in bottom raster

        if bottom_elevation is not None:
            bottom = bot_npim

            # where top is actually lower than bottom (which can happen with Anson's data), set top to bottom
            top = np.where(top < bottom, bottom, top)

            # bool array with True where bottom has NaN values but top does not
            # this is specific to Anson's way of encoding through-water cells
            nan_values = np.logical_and(np.isnan(bottom), np.logical_not(np.isnan(top)))
            if np.any(nan_values) == True: 
                bottom[nan_values] = 0 # set bottom NaN values to 0 
                throughwater = True # flag for easy checking

            # if both have the same value (or very close to) set both to Nan
            # No relative tolerance here as we don't care about this concept here. Set the abs. tolerance to 0.001 m (1 mm)
            close_values = np.isclose(top, bottom, rtol=0, atol=0.001, equal_nan=False) # bool array

            # for any True values in array, set corresponding top and bottom cells to NaN
            # Also set NaN flags
            if np.any(close_values) == True: 
                # save pre-dilated top for later dilation
                top_pre_dil = top.copy()  
                top[close_values] = np.nan   # set close values to NaN   

                # if diagonal cleanup is requested, we need to do it again after setting NaNs
                #clean_up_diags_check(top)

                # save original top after setting NaNs so we can skip the undilated NaN cells later
                top_orig = top.copy()  
                top = dilate_array(top, top_pre_dil) # dilate the NaN'd top with the original (pre NaN'd) top

                bottom[close_values] = np.nan # set close values to NaN 
                #clean_up_diags_check(bottom) # re-check for diags
                
                if throughwater == True:
                    bottom = dilate_array(bottom) # dilate with 3x3 nanmean #  
                else:
                    bottom = dilate_array(bottom, top_pre_dil) # dilate the NaN'd bottom with the original (pre NaN'd) top (same as original bottom)

                # pre-dilated top is not needed anymore
                del top_pre_dil

        # if we have no bottom but have NaNs in top, make a copy and 3x3 dilate it. 
        # We'll still use the non-dilated top_orig when we need to skip NaN cells
        elif np.any(np.isnan(npim)):
            top_orig = top.copy()   # save original top before it gets dilated
            top = dilate_array(top) # dilate with 3x3 nanmean 


        # repair these patterns, which cause non_manifold problems later:
        # 0 1    or     1 0
        # 1 0    or     0 1
        if clean_diags == True:
            npim = clean_up_diags(npim)
            if bottom_elevation != None:  
                bot_npim = clean_up_diags(bot_npim) 
                # TODO: check if this is needed as top NaNs dictate if a cell
                # should be skipped or not

        #
        # deal with min_elev and min_bottom_elev (and user set min_elev)
        #

        # set minimum elevation for top (will be used by all tiles)
        user_offset = 0  # no offset unless user specified min_elev
        min_bottom_elev = None
        if min_elev != None: # user-given minimum elevation (via min_elev argument)
            if bottom_elevation != None: # have a bottom elevation
                 min_bottom_elev = numpy.nanmin(bot_npim) #(actual min elev for all tiles)
            user_offset = numpy.nanmin(npim) - min_elev 
            min_elev = numpy.nanmin(npim) #(actual min elev for all tiles)
        else: # no user-given min_elev
            min_elev = numpy.nanmin(npim)
            if bottom_elevation != None:
                min_bottom_elev = numpy.nanmin(bot_npim)

        print(f"elev min/max : {min_elev:.2f} to {numpy.nanmax(npim):.2f}")
        if bottom_elevation != None:
                print(f"bottom elev min/max : {numpy.nanmin(bot_npim):.2f} to {numpy.nanmax(bot_npim):.2f}")

        #
        # plot DEM and histogram, save as png
        #
        plot_file_name = plot_DEM_histogram(npim, DEM_name, temp_folder)
        print(f"DEM plot and histogram saved as {plot_file_name}", file=sys.stderr)

        #
        # create tile info dict
        #
        tile_info = {
            "DEMname": DEM_name, # name of raster requested from earth eng.
            "bottom_elevation": bottom_elevation, # None or name of bottom elevation raster
            "crs" : crs_str, # cordinate reference system, can be EPSG code or UTM zone or any projection
            #"UTMzone" : utm_zone_str, # UTM zone e.g. UTM13N or
            "scale"  : print3D_scale_number, # horizontal scale number,  1000 means 1:1000 => 1m in model = 1000m in reality
            "z_scale" : zscale,  # z (vertical) scale (elevation exageration) factor
            "pixel_mm" : print3D_resolution_mm, # lateral (x/y) size of a 3D printed "pixel" in mm
            "min_elev" : min_elev, # needed for multi-tile models
            "user_offset":  user_offset, # offset between user given min_elev and actual data min_elev
            "min_bot_elev" : min_bottom_elev, # needed for multi-tile models
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
            "no_bottom": no_bottom, # omit bottom triangles?
            "bottom_image": bottom_image, # None or name of bottom image file (for relief)
            "ntilesy": ntilesy, # number of tiles in y, ntilesx is not needed here
            "only": only, # if nont None, process only this tile e.g. [1,2]
            "no_normals": no_normals, # calculate normals?
            "geo_transform": geo_transform, # GeoTransform of geotiff
            "use_geo_coords": use_geo_coords, # create STL coords in UTM: None, "centered" or "UTM"
            "smooth_borders": smooth_borders, # optimize borders?
            "clean_diags": clean_diags, # remove diagonal patterns?
            "dirty_triangles": dirty_triangles, # allow creating of better fitting but potentiall degenerate triangles
            "throughwater": throughwater, # special flag for NaNs in bottom raster
        }


        #
        # Make tiles (subsets) of the full raster and generate 3D grid model
        #

        # num_tiles[0], num_tiles[1]: x, y !
        cells_per_tile_x = int(npim.shape[1] / num_tiles[0]) # tile size in pixels
        cells_per_tile_y = int(npim.shape[0] / num_tiles[1])
        pr("Cells per tile (x/y)", cells_per_tile_x, "x", cells_per_tile_y)


        # pad full rasters(s) by one at the fringes
        npim = numpy.pad(npim, (1,1), 'edge') # will duplicate edges, including nan
        if bottom_elevation != None:
            bot_npim = numpy.pad(bot_npim, (1,1), 'edge')
        if top_orig is not None:
            top_orig =  numpy.pad(top_orig, (1,1), 'edge')

        # store size of full raster
        tile_info["full_raster_height"], tile_info["full_raster_width"]  = npim.shape

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


                if bottom_elevation != None :
                    tile_bot_elev_raster = bot_npim[start_y:end_y, start_x:end_x] #  [y,x]
                    tile_bot_elev_raster.flags.writeable = False
                else:
                    tile_bot_elev_raster = None

                tile_elev_orig_raster = None
                if top_orig is not None:
                    tile_elev_orig_raster =  top_orig[start_y:end_y, start_x:end_x]
                    tile_elev_orig_raster.flags.writeable = False 

                # add to tile_list
                tile_info["tile_no_x"] = tx + 1
                tile_info["tile_no_y"] = ty + 1
                my_tile_info = tile_info.copy() # make a copy of the global info, so we can store tile specific info in during processing

                # if raster is too large, use temp files to create the tile STL/obj files
                if tile_info["full_raster_height"] * tile_info["full_raster_width"]  > max_cells_for_memory_only:
                    # use a temp file in local tmp folder
                    # Note: yes, I tried using a named tempfile, which works nicely except for MP and it's too hard to figure out the issue with MP
                    mytempfname = f"{temp_folder}{os.sep}{zip_file_name}{tile_info['tile_no_x']}{tile_info['tile_no_y']}.tmp"

                    # store temp file names (not file objects), MP will create file objects during processing
                    my_tile_info["temp_file"]  = mytempfname

                # assemble tile to be processed
                tile = (my_tile_info, tile_elev_raster, tile_bot_elev_raster, tile_elev_orig_raster)   # leave it to process_tile() to unwrap the info and data parts

                # if we only process one tile ...
                if process_only == None: # "only" parameter was not given
                    tile_list.append(tile)
                else:
                    if process_only[0] == tile_info['tile_no_x'] and process_only[1] == tile_info['tile_no_y']:
                        tile_list.append(tile) # got the only tile
                    else:
                        print("process only is:", process_only, ", skipping tile", tile_info['tile_no_x'], tile_info['tile_no_y'])

        if tile_info["full_raster_height"] * tile_info["full_raster_width"]  > max_cells_for_memory_only:
            logger.debug("tempfile or memory? number of pixels:" + str(tile_info["full_raster_height"] * tile_info["full_raster_width"]) + ">" + str(max_cells_for_memory_only) + " => using temp file")


        # single core processing: just work on the list sequentially, don't use multi-core processing.
        # if there's only one tile or one CPU or CPU_cores_to_use is still at default None.
        # processed list will contain tuple(s): [0] is always the tile info dict, if its
        # "temp_file" is None, we got a buffer, but if "temp_file" is a string, we got a file of that name
        # [1] can either be the buffer or again the name of the temp file we just wrote (which is redundant, i know ...)
        if num_tiles[0] * num_tiles[1] == 1 or CPU_cores_to_use == 1 or CPU_cores_to_use == None:
            pr("using single-core only (multi-core is currently broken :(")
            processed_list = []
            # Convert each tile into a list: [0]: updated tile info, [1,2,3]: rasters (or None)
            for i,t in enumerate(tile_list):
                # t[0] is the tile info dict, t[1] is the numpy array of elevations, t[2] is the numpy array of bottom elevations or None
                #print "processing", i, numpy.round(t[1], 1), t[0]

                pt = process_tile(t)  # pt is a tuple: [0]: updated tile info, [1]: grid object (or None)
                if pt[1] is not None: # if we got a grid object and not None
                    processed_list.append(pt) # append to list of processed tiles
                else:
                    try: # delete temp file b/c it's only a STLb header from a tile with no elevations
                        os.remove(pt[0]["temp_file"])
                    except Exception as e:
                        logger.error("Error removing" + str(pt[0]["temp_file"]) + " " + str(e))
            

        # use multi-core processing
        else:

            #if CPU_cores_to_use is 0(!) us all cores, otherwise use that number
            if CPU_cores_to_use == 0:
                num_cores = None
                num_core_str = "all"
            else:
                num_cores = CPU_cores_to_use
                num_core_str = str(num_cores)
            # TODO: Using 0 here that needs to become None is confusing, but too esoteric to clean up ..
            # Better: make default 1, else use MP with None (meaning all)

            pr("Multiprocessing: using " + num_core_str + " cores (no logging info available while processing)  ...")
            import multiprocessing
            #import dill as pickle

            # As per Nick this is needed to make MP work with gnunicon on linux
            # b/c the default on unix is fork not spawn which starts faster but can also
            # be problematic so now we're using the slower starting spawn
            mp = multiprocessing.get_context('spawn')
            pool = mp.Pool(processes=num_cores, maxtasksperchild=1) # processes=None means use all available cores

            # Convert each tile in tile_list and return as list of lists: [0]: updated tile info, [1]: grid object
            try:
                print("Before map()\n", file=sys.stderr)  # DEBUG
                processed_list = pool.map(process_tile, tile_list)
                print("After map()\n", file=sys.stderr)   # DEBUG
            except Exception as e:
                pr(e)
            else:
                pool.close()
                pool.terminate()

            pr("... multi-core processing done, logging resumed")

        # the tile width/height was written into tileinfo during processing
        pr(f"\n{num_tiles[0]} x {num_tiles[1]} tiles, tile size {tile_info['tile_width']:.2f} x {tile_info['tile_height']:.2f} mm\n")

        # delete tile list, as the elevation arrays are no longer needed
        del tile_list

        # stl_list will contain the stl/obj files or buffers 
        # we can use it later to create a k3d render
        stl_list = [] # make list of filenames or buffers

        # concat all processed tiles into a zip file
        #print "start of putting tiles into zip file")
        for p in processed_list:
                tile_info = p[0] # per-tile info
                tile_name = f"{DEM_title}_tile_{tile_info['tile_no_x']}_{tile_info['tile_no_y']}.{fileformat[:3]}" # name of file inside zip
                buf= p[1] # either a string or a file object

                if tile_info.get("temp_file") != None: # if buf is a file 
                    fname = tile_info["temp_file"]
                    stl_list = add_to_stl_list(fname, stl_list)
                    zip_file.write(fname , tile_name) # write temp file into zip
                else:
                    zip_file.writestr(tile_name, buf) # buf is a string
                    stl_list = add_to_stl_list(buf, stl_list)


                total_size += tile_info["file_size"]
                logger.debug("adding tile %d %d, total size is %d" % (tile_info["tile_no_x"],tile_info["tile_no_y"], total_size))

                # print size and elev range
                pr("tile", tile_info["tile_no_x"], tile_info["tile_no_y"], ": height: ", tile_info["min_elev"], "-", tile_info["max_elev"], "mm",
                   ", file size:", round(tile_info["file_size"]), "Mb")


        pr("\ntotal size for all tiles:", round(total_size, 1), "Mb")

        # delete all the GDAL geotiff stuff
        del npim
        del band
        dem = None #  Python GDAL's way of closing/freeing the raster, needed to be able to delete the inital geotiff

        # clean up data for offset_masks
        if offset_masks_lower is not None:
            for offset_layer in offset_npim:
                del offset_layer


        # make k3d render
        if kd3_render == True and (fileformat == "STLa" or fileformat == "STLb"):
            if tile_info.get("temp_file") != None:
                html_file = k3d_render_to_html(stl_list, temp_folder, buffer=False)
            else:
                html_file = k3d_render_to_html(stl_list, temp_folder, buffer=True)
            zip_file.write(html_file, "k3d_plot.html") # write into zip


        # file or buffer cleanup
        for p in processed_list:
            tile_info = p[0]
            buf= p[1]
            if tile_info.get("temp_file") != None:
                try:
                    os.remove(fname) # on windows remove closed file manually
                except Exception as e:
                    logger.error("Error removing" + str(fname) + " " + str(e))
            else:
                del buf # delete buffer


    # end of: if fileformat != "GeoTiff"

    print("zip finished:", datetime.datetime.now().time().isoformat())

    # add (full) geotiff we got from EE to zip
    if importedDEM == None:
        total_size += os.path.getsize(GEE_dem_filename) / 1048576
        zip_file.write(GEE_dem_filename, DEM_title + ".tif")
        pr("added full geotiff as " + DEM_title + ".tif")
        plot_file_name = plot_DEM_histogram(npim, DEM_name, temp_folder)
        pr(f"DEM plot and histogram saved as {plot_file_name}", file=sys.stderr)

    # add png from Google Maps static (ISU server doesn't use that b/c it eats too much into our free google maps allowance ...)
    if map_img_filename != None:
        zip_file.write(map_img_filename, DEM_title + ".jpg")
        pr("added map of area as " + DEM_title + ".jpg")

    pr("\nprocessing finished: " + datetime.datetime.now().time().isoformat())

    # add plot with histogram to zip
    zip_file.write(plot_file_name, "elevation_plot_with_histogram.png")


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

    # remove map image
    if map_img_filename != None:
        try:
            os.remove(map_img_filename)
        except Exception as e:
            print("Error removing plot_with_histogram.png" + str(map_img_filename) + " " + str(e), file=sys.stderr)

    # remove plot+histo file
    try:
        os.remove(plot_file_name)
    except Exception as e:
        print("Error removing map image " + str(map_img_filename) + " " + str(e), file=sys.stderr)

    # return total  size in Mega bytes and location of zip file
    return total_size, full_zip_file_name
