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

import touchterrain.common
from touchterrain.common.grid_tesselate import grid      # my own grid class, creates a mesh from DEM raster
from touchterrain.common.Coordinate_system_conv import * # arc to meters conversion

import numpy
from PIL import Image

# for reading/writing geotiffs
# Later versions of gdal may be bundled into osgeo so check there as well.
try:
    import gdal
except ImportError as err:
    from osgeo import gdal

import time
import random
import os.path

# get root logger, will later be redirected into a logfile
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# CH test Aug 18: do EE init here only  
# this seems to prevent the file_cache is unavailable when using oauth2client >= 4.0.0 or google-auth
# crap from happening. It assumes that any "main" file imports TouchTerrainEarthEngine anyway.
# But, as this could als be run in a standalone scenario where EE should not be involved,
# the failed to EE init messages are just warnings 
try:
    import ee
    ee.Initialize() # uses .config/earthengine/credentials
except Exception as e:
    logging.warning("EE init() error (with .config/earthengine/credentials) " + str(e) + " (This is OK if you don't use earthengine anyway!)")
else:
    logging.info("EE init() worked with .config/earthengine/credentials")

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
DEM_sources = ["USGS/NED", 
               "USGS/GMTED2010", 
               "NOAA/NGDC/ETOPO1", 
               "USGS/SRTMGL1_003",
               "JAXA/ALOS/AW3D30/V2_2",
               "NRCan/CDEM",
               "USGS/GTOPO30",
               "CPOM/CryoSat2/ANTARCTICA_DEM",
               "MERIT/DEM/v1_0_3"
              ]


# Define default parameters
# Print settings that can be used to initialize the actual args
initial_args = {
    "DEM_name": 'USGS/NED',# DEM_name:    name of DEM source used in Google Earth Engine
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
    "CPU_cores_to_use" : 0,  # 0 means all cores, None (null in JSON!) => don't use multiprocessing
    "max_cells_for_memory_only" : 5000 * 5000, # if raster is bigger, use temp_files instead of memory
    "zip_file_name": "myterrain",   # base name of zipfile, .zip will be added
    # these are the args that could be given "manually" via the web UI
    "no_bottom": False, # omit bottom triangles?
    #"rot_degs": 0, # rotate by degrees ccw  # CH disabled for now
    "bottom_image": None,  # 1 band greyscale image used for bottom relief
    "ignore_leq": None, # set values <= this to NaN, so they are ignored
    "lower_leq": None,  # e.g. [0.0, 2.0] values <= 0.0 will be lowered by 2mm in the final model
    "unprojected": False, # don't project to UTM, only usefull when using GEE for DEM rasters
    "only": None,# list of tile index [x,y] with is the only tile to be processed. None means process all tiles (index is 1 based)
    "importedGPX": [], # list of gpx path file(s) to be use  
}


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

    # create a grid object containing cells, each cell has a top/bottom and maybe wall quad(s)
    # each quad is 2 triangles with 3 vertices
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


import kml2geojson # https://rawgit.com/araichev/kml2geojson/master/docs/_build/singlehtml/index.html
import defusedxml.minidom as md 
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
                return (coords_2d, None)
        
        # didn't find a Polygon, try again and look for a LineString
        for feature in features:
            #print(feature)
            geometry = feature["geometry"]
            #print(geometry)
            geom_type = geometry["type"]
            coords = geometry["coordinates"]
            if geom_type == "LineString":
                coords_2d = [[c3[0], c3[1]] for c3 in coords]
                return (coords_2d, "Warning: no Polygon found, used a (closed) Line instead") 
    
    # found neither polygon nor line
    return (None, "Error: no Polygon or LineString found, falling back to region box")

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
                         **otherargs):
    """
    args:
    - DEM_name:  name of DEM layer used in Google Earth Engine, see DEM_sources
    - trlat, trlon: lat/lon of top right corner of bounding box
    - bllat, bllon: lat/lon of bottom left corner of bounding box
    - polygon: optional geoJSON polygon
    - importedDEM: None (means: get the DEM from GEE) or local file name with DEM to be used instead
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
    - lower_leq: lower elevation values <= lower_leq[0] m by lower_leq[1] mm in final mesh, good for adding emphasis to coastlines. Unaffected by z_scale.
    - unprojected: don't apply UTM projection, can only work when exporting a Geotiff as the mesh export needs x/y in meters
    - only: 2-list with tile index starting at 1 (e.g. [1,2]), which is the only tile to be processed
    - original_query_string: the query string from the app, including map info. Put into log only. Good for making a URL that encodes the app view
    - no_normals: True -> all normals are 0,0,0, which speeds up processing. Most viewers will calculate normals themselves anyway
    - projection: EPSG number (as int) of projection to be used. Default (None) use the closest UTM zone
    - use_geo_coords: None, centered, UTM. not-None forces units to be in meters, centered will put 0/0 at model center for all tiles
                      not-None will interpret basethickness to be in multiples of 10 meters (0.5 mm => 5 m)    
    - importedGPX: None or List of GPX file paths that are to be plotted on the model
    - gpxPathHeight: Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon, therefore this is in meters. Negative numbers are ok and put a dent in the mdoel 
    - gpxPixelsBetweenPoints:  GPX Files can have a lot of points. This argument controls how many pixel distance there should be between points, effectively causing fewing lines to be drawn. A higher number will create more space between lines drawn on the model and can have the effect of making the paths look a bit cleaner at the expense of less precision 
    - gpxPathThickness: Stack paralell lines on either side of primary line to create thickness. A setting of 1 probably looks the best 
    - polyURL: Url to a KML file (with a polygon) as a publically read-able cloud file (Google Drive)
    - poly_file: local KML file to use as mask
    - map_image_filename: image with a map of the area
    
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
    assert not (bottom_image != None and basethick <= 0.5), "Error: base thickness (" + str(basethick) + ") must be > 0.5 mm when using a bottom relief image"

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

    #
    # get polygon data, either from GeoJSON or from kml URL or file
    #
    clip_poly_coords = None # list of lat/lons, will create ee.Feature used for clipping the terrain image 
    if polygon != None: 
        
        # If we have a GeoJSON and also a kml
        if polyURL != None and polyURL != '': 
            pr("Warning: polygon via Google Drive KML will be ignored b/c a GeoJSON polygon was also given!")
        elif poly_file != None and poly_file != '':
             pr("Warning: polygon via KML file will be ignored b/c a GeoJSON polygon was also given!")
        assert polygon.is_valid, "Error: GeoJSON polygon is not valid! (" + polygon + ")"
        clip_poly_coords = polygon["coordinates"][0] # ignore holes, which would be in 1,2, ...
        logging.info("Using GeoJSON polygon for masking with " + str(len(clip_poly_coords)) + " points")
        
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
        
    # overwrite trlat, trlon, bllat, bllon with bounding box around 
    if clip_poly_coords != None: 
        trlat, trlon, bllat, bllon = get_bounding_box(clip_poly_coords)

        # Hack: If we only have 5 points forming a rectangle just use the bounding box and forget about the polyon
        # Otherwise a rectangle digitized via gee ends up as a slightly sheared rectangle
        # This does assume a certain order, which seems to be the same for gee rectangles no matter how they are digitized:
        #[[-111.895752, 42.530947], p0
        # [-111.895752, 42.820084], p1
        # [-111.533203, 42.820084], p2
        # [-111.533203, 42.530947], p3
        # [-111.895752, 42.530947]]
        if len(clip_poly_coords) == 5: # 4 points + overlap with first
            cp = clip_poly_coords
            if cp[0][0] == cp[1][0] and cp[0][1] == cp[3][1]: # 0 matches with 1 and 3
                if cp[2][0] == cp[3][0] and cp[2][1] == cp[1][1]: # 2 also matches with 1 and 3
                    clip_poly_coords = None

    # end of polygon stuff



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
        image1 = ee.Image(DEM_name)
        info = image1.getInfo() # this can go wrong and return nothing for some sources, but we don't really need the info as long as we get the actual data

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
            'crs': epsg_str, # projection
 			# CH Mar 10, 2020: Do NOT specify the format anymore or getDownloadUrl() won't work!
 			# apparently it's only geotiffs now
        }

        # if cellsize is <= 0, just get whatever GEE's default cellsize is (printres = -1)
        if cell_size_m <= 0: del request_dict["scale"]

        # don't apply UTM projection, can only work for Geotiff export
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
        gdal_undef_val = band.GetNoDataValue()
        geo_transform = dem.GetGeoTransform()
        GEE_cell_size_m =  (geo_transform[1], geo_transform[5])

        # if we requested the true resolution of the source, use the cellsize of the gdal/GEE geotiff
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
            if gdal_undef_val != None:
                logger.debug("undefined GDAL value used by GEE geotiff: " + str(gdal_undef_val))

            # delete zip file and buffer from memory
            GEEZippedGeotiff.close()
            del zipdir, str_data

            # although STL can only use 32-bit floats, we need to use 64 bit floats
            # for calculations, otherwise we get non-manifold vertices!
            npim = band.ReadAsArray().astype(numpy.float64)
            #print npim, npim.shape, npim.dtype, numpy.nanmin(npim), numpy.nanmax(npim)
            min_elev = numpy.nanmin(npim)

            # Do a quick check if all the values are the same, which happens if we didn't get
            # any actual elevation data i.e. the area was not covered by the DEM
            if numpy.all(npim == npim[0,0]): # compare to first cell value
                s = "All(!) elevation values are " + str(npim[0,0]) + "! "
                s += "This may happen if the DEM source does not cover the selected area.\n"
                s += "For the web app, ensure that your red selection box is at least partially covered by the grey hillshade overlay "
                s += "or try using AW3D30 as DEM source."
                assert False, s # bail out

            # Add GPX points to the model (thanks KohlhardtC!)
            if importedGPX != None:
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
            if min_elev < -16384:
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
    # end of getting DEM data via GEE


    #
    # B) DEM data comes from a local raster file (geotiff, etc.)
    #
    # TODO: deal with clip polygon?   

    else:

        filename = os.path.basename(importedDEM)
        pr("Log for creating", num_tiles[0], "x", num_tiles[1], "3D model tile(s) from", filename, "\n")


        pr("started:", datetime.datetime.now().time().isoformat())
        dem = gdal.Open(importedDEM)
        band = dem.GetRasterBand(1)
        npim = band.ReadAsArray().astype(numpy.float64)

        # get the GDAL cell size in x (width), assumes cells are square!
        tf = dem.GetGeoTransform()  # In a north up image, padfTransform[1] is the pixel width, and padfTransform[5] is the pixel height. The upper left corner of the upper left pixel is at position (padfTransform[0],padfTransform[3]).
        pw,ph = abs(tf[1]), abs(tf[5])
        if pw != ph:
            logger.warning("Warning: raster cells are not square (" + str(pw) + "x" + str(ph) + ") , using" + str(pw))
        cell_size_m = pw
        pr("source raster upper left corner (x/y): ",tf[0], tf[3])
        pr("source raster cells size", cell_size_m, "m ", npim.shape)
        geo_transform = tf

        # I use PROJCS[ to get a projection name, e.g. PROJCS["NAD_1983_UTM_Zone_10N",GEOGCS[....
        # I'm grabbing the text between the first and second double-quote.
        utm_zone_str = dem.GetProjection()
        i = utm_zone_str.find('"')+1
        utm_zone_str = utm_zone_str[i:]
        i = utm_zone_str.find('"')
        utm_zone_str = utm_zone_str[:i]
        epsg_str = "N/A"
        pr("projection:", utm_zone_str)

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
                print3D_resolution_mm = source_print3D_resolution

        else: # yes, resample
            scale_factor = print3D_resolution_mm / float(source_print3D_resolution)
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

            if adjusted_print3D_resolution != print3D_resolution_mm:
                pr("after resampling, requested print res was adjusted from", print3D_resolution_mm, "to", adjusted_print3D_resolution, "to ensure correct model dimensions")
                print3D_resolution_mm = adjusted_print3D_resolution
            else:
                pr("print res is", print3D_resolution_mm, "mm")

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
        
        if lower_leq is not None:
            assert len(lower_leq) == 2, \
                "lower_leq should have the format [threshold, offset]. Got {}".format(lower_leq)
            #sf = (print3D_height_total_mm / 1000) / region_size_in_meters[1] # IdenC
            #offset = (lower_leq[1] / 1000) / sf
            
            threshold = lower_leq[0]
            offset = lower_leq[1] / 1000 * print3D_scale_number  # scale mm up to real world meters
            offset /= zscale # account for zscale
            
            # Instead of lowering, shift elevations greater than the threshold up to avoid negatives
            npim = numpy.where(npim > threshold, npim + offset, npim)
            pr("Lowering elevations <= ", threshold, " by ", offset, "m, equiv. to", lower_leq[1],  "mm at map scale")  

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
            "pixel_mm" : print3D_resolution_mm, # lateral (x/y) size of a 3D printed "pixel" in mm
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
            "geo_transform": geo_transform, # GeoTransform of geotiff
            "use_geo_coords": use_geo_coords, # create STL coords in UTM: None, "centered" or "UTM"
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


        # single core processing: just work on the list sequentially, don't use multi-core processing
        # if there's only one tile or one CPU or CPU_cores_to_use is still at default None
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

    # add png from Google Maps static 
    if map_img_filename != None:
        zip_file.write(map_img_filename, DEM_title + ".jpg")
        pr("added map of area as " + DEM_title + ".jpg")

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

    # remove map image
    if map_img_filename != None:
        try:
            os.remove(map_img_filename)
        except Exception as e:
            print("Error removing map image " + str(map_img_filename) + " " + str(e), file=sys.stderr)


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
    '''
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
    '''
    args = {"DEM_name": 'USGS/NED',# DEM_name:    name of DEM source used in Google Earth Engine
                                   # for all valid sources, see DEM_sources in TouchTerrainEarthEngine.py
            "trlat": 39.6849,        # lat/lon of top right corner
            "trlon": -104.6451,
            "bllat": 37.6447,        # lat/lon of bottom left corner
            "bllon": -106.6694,
            "importedDEM": None, # if not None, the raster file to use as DEM instead of using GEE (null in JSON)
            "printres": 0.4,  # resolution (horizontal) of 3D printer (= size of one pixel) in mm
            "ntilesx": 1,      # number of tiles in x and y
            "ntilesy": 1,
            "tilewidth": 160, # width of each tile in mm (<- !!!!!), tile height is calculated
            "basethick": 1, # thickness (in mm) of printed base
            "zscale": 2.0,      # elevation (vertical) scaling
            "fileformat": "STLb",  # format of 3D model files: "obj" wavefront obj (ascii),"STLa" ascii STL or "STLb" binary STL
            "tile_centered": False, # True-> all tiles are centered around 0/0, False, all tiles "fit together"
            "polyURL": "https://drive.google.com/file/d/1WIvprWYn-McJwRNFpnu0aK9RBU7ibUMw/view?usp=sharing"
            }   
    r = get_zipped_tiles(**args)
    zip_string = r[1] # r[1] is a zip folder as stringIO, r[0] is the size of the file in Mb
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
            bottom_elev = numpy.asarray(bimg).astype(numpy.float64)
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
            hole_elev = numpy.asarray(himg).astype(numpy.float64)
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
