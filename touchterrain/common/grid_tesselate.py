# grid_tesselate.py
# create triangles from a top and bottom np 2D array, including walls

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
# CH: May  2023: modified refactored optimized version (lower memory foot print) by keerl 
# CH: Apr. 2019: converted to Python 3
# CH: Feb. 2018: added use of tempfile as file buffer to lower memory footprint
# CH: Feb. 2017: added calculations for normals in stl files
# CH: Jan. 22, 16: putting the vert index behind a comment makes some programs crash
#                  when loading the obj file, so I removed those.
# FIX: (CH, Nov.16,15): make the vertex index a per grid attribute rather than
#  a vertex class attribute as this seem to index not found fail eventually when
#  multiple grids are processed together.
# CH July 2015

import numpy as np
import warnings # for muting warnings about nan in e.g. nanmean()
import struct # for making binary STL
import sys
import multiprocessing
import io
import os
import shutil   

# get root logger, will later be redirected into a logfile
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from touchterrain.common.vectors import Vector, Point  # local copy of vectors package which was no longer working in python 3
import touchterrain.common.utils as utils



# function to calculate the normal for a triangle
def get_normal(tri):
    "in: 3 verts, out normal (nx, ny,nz) with length 1"
    
    (v0, v1, v2) = tri
    p0 = Point.from_list(v0.get())
    p1 = Point.from_list(v1.get())
    p2 = Point.from_list(v2.get())
    a = Vector.from_points(p1, p0)
    b = Vector.from_points(p1, p2)
    #print p0,p1, p2
    #print a,b
    c = a.cross(b)
    #print c
    m = float(c.magnitude())
    if m == 0:
        normal = [0, 0, 0]
    else:
        normal = [c.x/m, c.y/m, c.z/m]
    return normal


class vertex:

    # dict of index value for each vertex
    # key is tuple of coordinates, value is a unique index
    vertex_index_dict = -1  

    def __init__(self, x,y,z):
        self.coords = tuple([float(d) for d in (x,y,z)])  # made this a tuple (zigzag won't work wth this anymore but it's not used anyway ...)
        vdict = vertex.vertex_index_dict # class attribute

        # for non obj file this is set to -1, and there's no need to deal with vertex indices
        if vdict != -1:
            # This creates a dict (a grid class attribute) with a tuple of the
            # 3 coords as key and a int as value. The int is a running index i.e. for each new
            # (not yet hashed) vertex this index just increases by 1, based on the current number of dict
            # entries. If a vertex has coords that already exist in the dict, nothing needs to be done.
            # This ensures that each index number is unique but can be shared by multiple indices
            # (e.g. when 2 triangles have vertices at exactly the same coords)
            # as it's easy to look up the index based on self.coords, a vertex does not actually 
            # have to store its index.

            # if we don't have an index value for these coords (as key)
            if self.coords not in vdict: # can't hash list
                vdict[self.coords] = len(vdict) # and set next running index as new value for key
                #print(self.coords, "now has idx", self.vert_idx) # DEBUG
            else: # this vertex has an idx in vdict
                #print(self.coords, "already has idx", vdict[tuple(self.coords)]) # DEBUG
                pass

    def get_id(self):
        '''return Id for my coords'''
        return vertex.vertex_index_dict[self.coords]

    def get(self):
        "returns [x,y,z] list of vertices"
        return self.coords

    def __str__(self):
        return "%.2f %.2f %.2f " % (self.coords[0], self.coords[1], self.coords[2])

    def __getitem__(self, index): 
        "enables use of index brackets for vertex objects: v[0] returns coords[0]"
        return self.coords[index]




class quad:
    """return list of 2 triangles (counterclockwise) per quad
       wall quads will NOT subdivide their quad into subquads if they are too skinny
       as this would require to re-index the entire mesh. However, I left the subdive
       stuff in in case we want to re-visit it later.
    """
    # class attribute, use quad.too_skinny_ratio
    too_skinny_ratio = 0.1 # border quads with a horizontal vs vertical ratio smaller than this will be subdivided

    # order is NE, NW, SW, SE
    # can be just a triangle, if it just any 3 ccw consecutive corners 
    def __init__(self, v0, v1, v2, v3=None): 
        self.vl = [v0, v1, v2, v3]
        self.subdivide_by = None # if not None, we need to subdivide the quad into that many subquads

    def get_copy(self):
        ''' returns a copy of the quad'''
        vl = self.vl[:]
        cp = quad(vl[0], vl[1], vl[2], vl[3])
        return cp

    def check_if_too_skinny(self, direction):
        '''if a border quad is too skinny it will to be subdivided into multiple quads'''
        #print direction, [str(v) for v in self.vl]

        # order of verts will be different for N,S vs E,W walls!
        if direction in ("S", "N"): # '-49.50 49.50 0.00 ', '-49.50 49.50 10.00 ', '-50.00 49.50 10.00 ', '-50.00 49.50 0.00 '
            horz_dist = abs(self.vl[0][0] - self.vl[2][0]) # x diff of v0 and v2
            max_elev = max(self.vl[1][2], self.vl[2][2]) # max elevation of v1 vs v2
            min_elev = min(self.vl[0][2], self.vl[3][2]) # min elevation v0 vs v3
            vert_dist = max_elev - min_elev # z diff of v0 and v1
        else: # -49.50 50.00 10.00 ', '-49.50 49.50 10.00 ', '-49.50 49.50 0.00 ', '-49.50 50.00 0.00 '
            horz_dist = abs(self.vl[0][1] - self.vl[1][1]) # y diff of v0 and v1
            max_elev = max(self.vl[0][2], self.vl[1][2]) # max elevation of v0 vs v1
            min_elev = min(self.vl[2][2], self.vl[3][2]) # min elevation v2 vs v3
            vert_dist = max_elev - min_elev # z diff of v0 and v1
        if vert_dist == 0: return # walls can be 0 height

        ratio = horz_dist / float (vert_dist)
        #print ratio, quad.too_skinny_ratio, quad.too_skinny_ratio / ratio
        if ratio < quad.too_skinny_ratio:
            sb = int(quad.too_skinny_ratio / ratio)
            self.subdivide_by = sb

    def get_triangles(self):
        "return list of 2 triangles (counterclockwise)"
        v0,v1,v2,v3 = self.vl[0],self.vl[1],self.vl[2],self.vl[3]
        t0 = (v0, v1, v2)  # verts of first triangle

        # if v3 is None, we only return t0
        if v3 != None:
            t1 = (v0, v2, v3)  # verts of second triangle
            return (t0,t1)
        else:
            return(t0, None)

    # this isn't used anymore 
    def get_triangles_with_indexed_verts(self):
        "return list of 2 triangles (counterclockwise) as vertex indices"

        vertidx = [] # list of the 4 verts as index
        for v in self.vl: # quad as list of 4 verts, each as (x,y,z)
            if v != None: # v3 could be None
                vi = v.get_id()
                vertidx.append(vi)
            #print v,vi

        t0 = (vertidx[0], vertidx[1], vertidx[2])  # verts of first triangle
        # if v3 is None(i.e. we didn't get a 4. index), we only return t0
        if len(vertidx) > 3:
            t1 = (vertidx[0], vertidx[2], vertidx[3])  # verts of second triangle
            return (t0,t1)
        else:
            return(t0, None)

    '''
    # splits skinny triangles
    def get_triangles(self, direction=None):
        """return list of 2 triangles (counterclockwise) per quad
           wall quads will subdivide their quad into subquads if they are too skinny
        """
        v0,v1,v2,v3 = self.vl[0],self.vl[1],self.vl[2],self.vl[3]

        # do we need to subdivide?
        if self.subdivide_by is None: # no, either not a wall or a chunky wall
            t0 = (v0, v1, v2)  # verts of first triangle
            t1 = (v0, v2, v3)  # verts of second triangle
            return (t0,t1)

        else:
            # subdivde into sub quads and return their triangles

            # order of verts will be different for N,S vs E,W walls!
            if direction in ("S", "N"): # '-49.50 49.50 0.00 ', '-49.50 49.50 10.00 ', '-50.00 49.50 10.00 ', '-50.00 49.50 0.00 '
                horz_dist = abs(self.vl[0][0] - self.vl[2][0]) # x diff of v0 and v2
                max_elev = max(self.vl[1][2], self.vl[2][2]) # max elevation of v1 vs v2
                min_elev = min(self.vl[0][2], self.vl[3][2]) # min elevation v0 vs v3
                vert_dist = max_elev - min_elev # z diff of v0 and v1
            else: # -49.50 50.00 10.00 ', '-49.50 49.50 10.00 ', '-49.50 49.50 0.00 ', '-49.50 50.00 0.00 '
                horz_dist = abs(self.vl[0][1] - self.vl[1][1]) # y diff of v0 and v1
                max_elev = max(self.vl[0][2], self.vl[1][2]) # max elevation of v0 vs v1
                min_elev = min(self.vl[2][2], self.vl[3][2]) # min elevation v2 vs v3
                vert_dist = max_elev - min_elev # z diff of v0 and v1



            tri_list = []

            # for finding the height of the sub quads I don't care about the different vert order
            z_list =[v[2] for v in self.vl]
            z_top = max(z_list) # z height of the top (take min() b/c one might be higher)
            z_bot = min(z_list) # z height at bottom
            z_dist = z_top - z_bot # distance to be

            #self.subdivide_by = 3 # DEBUG

            qheight = z_dist / float(self.subdivide_by) # height (elevation dist) of each quad
            height_list = [ z_top - qheight * i for i in range(self.subdivide_by+1) ] # list of h

            # make new subquads and return a list of their triangles
            vl_copy = copy.deepcopy(self.vl) # must make a deep copy, otherwise changing the subquads affect the current quad
            tl = [] # triangle list

            bottom_height_list = height_list[1:]
            for n,_ in enumerate(bottom_height_list):
                v0_,v1_,v2_,v3_ = vl_copy[0], vl_copy[1], vl_copy[2],vl_copy[3] # unroll copy
                #print n,v0_,v1_,v2_,v3_

                # as order of verts will be different for N,S vs E,W walls we need 2 different cases
                if direction in ("N", "S"):
                    top_inds = (1,2)
                    bot_inds = (0,3)
                else:
                    top_inds = (0,1)
                    bot_inds = (2,3)


                # top verts
                if n > 0: # don't change top z for topmost sub quad
                    h = height_list[n]
                    v= vl_copy[top_inds[0]] # first vertex of subquad
                    v.coords[2] = h         # set its z value
                    v= vl_copy[top_inds[1]]
                    v.coords[2] = h

                # bottom verts
                if n < len(bottom_height_list): # don't change bottom z for bottommost sub quad
                    h = height_list[n+1]
                    v = vl_copy[bot_inds[0]]
                    v.coords[2] = h
                    v = vl_copy[bot_inds[1]]
                    v.coords[2] = h

                # make a sub quad
                sq = copy.deepcopy(quad(vl_copy[0], vl_copy[1], vl_copy[2],vl_copy[3])) # each subquad needs to be its own copy
                #print n, sq,

                t0,t1 = sq.get_triangles()
                tl.append(t0)
                tl.append(t1)

            return tl
    '''

    def __str__(self):
        rs ="  "
        for n,v in enumerate(self.vl):
            rs = rs + "v" + str(n) + ": " + str(v) + "  "
        return rs


class cell:
    '''a cell with a top and bottom quad, constructor: uses refs and does NOT copy ...
       except for triangle cells
       '''
    def __init__(self, topquad, bottomquad, borders, is_tri_cell=False):
        self.topquad = topquad
        self.bottomquad = bottomquad
        self.borders = borders
        self.is_tri_cell = is_tri_cell

    def __str__(self):
        r = hex(id(self)) + "\n top:" + str(self.topquad) + "\n btm:" + str(self.bottomquad) + "\n borders:\n"
        for d in ["N", "S", "E", "W"]:
            if self.borders[d] != False:
                r = r + "  " + d + ": " + str(self.borders[d]) + "\n"
        return r

    def check_for_tri_cell(self):
        """Returns True if cell has borders on 2 consecutive sides False otherwise.
           Returns False is cell is already a tri-cell""" 
        if self.is_tri_cell == True: return None
        b = self.borders

        # Count borders (non-False will be a pointer to a wall quad, i.e. True is not used here!
        num_borders = 0
        for d in ["N", "S", "E", "W"]:
            if b[d] != False: num_borders += 1

        if num_borders == 2:
            if b["N"] != False and b["S"] != False: return False
            if b["E"] != False and b["W"] != False: return False
        else: 
            return False # cannot be triangelized

        #print("tricell:", num_borders, b)
        return True # 2 touching sides
    
    def convert_to_tri_cell(self):
        """Collapses the top and bottom quad into a triangle based on its 2 border walls,
        replaces one of the 2 border walls with a diagonal wall and the other with False.
        returns None, sets is_tri_cell to True"""
        if self.is_tri_cell == True: return None

        b = self.borders    
        tq =  self.topquad.get_copy()
        bq =  self.bottomquad.get_copy()     # NW SE SW NE
        tvl = tq.vl #                           0  1  2  3
        bvl = bq.vl # vertex order in quad is   0  3  2  1
        
        # Collapse the quad into a triangle depending on where the 2 borders are
        # In addition we need to get rid of one wall and overwrite the other
        # with a new diagonal wall 
        
        if b["N"] != False and b["W"] != False:
            self.topquad = quad(tvl[3], tvl[1], tvl[2], None) # ccw, order doesn't matter
            self.bottomquad = quad(bvl[1], bvl[2], bvl[3], None) # cw!
            b["N"] = quad(tvl[1], tvl[3], bvl[1], bvl[3]) # diagonal wall (ccw!)
            b["W"] = False # no used anymore
        elif b["N"] != False and b["E"] != False: 
            self.topquad = quad(tvl[0], tvl[1], tvl[2], None)
            self.bottomquad = quad(bvl[0], bvl[2], bvl[3], None) 
            b["N"] = quad(tvl[0], tvl[2], bvl[2], bvl[0])
            b["E"] = False 
        elif b["S"] != False and b["E"] != False: 
            self.topquad = quad(tvl[3], tvl[0], tvl[1], None)
            self.bottomquad = quad(bvl[3], bvl[0], bvl[1], None)
            b["S"] = quad(tvl[3], tvl[1], bvl[3], bvl[1])
            b["E"] = False
        elif b["S"]!= False and b["W"] != False: 
            self.topquad = quad(tvl[2], tvl[3], tvl[0], None)
            self.bottomquad = quad(bvl[0], bvl[1], bvl[2], None)
            b["S"] = quad(tvl[2], tvl[0], bvl[0], bvl[2])
            b["W"] = False
        else:
            print("convert_to_tri_cell() got invalid border config:", (self.borders), " - aborting")
            sys.exit() 
            
        self.is_tri_cell = True

        return None


'''
#profiling decorator
# https://medium.com/fintechexplained/advanced-python-learn-how-to-profile-python-code-1068055460f9
import cProfile
import functools
import pstats
import tempfile
def profile_me(func):
    @functools.wraps(func)
    def wraps(*args, **kwargs):
        print("profiling started")
        file = tempfile.mktemp()
        profiler = cProfile.Profile()
        profiler.runcall(func, *args, **kwargs)
        profiler.dump_stats(file)
        metrics = pstats.Stats(file)
        metrics.strip_dirs().sort_stats('time').print_stats(100)
    return wraps
'''





class grid:
    """makes cell data structure from two np arrays (top, bottom) of the same shape."""
    #@profile # https://pypi.org/project/memory-profiler/

    # I'm unclear why these class attributes need to be created here (added by keerl)
    top = None
    bottom = None
    tile_info = None
    xmaxidx = None
    ymaxidx = None
    cell_size = None
    offsetx = None
    offsety = None
    num_triangles = 0
    fo = None  
    

    def __init__(self, top, bottom, top_orig, tile_info):
        '''top: top elevation raster, must hang over by 1 row/column on each side (be already padded)
        bottom: None => bottom elevation is 0, otherwise either a 8 bit raster that will be resized to top's size or a bottom elevation raster
        top_orig: top elevation raster before top dilation
        tile_info: dict with info about the current tile + some tile global settings
        '''
        

        self.top = top
        self.bottom = bottom
        self.top_orig = top_orig
        self.throughwater = tile_info["throughwater"]    # Anson's all-the-way-through water case
        self.tile_info = tile_info


        if self.tile_info["fileformat"] == 'obj':
            vertex.vertex_index_dict = {} # will be filled with vertex indices

        self.cells = None # stores the cells in  a 2D array of cells

        # Important: in 2D np arrays, x and y coordinate are "flipped" in the sense that when printing top
        # top[0,0] appears to the upper left (NW) corner and [0,1] (East) of it:
        #[[11  12 13]       top[0,1] => 12
        # [Nan 22 23]       top[2,0] => NaN (Not a Number -> undefined elevation)
        # [31  32 33]       top[2,1] => 32
        # [41  42 43]]
        # Note: the actual array will be edge-padded which is important to be able to interpolate the border cells


        # DEBUG: normalized (0 - 1) xy coord increment per cell
        #y_norm_delta  = 1 / float(top.shape[0]) # y (north-south) direction
        #x_norm_delta  = 1 / float(top.shape[1]) # x (east-west) direction
        #print "normalized x/y delta:", x_norm_delta, y_norm_delta

        # cell size (x and y delta)
        self.cell_size = self.tile_info["pixel_mm"]

        # does top have NaNs?
        self.tile_info["have_nan"] = np.any(np.isnan(self.top)) # True => we have NaN values    
    
        # same for bottom, if we have one
        if self.tile_info["bottom_elevation"] is not None:
            self.tile_info["have_bot_nan"] = np.any(np.isnan(self.bottom))# True => we have NaN values, 

        # Jan 2019: no idea why, but sometimes changing top also changes the elevation
        # array of another tile in the tile list
        # for now I make a copy of all rasters and convert them to float
        self.top = self.top.copy().astype(np.float64) # writeable

        if self.bottom is not None:
            self.bottom = bottom.copy().astype(np.float64) # writeable

        if self.top_orig is not None:
            self.top_orig = top_orig.copy().astype(np.float64)


        #
        # Some sanity checks
        #

        # if bottom is not an ndarray, we don't have a bottom raster, so the bottom is a constant 0
        if isinstance(self.bottom, np.ndarray) == False:  
            self.bottom = 0
            self.tile_info["have_bottom_array"] = False
        # can't have a bottom_image and NaNs in top
        elif tile_info["bottom_image"] is not None and isinstance(self.bottom, np.ndarray) == True and self.tile_info["have_nan"] == True:  
            self.tile_info["have_bottom_array"] = False
            self.bottom = 0
            print("Top has NaN values, requested bottom image will be ignored!")
        # bottom is a elevation raster. It's ok to have NaNs in the bottom raster and/or top raster
        elif tile_info["bottom_elevation"] is not None and isinstance(self.bottom, np.ndarray) == True:
            self.tile_info["have_bottom_array"] = True

        # need to use the tilewide min/max for each tile, otherwise the boudaries don't line up perfectly! 

        if self.tile_info["bottom_elevation"] is not None: # we have a bottom raster
            
            '''

            # where top is actually lower than bottom (which can happen with Anson's data), set top to bottom
            self.top = np.where(self.top < self.bottom, self.bottom, self.top)
            
            #
            # Checking for all-the-way-through bottom NaNs and for top == bottom or bottom < top
            #

            # If the bottom has NaNs where top does not, set them to 0
            # This is very specific to Anson's way of creating all-the-way-through water
            # where his preprocessing sets the bottom to NaN for the water. (here called throughwater case)
            if self.tile_info["have_bot_nan"] == True:
                # CH1
                # bool array with True where self.bottom has NaN values but self.top does not
                nan_values = np.logical_and(np.isnan(self.bottom), np.logical_not(np.isnan(self.top)))
                if np.any(nan_values) == True: 
                    self.bottom[nan_values] = 0 # set bottom NaN values to 0 
                    self.throughwater = True # flag for easy checking


            # if both have the same value (or very close to) set both to Nan
            # No relative tolerance here as we don't care about this concept here. Set the abs. tolerance to 0.001 m (1 mm)
            close_values = np.isclose(self.top, self.bottom, rtol=0, atol=0.001, equal_nan=False) # bool array

            # for any True values in array, set corresponding top and bottom cells to NaN
            # Also set NaN flags
            if np.any(close_values) == True: 
                # save pre-dilated top for later dilation
                top_pre_dil = self.top.copy()  
                self.top[close_values] = np.nan   # set close values to NaN   

                # if diagonal cleanup is requested, we need to do it again after setting NaNs
                #clean_up_diags_check(self.top)

                # save original top after setting NaNs so we can skip the undilated NaN cells later
                self.top_orig = self.top.copy()  
                self.top = dilate_array(self.top, top_pre_dil) # dilate the NaN'd top with the original (pre NaN'd) top

                self.bottom[close_values] = np.nan # set close values to NaN 
                #clean_up_diags_check(self.bottom) # re-check for diags
                
                
                if self.throughwater == True:
                    self.bottom = dilate_array(self.bottom) # dilate with 3x3 nanmean #  
                else:
                    self.bottom = dilate_array(self.bottom, top_pre_dil) # dilate the NaN'd bottom with the original (pre NaN'd) top (same as original bottom)
                

                # as we may have changed the rasters, recalculate min elev (TODO: not sure if this is needed any more)
                self.tile_info["min_elev"] = np.nanmin(self.top)  
                self.tile_info["min_bot_elev"] = np.nanmin(self.bottom)  

                # check if we have NaNs in the top and/or bottom now (any() returns Bools)
                self.tile_info["have_nan"] = np.any(np.isnan(self.top))
                self.tile_info["have_bot_nan"] = np.any(np.isnan(self.bottom))

                # pre-dilated top is not needed anymore
                del top_pre_dil

        # if we have no bottom but have NaNs in top, make a copy and 3x3 dilate it. We'll still use the non-dilated top
        # when we need to skip NaN cells
        elif self.tile_info["have_nan"] == True:

            self.top_orig = self.top.copy()   # save original top before it gets dilated
            self.top = dilate_array(self.top) # dilate with 3x3 nanmean 
    
        # CH2
        '''
        #
        # Convert elevation from real word elevation (m) to model height (mm)
        # 
        if self.tile_info["use_geo_coords"] is None: # Coordinates need to be in mm 

            scz = 1 / self.tile_info["scale"] * 1000.0 # scale z to mm

            if self.tile_info["have_bottom_array"] == False:
                self.top -= self.tile_info["min_elev"] # subtract global min from top to get to 0 
                
            else:
                if self.throughwater == False:  # normal water case,  
                    self.top -= self.tile_info["min_bot_elev"] # subtract global bottom min 
                    self.bottom -= self.tile_info["min_bot_elev"]
                    self.bottom += self.tile_info["user_offset"] # add potential user offset from top (default: 0)
                    self.bottom *= scz * self.tile_info["z_scale"] # apply z-scale to bottom
                    self.bottom += self.tile_info["base_thickness_mm"] # add base thickness to bottom

                    # Update with per-tile mm min/max 
                    self.tile_info["min_bot_elev"] = np.nanmin(self.bottom) 
                    self.tile_info["max_bot_elev"] = np.nanmax(self.bottom)
                    print("bottom min/max (mm) for tile:", self.tile_info["min_bot_elev"], self.tile_info["max_bot_elev"])
                else: # throughwater case
                    self.top -= self.tile_info["min_elev"] 
                    # bottom was set to 0 earlier

            self.top += self.tile_info["user_offset"] # add potential user offset from top (default: 0)
            self.top *= scz * self.tile_info["z_scale"] # apply z-scale to top
            self.top += self.tile_info["base_thickness_mm"] # add base thickness to top

            # post-scale (i.e. in mm) top elevations (for this tile)
            self.tile_info["min_elev"] = np.nanmin(self.top)
            self.tile_info["max_elev"] = np.nanmax(self.top)
            print("top min/max for tile (mm):", self.tile_info["min_elev"], self.tile_info["max_elev"])

        else:  # using geo coords (UTM, meter based) - thickness is meters
            # TODO: Just noticed that we don't apply a z-scale to the top. Not sure if we should
            self.bottom = self.tile_info["min_elev"] - self.tile_info["base_thickness_mm"] * 10
            logger.info("Using geo coords with a base thickness of " + str(self.tile_info["base_thickness_mm"] * 10) + " meters")

        # max index in x and y for "inner" raster
        self.xmaxidx = self.top.shape[1]-2
        self.ymaxidx = self.top.shape[0]-2
        #print range(1, xmaxidx+1), range(1, ymaxidx+1)

        # offset so that 0/0 is the center of this tile (local) or so that 0/0 is the lower left corner of all tiles (global)
        if self.tile_info["tile_centered"] == False: # global offset, best for looking at all tiles together
            self.offsetx = -self.tile_info["tile_width"]  * (self.tile_info["tile_no_x"]-1)  # tile_no starts with 1! This is the top end of the tile, not 0!
            self.offsety = -self.tile_info["tile_height"] * (self.tile_info["tile_no_y"]-1)  + self.tile_info["tile_height"] * self.tile_info["ntilesy"]

        else: # local centered for printing
            self.offsetx = self.tile_info["tile_width"] / 2.0
            self.offsety = self.tile_info["tile_height"] / 2.0

        # geo coords are in meters (UTM). tile_centered is ignored for geo coords 
        if self.tile_info["use_geo_coords"] != None:

            geo_transform = self.tile_info["geo_transform"]
            self.cell_size = abs(geo_transform[1]) # rw pixel size of geotiff in m
            tile_width_m  = self.xmaxidx * self.cell_size # number of (unpadded) pixels of current tile
            tile_height_m = self.ymaxidx * self.cell_size

            # Place the tiles so that the center is at 0/0, which is what Blender GIS needs.
            if self.tile_info["use_geo_coords"] == "centered":

                self.offsetx = -tile_width_m  * (self.tile_info["tile_no_x"]-1)
                self.offsety = tile_height_m  * self.tile_info["ntilesy"] - tile_height_m * (self.tile_info["tile_no_y"]-1)

                # center by half the total size
                self.offsetx += (self.tile_info["full_raster_width"] * self.cell_size) / 2
                self.offsety -= (self.tile_info["full_raster_height"] * self.cell_size) / 2

                # correct for off-by-1 cells
                self.offsetx -= self.cell_size
                self.offsety += self.cell_size

            # size in meters but the UTM zone's origin is used, i.e. each vertex is in full
            # UTM coordinates. Not sure what CAD/modelling system uses that but if needed it's an option.
            else:  # "UTM"

                self.offsetx = -tile_width_m  * (self.tile_info["tile_no_x"]-1)
                self.offsety = -tile_height_m * (self.tile_info["tile_no_y"]-1)

                self.offsetx = -geo_transform[0] + self.offsetx # UTM x of upper left corner
                self.offsety =  geo_transform[3] + self.offsety # UTM y

        
        # put corner coordinates tile info dict (may later be needed for 2 bottom triangles)
        if self.tile_info["tile_centered"] == False:
            #print("tile width", self.tile_info["tile_width"])
            #print("tile_no_x", self.tile_info["tile_no_x"])
            #print("tile_no_y", self.tile_info["tile_no_y"])
            #print("tile_height", self.tile_info["tile_height"])
            #print("ntilesy", self.tile_info["ntilesy"])
            self.tile_info["W"] = self.tile_info["tile_width"]  * (self.tile_info["tile_no_x"]-1)  
            self.tile_info["E"] = self.tile_info["W"] + self.tile_info["tile_width"]
            tot_height = self.tile_info["tile_height"] * self.tile_info["ntilesy"]
            # y tiles index goes top(0) DOWN to bottom
            self.tile_info["N"] = tot_height - (self.tile_info["tile_height"] * (self.tile_info["tile_no_y"]-1))
            self.tile_info["S"] = self.tile_info["N"] - self.tile_info["tile_height"]
            #print("WENS", self.tile_info["W"] , self.tile_info["E"], self.tile_info["N"] ,self.tile_info["S"] )
        else:
            self.tile_info["W"] = -self.tile_info["tile_width"] / 2
            self.tile_info["E"] =  self.tile_info["tile_width"] / 2
            self.tile_info["S"] = -self.tile_info["tile_height"] / 2
            self.tile_info["N"] =  self.tile_info["tile_height"] / 2

    def clean_up_diags_check(self, ras):
        '''Local function to check for NaNs in the raster and clean up diagonal NaNs if requested'''
        if np.any(np.isnan(ras)) == True: # do we have any NaNs?
            if self.tile_info["clean_diags"] == True: # cleanup requested?
                ras = utils.clean_up_diags(ras)

    def create_cells(self):
        '''Creates a data structure for each raster cell based on quads for top, any walls and possible bottom.
        Once created, each cell is converted into triangles for each file format, which are stored as a stream buffer (self.s)
        If using temp files, this buffer serves as a cache for occasionally writing to disk (self.fo)
        Note that for obj, two streams/files are needed, one for indices that define the vertices for each triangle and one
        for vertex coordinates. Here, only the index part (s[1] and fo[1]) is stored, the vertex coordinates will be
        created and stored later based on the keys of the vertex class attribute vertex_index_dict'''
        
        # store cells in an array, init to None
        self.cells = np.empty([self.ymaxidx, self.xmaxidx], dtype=cell)

        # TODO: not sure we need this any more, given that this was done on the full raster
        # and after the operations that could have changed the raster 
        if self.tile_info["clean_diags"] == True:
            self.top = utils.fillHoles(self.top, 1, 8, True) # fill single holes
            self.top = utils.clean_up_diags(self.top)
            if self.top_orig is not None:
                self.top_orig = utils.clean_up_diags(self.top_orig)

        # report progress in %
        percent = 10
        pc_step = int(self.ymaxidx/percent) + 1
        progress = 0
        print("creating internal triangle data structure for", multiprocessing.current_process(), file=sys.stderr)

        for j in range(1, self.ymaxidx+1):# y dimension for looping within the +1 padded raster
            if j % pc_step == 0:
                progress += percent
                print(progress, "%", multiprocessing.current_process(), file=sys.stderr)

            for i in range(1, self.xmaxidx + 1):# x dim.
                #print("y=",j," x=",i, " elev=",top[j,i])

                # for throughwater we must use the pre-dilated, but for NaN'd top only use this check 
                # same for top with NaNs which have been 3x3 dilated
                # dirty_trianglescreates a technically better fit fit of the water into the terrain but will create triangles
                # that are collapsed into a line or a point. This should not be a problem for a modern slicer but will
                # lead to issues when using the model in a 3D mesh modeling program
                if self.tile_info["have_nan"] == True and self.tile_info["dirty_triangles"] == False: 
                    top = self.top_orig
                else:
                    top = self.top


                # if center elevation of current top cell is NaN, set its cell to None and skip the rest
                if self.tile_info["have_nan"] and np.isnan(top[j, i]):
                    self.cells[j-1, i-1] = None
                    continue
                
                # x/y coords of cell "walls", origin is upper left
                E = (i-1) * self.cell_size - self.offsetx # index -1 as it's ref'ing to top, not ptop
                W = E + self.cell_size  # CH Nov 2021: I think E and W are flipped (?) but I must correct for that later somewhere (?)
                N = -(j-1) * self.cell_size + self.offsety # y is flipped to negative
                S = N - self.cell_size
                #print(i,j, " ", E,W, " ",  N,S, " ", top[j,i])
                
                ## Which directions will need to have a wall?
                # True means: we have an adjacent cell and need a wall in that direction
                borders =   dict([[drct, False] for drct in ["N", "S", "E", "W"]]) # init with no walls                   
                
                # set walls for fringe cells
                if j == 1             : borders["N"] = True
                if j == self.ymaxidx  : borders["S"] = True
                if i == 1             : borders["W"] = True
                if i == self.xmaxidx  : borders["E"] = True

                
                def interpolate_with_NaN(elev, i, j):
                    '''Get elevation of 4 corners of current cell and return them as NEelev, NWelev, SEelev, SWelev
                    If any of the corners is NaN, return None for all 4 corners'''

                    # interpolate each corner with possible NaNs, using mean()
                    # Note: if we have 1 or more NaNs, we get a warning: warnings.warn("Mean of empty slice", RuntimeWarning)
                    # but if the result of ANY corner is NaN (b/c it used 4 NaNs), skip this cell entirely by setting it to None instead a cell object
                    with warnings.catch_warnings():
                        warnings.filterwarnings('error')
                        NEar = np.array([elev[j+0,i+0], elev[j-1,i-0], elev[j-1,i+1], elev[j-0,i+1]]).astype(np.float64)
                        NWar = np.array([elev[j+0,i+0], elev[j+0,i-1], elev[j-1,i-1], elev[j-1,i+0]]).astype(np.float64)
                        SEar = np.array([elev[j+0,i+0], elev[j-0,i+1], elev[j+1,i+1], elev[j+1,i+0]]).astype(np.float64)
                        SWar = np.array([elev[j+0,i+0], elev[j+1,i+0], elev[j+1,i-1], elev[j+0,i-1]]).astype(np.float64)
            
                        try: 
                            # init all elevs with NaN
                            NEelev = NWelev = SEelev = SWelev = np.nan

                            # nanmean() is expensive, so only use it when actually needed
                            NEelev = np.nanmean(NEar) if np.isnan(np.sum(NEar)) else (elev[j+0,i+0] + elev[j-1,i-0] + elev[j-1,i+1] + elev[j-0,i+1]) / 4.0  
                            NWelev = np.nanmean(NWar) if np.isnan(np.sum(NWar)) else (elev[j+0,i+0] + elev[j+0,i-1] + elev[j-1,i-1] + elev[j-1,i+0]) / 4.0
                            SEelev = np.nanmean(SEar) if np.isnan(np.sum(SEar)) else (elev[j+0,i+0] + elev[j-0,i+1] + elev[j+1,i+1] + elev[j+1,i+0]) / 4.0
                            SWelev = np.nanmean(SWar) if np.isnan(np.sum(SWar)) else (elev[j+0,i+0] + elev[j+1,i+0] + elev[j+1,i-1] + elev[j+0,i-1]) / 4.0

                        except RuntimeWarning: #  corner is surrounded by NaN elevations - skip this cell
                            #print(j-1, i-1, ": elevation of at least one corner of this cell is NaN - skipping cell")
                            #print " NW",NWelev," NE", NEelev, " SE", SEelev, " SW", SWelev # DEBUG
                            num_nans = sum(np.isnan(np.array([NEelev, NWelev, SEelev, SWelev]))) # is ANY of the corners NaN?
                            if num_nans > 0: # yes, set cell to None and skip it ...
                                self.cells[j-1, i-1] = None
                                return None, None, None, None
                        else:
                            
                            '''
                            print("\n", i,j)
                            print("NE", elev[j+0,i+0], elev[j-1,i-0], elev[j-1,i+1], elev[j-0,i+1], NEelev)
                            print("NW", elev[j+0,i+0], elev[j+0,i-1], elev[j-1,i-1], elev[j-1,i+0], NWelev)
                            print("SE", elev[j+0,i+0], elev[j-0,i+1], elev[j+1,i+1], elev[j+1,i+0], SEelev)
                            print("SW", elev[j+0,i+0], elev[j+1,i+0], elev[j+1,i-1], elev[j+0,i-1], SWelev)
                            '''
                            return NEelev, NWelev, SEelev, SWelev    


                if not self.tile_info["have_nan"]:
                    # non NaNs: interpolate elevation of four corners (array order is top[y,x]!)
                    NEelev = (self.top[j+0,i+0] + self.top[j-1,i-0] + self.top[j-1,i+1] + self.top[j-0,i+1]) / 4.0
                    NWelev = (self.top[j+0,i+0] + self.top[j+0,i-1] + self.top[j-1,i-1] + self.top[j-1,i+0]) / 4.0
                    SEelev = (self.top[j+0,i+0] + self.top[j-0,i+1] + self.top[j+1,i+1] + self.top[j+1,i+0]) / 4.0
                    SWelev = (self.top[j+0,i+0] + self.top[j+1,i+0] + self.top[j+1,i-1] + self.top[j+0,i-1]) / 4.0
                    '''
                    print("\n", i,j)
                    print("NE",self.top[j+0,i+0],self.top[j-1,i-0],self.top[j-1,i+1],self.top[j-0,i+1], NEelev)
                    print("NW",self.top[j+0,i+0],self.top[j+0,i-1],self.top[j-1,i-1],self.top[j-1,i+0], NWelev)
                    print("SE",self.top[j+0,i+0],self.top[j-0,i+1],self.top[j+1,i+1],self.top[j+1,i+0], SEelev)
                    print("SW",self.top[j+0,i+0],self.top[j+1,i+0],self.top[j+1,i-1],self.top[j+0,i-1], SWelev)
                    '''
                else:
                    # NaNs: set borders to True if we have any NaNs in any of the adjacent cells
                    # Do this only for top as we assume that any bottom raster NaNs are the same as on top

                    # get values for current cell i, j, NEelev, NWelev, SEelev, SWelev
                    NEelev, NWelev, SEelev, SWelev = interpolate_with_NaN(self.top, i, j)
                    if NEelev is None: # if any of the corners is NaN, we have set the cell to None and can skip it
                        continue 
                    
                    # for the through water case or Top NaN, base the walls on the original (non-dilated) top
                    if self.tile_info["have_nan"] == True: 
                        top = self.top_orig
                    else:
                        top = self.top

                    with warnings.catch_warnings():
                        warnings.filterwarnings('error')
                        try:
                            if np.isnan(top[j-1,i]): borders["N"] = True
                            if np.isnan(top[j+1,i]): borders["S"] = True
                            if np.isnan(top[j,i-1]): borders["W"] = True
                            if np.isnan(top[j,i+1]): borders["E"] = True
                        except RuntimeWarning:
                            pass # nothing wrong - just here to ignore the warning
                    

                #
                # Make top and bottom quads and wall. Note that here we flip x and y coordinate axis to the system 
                # used in 3D graphics
                #

                # make top quad (x,y,z)    vi is the vertex index dict of the grids
                NEt = vertex(E, N, NWelev)  # yes, NEt gets the z of NWelev, has to do with coordinate system change
                NWt = vertex(W, N, NEelev)
                SEt = vertex(E, S, SWelev)
                SWt = vertex(W, S, SEelev)
                # a certain vertex order is needed to make the 2 triangles be counter clockwise and so point outwards
                topq = quad(NEt, SEt, SWt, NWt) 
                #print(i, j, topq)
                

                #
                # make bottom quad  
                #

                # get corner for bottom array
                if self.tile_info["have_bottom_array"] == True:

                    # for the through water case, simply set the bottom to 0
                    if self.throughwater == True:
                        NEelev = NWelev = SEelev = SWelev = 0
                    else:
                        # simple interpolation
                        if not self.tile_info["have_bot_nan"]:
                            NEelev = (self.bottom[j+0,i+0] + self.bottom[j-1,i-0] + self.bottom[j-1,i+1] + self.bottom[j-0,i+1]) / 4.0
                            NWelev = (self.bottom[j+0,i+0] + self.bottom[j+0,i-1] + self.bottom[j-1,i-1] + self.bottom[j-1,i+0]) / 4.0
                            SEelev = (self.bottom[j+0,i+0] + self.bottom[j-0,i+1] + self.bottom[j+1,i+1] + self.bottom[j+1,i+0]) / 4.0
                            SWelev = (self.bottom[j+0,i+0] + self.bottom[j+1,i+0] + self.bottom[j+1,i-1] + self.bottom[j+0,i-1]) / 4.0
                        else:
                            # Nan aware interpolation 
                            NEelev, NWelev, SEelev, SWelev = interpolate_with_NaN(self.bottom, i, j)
                            if NEelev is None: # if any of the corners is NaN, we have set the cell to None and are skippping it
                                continue # skip this cell
                else:
                    NEelev = NWelev = SEelev = SWelev = self.bottom # otherwise use the constant bottom elevation value

                # from whatever bottom values we have now, make the bottom quad
                # (if we do the 2 tri bottom, these will end up not be used for the bottom but they may be used for any walls ...)
                NEb = vertex(E, N, NWelev)
                NWb = vertex(W, N, NEelev)
                SEb = vertex(E, S, SWelev)
                SWb = vertex(W, S, SEelev)
                botq = quad(NEb, NWb, SWb, SEb)

                #print(topq)
                #print(botq)
                 
                # Quads for walls: in borders dict, replace any True with a quad of that wall
                if borders["N"] == True: borders["N"] = quad(NEb, NEt, NWt, NWb)
                if borders["S"] == True: borders["S"] = quad(SWb, SWt, SEt, SEb)
                if borders["E"] == True: borders["E"] = quad(NWt, SWt, SWb, NWb)
                if borders["W"] == True: borders["W"] = quad(SEt, NEt, NEb, SEb)

                # Make cell
                if self.tile_info["no_bottom"] == True:
                    c = cell(topq, None, borders) # omit bottom - do not fill with 2 tris later (may have NaNs)
                else:
                    if self.tile_info["have_nan"] == True or self.tile_info["have_bottom_array"] == True: 
                        # for through water case make sure this in not one of the dilated cells

                        c = cell(topq, botq, borders) # full cell: top quad, bottom quad and wall quads
                    else:
                        c = cell(topq, None, borders) # omit bottom, will fill with 2 tris later

                # DEBUG: store i,j, and central elev
                #c.iy = j-1
                #c.ix = i-1
                #c.central_elev = top[j-1,i-1]

                # if we have nan cells, do some postprocessing on this cell to get rid of stair case patterns
                # This will create special triangle cells that have a triangle of any orientation at top/bottom, which 
                # are flagged as is_tri_cell = True, and have only v0, v1 and v2. One border is deleted, the other
                # is set as a diagonal wall.
                # Note: this will not be done if we have a bottom as it will lead to lots of triangle holes! 
                if self.tile_info["have_nan"] == True and self.tile_info["smooth_borders"] == True and self.tile_info["have_bottom_array"] == False:
                    #print(i,j, c.borders)
                    if c.check_for_tri_cell():
                        c.convert_to_tri_cell()  # collapses top and bot quads into a triangle quad and make diagonal wall
                
                #
                # Make quads for top, bottom and walls
                #
                no_bottom = self.tile_info["no_bottom"]
                # list of quads for this cell,
                if no_bottom == False and (self.tile_info["have_nan"] or self.tile_info["have_bottom_array"]): #  
                    quads = [c.topquad, c.bottomquad]
                else:
                    quads = [c.topquad] # no bottom quads, only top

                # add border quads if we have any (False means no border quad) 
                for k in c.borders:  # k is N, S, E, W
                    if c.borders[k] is not False: quads.append(c.borders[k])
                
                # write the triangles of this quad to buffer
                for q in quads:
                    t0, t1 = q.get_triangles() # tri vertices

                    # for STL this will write triangles (vertices) but for obj this will
                    # write indices into s[1]/fo[1] (indices), vertices have to written based on these later 
                    self.write_triangle_to_buffer(t0)
                    self.write_triangle_to_buffer(t1) # could be empty ...        
        
        print("100%", multiprocessing.current_process(), "\n", file=sys.stderr)
    
    def write_triangle_to_buffer(self, t):
        '''write triangle vertices for triangle t to stream buffer self.s for caching.
        Once the cache is full, is is writting to disk (self.fo)'''
        
        if t is None: return # just for the case that one of the two triangle was removed by smoothing
        
        #print(self.num_triangles, end=", ")
        self.num_triangles += 1

        # Create triangle coords list, for STL including normal coords (no normals for obj)
        if self.tile_info["fileformat"] != "obj":
            tl = get_normal(t) if self.tile_info["no_normals"] == False else [0,0,0]
            for v in t:
                coords = v.get() # get() => list of coords [x,y,z]
                tl.extend(coords) # like append() but extend() unpacks that list!
            tl.append(0) # append attribute byte 0

        if self.tile_info["fileformat"] == "STLb":
            # en.wikipedia.org/wiki/STL_%28file_format%29#Binary_STL
            BINARY_FACET = "12fH" # 12 32-bit floating-point numbers + 2-byte ("short") unsigned integer ("attribute byte count" -> use 0)
            self.s.write(struct.pack(BINARY_FACET, *tl)) # append to s

        elif self.tile_info["fileformat"] == "STLa":
            ASCII_FACET ="""facet normal {face[0]:f} {face[1]:f} {face[2]:f}\nouter loop\nvertex {face[3]:f} {face[4]:f} {face[5]:f}\nvertex {face[6]:f} {face[7]:f} {face[8]:f}\nvertex {face[9]:f} {face[10]:f} {face[11]:f}\nendloop\nendfacet\n"""
            self.s.write(ASCII_FACET.format(face=tl))

        elif self.tile_info["fileformat"] == "obj":
            # add facet indices to index stream buffer
            vl = [v.get_id() + 1 for v in t] # vertex list +1 b/c obj indices start at 1
            self.s[1].write(f"f {vl[0]}, {vl[1]}, {vl[2]}\n") 

        # for STL maybe write to temp file. This can't work for obj b/c we need the full list 
        # of tri indices first. Once we have that, we can create a buffer/tempfile
        if self.tile_info["fileformat"] != "obj":  
            self.write_buffer_to_file()
            
    def write_buffer_to_file(self, flush=False, chunk_size=100000):
        # write buffer to file every 10k triangles
        # chunksize is the number of triangles that need to have been collected into the buffer in order to actually write to disk. (cache)
        # flusk=True forces a write: use this to flush whatever is in the buffer.  Will NOT close the file!
        # for obj, write only the indices [1], vertices [0] will be done later
        
        # Only write to file if we're actually using temp files, otherwise just bail out
        if self.tile_info.get("temp_file") is None:
            return
        
        if self.num_triangles % chunk_size == 0  or flush == True:
            if self.tile_info["fileformat"] == "STLb":
                self.fo.write(self.s.getbuffer())   # append (partial) binary buffer to file
                self.s.close()
                self.s = io.BytesIO()
            elif self.tile_info["fileformat"] == "STLa":
                self.fo.write(self.s.getvalue())   # append (partial) text buffer to file
                self.s.close()
                self.s = io.StringIO()
            elif self.tile_info["fileformat"] == "obj":
                self.fo[1].write(self.s[1].getvalue())
                self.s[1].close()
                self.s[1] = io.StringIO()

        if flush == True:
            # close buffers (needed?)
            if self.tile_info["fileformat"] == "obj":
                self.s[1].close()
            else: # STLb and STLa
                self.s.close()
    
    
    '''
    def create_zigzag_borders(self, num_cells_per_zig = 100, zig_dist_mm = 0.15, zig_undershoot_mm = 0.05):
        """ post process the border quads so that it follows a zig-zag pattern """

        assert num_cells_per_zig > 1, "create_zigzag_borders() error: num_cells_per_zig =" + str(num_cells_per_zig)

        # number of cells in x and y     grid is cells[y,x]
        ncells_x = self.cells.shape[1]
        ncells_y = self.cells.shape[0]

        ncpz = num_cells_per_zig

        # north and south border
        ncells = ncells_x

        # figure out how many full and partial zigs we need
        num_full_zigs = ncells // ncpz
        num_leftover_cells = ncells % ncpz

        offset = -abs(zig_undershoot_mm) # in mm

        # very first full zig
        rise_first_full = 1 / float(ncpz-1)

        # full width zig, after the very first
        rise_full = (1 + abs(offset)) / float(ncpz-1)

        # partial zig, made from leftovers
        rise_partial = 0 # 0 means no partials
        if num_leftover_cells > 1:
            rise_partial = (1 + abs(offset)) / float(num_leftover_cells-1)


        #print ncells, ncpz, num_full_zigs, num_leftover_cells, rise_full, brief_text

        # As I have to do 4 passes, I'm wrapping the calculation of the zig "height" into a local function
        def getzigvalue(ci, zig_dist_mm, ncells, ncpz, num_full_zigs, num_leftover_cells, rise_full, rise_partial):
            c_in_zig = ci % ncpz
            #print ncpz, ci, c_in_zig

            # very first zig has to start at 0, not offset
            if ci <= c_in_zig:

                yl = rise_first_full * c_in_zig + 0
                if c_in_zig < ncpz-1:
                    yr = rise_first_full * (c_in_zig+1)
                else:
                    yr = offset # done with first zig, go to offset

            # subsequent zigs, full or partial
            else:

                # full or partial zig
                if ncells - ci > num_leftover_cells:

                    # full cell, go to offset
                    yl = rise_full * c_in_zig + offset
                    if c_in_zig < ncpz-1:
                        yr = rise_full * (c_in_zig+1) + offset
                    else:
                        yr = offset
                else: # partial
                    yl = rise_partial * c_in_zig + offset
                    if c_in_zig < ncpz-1:
                        yr = rise_partial * (c_in_zig+1) + offset
                    else:
                        yr = offset

            # very last cell must set yr as 0
            if ci == ncells-1:
                yr = 0

            #print ci, c_in_zig, yl, yr
            return yl * zig_dist_mm, yr * zig_dist_mm

        # North  and south border
        for ci in range(0, ncells_x):
            yl,yr = getzigvalue(ci,zig_dist_mm, ncells_x, ncpz, num_full_zigs, num_leftover_cells, rise_full, rise_partial)

            # get vertex lists for the 2 quads for the north cell
            nrthcell = self.cells[0,ci]
            topverts = nrthcell.topquad.vl
            botverts = nrthcell.bottomquad.vl

            # note that the vertex order in top or bottom quads are different b/c top has normals up, bottom has normals down

            # order: NEb, NWb, SWb, SEb
            botverts[0].coords[1] += yl  # move y coord up a bit
            botverts[1].coords[1] += yr

            # order: NEt, SEt, SWt, NWt
            topverts[0].coords[1] += yl
            topverts[3].coords[1] += yr



            # get vertex lists for the 2 quads for the south cell
            sthcell = self.cells[-1,ci]
            topverts = sthcell.topquad.vl
            botverts = sthcell.bottomquad.vl


            # order: NEb, NWb, SWb, SEb
            botverts[2].coords[1] += yr  # WTH???? why yr?
            botverts[3].coords[1] += yl

            # order: NEt, SEt, SWt, NWt
            topverts[1].coords[1] += yl
            topverts[2].coords[1] += yr


        # West and east border
        for ci in range(0, ncells_y):
            yl,yr = getzigvalue(ci, zig_dist_mm, ncells_x, ncpz, num_full_zigs, num_leftover_cells, rise_full, rise_partial)


            wcell = self.cells[ci,0]
            topverts = wcell.topquad.vl
            botverts = wcell.bottomquad.vl


            # WTH? why east here?

            # order: NEb, NWb, SWb, SEb
            botverts[0].coords[0] -= yl
            botverts[3].coords[0] -= yr

            # order: NEt, SEt, SWt, NWt
            topverts[0].coords[0] -= yl
            topverts[1].coords[0] -= yr

            # East border
            wcell = self.cells[ci,-1]
            topverts = wcell.topquad.vl
            botverts = wcell.bottomquad.vl


            # WTH? why west here?

            # order: NEb, NWb, SWb, SEb
            botverts[1].coords[0] -= yl
            botverts[2].coords[0] -= yr

            # order: NEt, SEt, SWt, NWt
            topverts[3].coords[0] -= yl
            topverts[2].coords[0] -= yr


    # version that splits skinny triangles - didn't turn out to be a problem but maybe useful later
    def make_STLfile_buffer(self, ascii=False, no_bottom=False, temp_file=None):
        """returns buffer of ASCII or binary STL file from a list of triangles, each triangle must have 9 floats (3 verts, each xyz)
            if no_bottom is True, bottom triangles are omitted
            if temp_file is not None, write STL into it (instead of a buffer) and return it
        """
        # Example: list of 2 triangles
        #[
        # [ 1.0,  1.0,  1.0, # vertex1 xyz
        #  -1.0,  1.0, -1.0, # vertex2 xyz
        #  -1.0, -1.0,  1.0] # vertex3 xyz
        # [ 1.0,  1.0,  1.0,
        #  -1.0, -1.0,  1.0,
        #   1.0, -1.0, -1.0]
        #]
        # Normal for each facet is set to 0,0,0

        triangles = [] # list of triangles

        # number of cells in x and y     grid is cells[y,x]
        ncells_x = self.cells.shape[1]
        ncells_y = self.cells.shape[0]

        # go through all cells, get all its quads and split into triangles
        for ix in range(0, ncells_x):
          for iy in range(0, ncells_y):
            cell = self.cells[iy,ix] # get cell from 2D array of cells (grid)

            if cell != None:
                #print "cell", ix, iy

                # list of top/bottom quads for this cell,
                if no_bottom == False:
                    quads = [cell.topquad, cell.bottomquad]
                else:
                    quads = [cell.topquad] # no bottom quads, only top

                # get tris for top and bottom
                for q in quads:
                    tl = q.get_triangles() # triangle list
                    triangles.append(tl[0])
                    triangles.append(tl[1])

                # add tris for border quads     cell.borders is a dict with S E W N as keys and a quad as value (if there's a border in that direction, False, otherwise)
                for k in cell.borders.keys():
                    border_quad = cell.borders[k]
                    if  border_quad != False:
                        #print k,
                        # run a check if wall is too skinny, this will set an quad internal value for how much to subdivide
                        # the subdivision will happen later when we ask for the skinny wall's triangles
                        # we need the direction (k) b/c the order of verts is different for n/s vs e/w!
                        border_quad.check_if_too_skinny(k)
                        #print border_quad, border_quad.subdivide_by
                        tl = border_quad.get_triangles(k) # triangle list
                        for t in tl:
                            triangles.append(t)

        #for n,t in enumerate(triangles): print n, t[0], t[1], t[2]

        buf = None
        if ascii:
            buf_as_list = self._build_ascii_stl(triangles)
            buf = "\n".join(buf_as_list).encode("UTF-8") # single utf8 string
        else:
            buf_as_list = self._build_binary_stl(triangles)
            buf = b"".join(buf_as_list)  # single "binary string"/buffer

        #print len(buf)

        if temp_file ==  None: return buf

        # Write string into temp file and return it
        temp_file.write(buf)
        return temp_file
    '''
    # Convert grid into a file or memory buffer containing triangles (plus indices for obj)
    def make_file_buffer(self):
        
        # check that we have a valid triangle file format
        if self.tile_info["fileformat"] not in ["obj", "STLa", "STLb"]:
            raise ValueError(f"Invalid file format: {self.tile_info['fileformat']}. Supported formats are 'obj', 'STLa', and 'STLb'")

        # get file name for temp file (or None if using memory)
        if self.tile_info.get("temp_file") != None:  # contains None or a file name.
            temp_file = self.tile_info["temp_file"]
        else:
            temp_file = None # means: use memory

        # Open in-memory stream buffers s 
        # s is used to collect the data that is eventually written into a proper file
        if self.tile_info["fileformat"] == "STLb":
            self.s = io.BytesIO()
            mode = "ab"  # for using open() later
        elif self.tile_info["fileformat"] == "STLa":
            self.s = io.StringIO() 
            mode = "a"
        elif self.tile_info["fileformat"] == "obj":
            mode = "a"   
            # 2 buffers: vertices and indices
            self.s = [io.StringIO(), io.StringIO()]

        # open temp file for appending, file object self.fo will be used in create_cells()
        if temp_file != None:
            if self.tile_info["fileformat"] == "STLa" or self.tile_info["fileformat"] == "STLb":
                try:
                    self.fo = open(temp_file, mode)
                except Exception as e:
                    print("Error opening:", temp_file, e, file=sys.stderr)
                    return e
            elif self.tile_info["fileformat"] == "obj":
                # for obj we need 2  temp files and file objects, so s and fo are now lists
                try:
                    vertsfo =  open(temp_file, mode)
                except Exception as e:
                    print("Error opening:", temp_file, e, file=sys.stderr)
                    return e
                idx_temp_file = temp_file + ".idx" # index temp file just has .idx at the end

                try:
                    idxfo = open(idx_temp_file, mode)
                except Exception as e:
                    print("Error opening:", idx_temp_file, e, file=sys.stderr)
                    return e
                self.fo = [vertsfo, idxfo]

        # header for STLa and obj
        # (STLb header can only pre-pended later)
        if self.tile_info["fileformat"] == "STLa":
            self.s.write('solid digital_elevation_model\n') # digital_elevation_model is the name of the model
        elif self.tile_info["fileformat"] == "obj":
            self.s[0].write("g vert\n")
            self.s[1].write("g tris\n")

        # populate self.cells, will write triangles into buffer/file
        self.create_cells()

        # Can we use 2-triangle bottoms?
        add_simple_bottom = True # True by default, set to False if we can't create a 2-triangle bottom
        
        # We don't have bottom tris but that's OK as we don't them anyway (no_bottom option was set)
        if self.tile_info["no_bottom"] == True: add_simple_bottom = False # 
        
        # With a NaN (masked) top array, we already have the corresponding full bottom
        if self.tile_info["have_nan"] == True: add_simple_bottom = False 
        
        # with a bottom image/elevation, we also already need a full bottom
        if self.tile_info["bottom_image"] != None or self.tile_info["bottom_elevation"] != None: 
            add_simple_bottom = False

        # obj files currently don't support simple bottoms
        #if self.tile_info["fileformat"] == 'obj': add_simple_bottom = False

        # For simple bottom, add 2 triangles based on the corners of the tile
        if add_simple_bottom:
            v0 = vertex(self.tile_info["W"], self.tile_info["S"], 0)
            v1 = vertex(self.tile_info["E"], self.tile_info["S"], 0)
            v2 = vertex(self.tile_info["E"], self.tile_info["N"], 0)
            v3 = vertex(self.tile_info["W"], self.tile_info["N"], 0)

            t0 = (v0, v2, v1) #A
            t1 = (v0, v3, v2) #B

            self.write_triangle_to_buffer(t0) #
            self.write_triangle_to_buffer(t1)

        # using buffer 
        if temp_file is None: 
        
            # finish STLa stream buffer
            if self.tile_info["fileformat"] == "STLa":
                self.s.write('endsolid digital_elevation_model') # append end clause
                buf = self.s.getvalue()

            # For STLb buffer, prepend the header
            if self.tile_info["fileformat"] == "STLb":
                BINARY_HEADER = "80sI" # up to 80 chars do NOT start with the word solid + number of faces as UINT32
                stlb_header = io.BytesIO()
                stlb_header.write(struct.pack(BINARY_HEADER, b'Binary STL Writer', self.num_triangles))
                stlb_header.write(self.s.getbuffer()) # append body to header
                del self.s # no longer needed
                buf = stlb_header.getvalue()  # CH 5/2025 changed from getbuffer to not return a memory object that c an't be pickled  

            # fill s[0] and append s[1]
            elif self.tile_info["fileformat"] == "obj":
                # fill s[0] with all vertices used (keys of vertex class attribute dict)
                print("Appending obj triangle indices\n", file=sys.stderr)
                for vc in vertex.vertex_index_dict:
                    self.s[0].write(f"v {vc[0]}, {vc[1]}, {vc[2]}\n")
                
                self.s[0].write(self.s[1].getvalue()) # append indices
                del self.s[1]
                buf = self.s[0].getvalue()

            return buf
        
        # using temp file
        else:
            self.write_buffer_to_file(flush=True) # write leftover buffer to file, will NOT close fo!

            # STLa: append last line
            if self.tile_info["fileformat"] == "STLa":
                self.fo.write('endsolid digital_elevation_model') 
                self.fo.close()

            # for binary STL we can only now prepend a header as we didn't have num_triangles until now.
            elif self.tile_info["fileformat"] == "STLb":
                # rename curent file so we can append it to the header file
                self.fo.close()
                body_file = temp_file + ".body"
                os.replace(temp_file, body_file)
                with open(body_file, "rb") as fbody:
                    with open(temp_file, "ab") as fheader: # new temp_file
                        BINARY_HEADER = "80sI" # up to 80 chars do NOT start with the word solid + number of faces as UINT32
                        fheader.write(struct.pack(BINARY_HEADER, b'Binary STL Writer', self.num_triangles))
                        shutil.copyfileobj(fbody, fheader) # append the body to the header
                os.remove(body_file)
            
            # For obj the the fo[0] temp file (vertices) must be filled, then the
            # .idx temp file needs to be appended to i 
            elif self.tile_info["fileformat"] == "obj":
                # fill vertex temp file
                print("Appending obj triangle indices\n", file=sys.stderr)
                for vc in vertex.vertex_index_dict:
                    self.fo[0].write(f"v {vc[0]}, {vc[1]}, {vc[2]}\n")
                self.fo[0].close()
                self.fo[1].close()

                # append index temp file top vertex temp file
                idx_temp_file = temp_file + ".idx"
                with open(idx_temp_file, "r") as idx_fo:
                    with open(temp_file, "a") as vert_fo:
                        shutil.copyfileobj(idx_fo, vert_fo)
                os.remove(idx_temp_file)
            
            return temp_file

  
       


 
# MAIN  (left this in so I can test stuff, most of it is however outdated and would need to be fixed ...)

#@profile # https://pypi.org/project/memory-profiler/
def main():
    nn = np.nan
    """
    top = np.array([[11,12,13,14],
                    [21,nn,nn,24],
                    [31,nn,nn,34],
                    [41,42,43,44],
                   ])

    top = np.array([[11,12,13],
                     [21,nn,23],
                     [31,32,33],
                    ])

    top = np.array([[np.nan, np.nan],
                    [np.nan, np.nan],
                    [np.nan, np.nan],
                    [1,1],
                   ])
    top = np.array([[0.3,0.5,0.4],
                    [0.4,np.nan,0.6],
                    [0.3,0.6,0.7],
                   ])

    top = np.array([[1],
                      ])

    top = np.array([[1.0,1.1, 1.2],
                    [1.4,1.2, 1.3],
                    [1.5,2.6, 1.0],
                    [1.2,1.6, 1.7],
                   ])
    
    top =  np.array([
                        [nn, nn, nn, 11, 11, nn, nn],
                        [nn, nn, 17, 22, 24, nn, nn],
                        [nn, 13, 33, 44, 33, 24, nn],                     
                        [11, 22, 55, 70, 25, 30, nn],
                        [14, 17, 33, 39, nn, 22, 12],
                        [nn, 10, 23, 10, nn, 10, nn],   
                        [nn, nn, 11,  6, nn, nn, nn],                     
                     ])
    
    top =  np.array([
                    [10, 10, 10, 10, 10, 10, 10],
                    [10, 10, 10, 10, 10, 10, 10],
                    [10, 10, 10, 10, 10, 10, 10],                     
                    [10, 10, 10, 100, 10, 10, 10],
                    [10, 10, 10, 10, 10, 10, 10],
                    [10, 10, 10, 10, 10, 10, 10],  
                    [10, 10, 10, 10, 10, 10, 10],                    
                    ])
    
    top =  np.array([ [nn, nn, 11],
                      [11, nn, nn],
                      [11, 11, nn],
                 ])
    
    top =  np.array([
                         [ 1, 5, 10, 50, 20, 10, 1],
                         [ 1, 10, 10, 50, 20, 10, 2],
                         [ 1, 11, 150, 30, 30, 10, 5],
                         [ 1, 23, 100, 40, 20, 10, 2 ],
                         [ 1, 50, 10, 10, 20, 10 , 1 ],

                   ])
    top = np.array([ [1]])
    """

    top =  np.array([ [2, 3, 4],
                      [3, 2, 3],
                      [3, 2, 1],
                 ])
    bot_elev = np.array([ [2, 3, 4],
                          [3, 1, 3],
                          [3, 2, 1],
                        ])
    

    
    """
    import matplotlib.pyplot as plt
    #plt.ion()
    fig = plt.figure(figsize=(7,10))
    npim = top
    imgplot = plt.imshow(npim, aspect=u"equal", interpolation=u"none")
    cmap_name = 'nipy_spectral' # gist_earth or terrain or nipy_spectral
    imgplot.set_cmap(cmap_name)
    #a = fig.add_axes()
    #plt.title(DEM_name + " " + str(center))
    plt.colorbar(orientation="horizontal")
    plt.show()
    """


    tile_info_dict = {
        #"scale"  : 10000, # horizontal scale number, defines the size of the model (= 3D map): 1000 => 1m (real) = 1000m in model
        "scale"  : 1, 
        "pixel_mm" : 1, # lateral (x/y) size of a pixel in mm
        "max_elev" : np.nanmax(top), # tilewide minimum/maximum elevation (in meter), either int or float, depending on raster
        "min_elev" : np.nanmin(top),
        "z_scale" :  1,     # z (vertical) scale (elevation exageration) factor, float
        "tile_no_x": 1, # current tile number in x, int, starting with 1, at upper left corner
        "tile_no_y": 1,
        "ntilesx": 1,
        "ntilesy": 1,
        "tile_centered" : False, # True: each tile's center is 0/0, False: global (all-tile) 0/0
        "fileformat": "stlb",  # folder/zip file name for all tiles
        #"fileformat": "obj",
        "base_thickness_mm": 0, # thickness between bottom and lowest elevation, NOT including the bottom relief.
        "tile_width": 100,
        "use_geo_coords": None,
        "no_bottom": False,
        "no_normals": True,
        "CPU_cores_to_use" : 1,
        "bottom_elevation": "bot.tif",
        "bottom_image": None
    }

    whratio = top.shape[0] / top.shape[1]
    tile_info_dict["tile_height"] = int(tile_info_dict["tile_width"]  * whratio)

    top = np.pad(top, (1,1), 'edge')
    
    bot_elev = np.pad(bot_elev, (1,1), 'edge')
    g = grid(top, bot_elev, tile_info_dict)



    #b = g.make_STLfile_buffer(ascii=True, no_normals=True, temp_file="STLtest_asc6.stl")
    #b = g.make_STLfile_buffer(ascii=False, no_normals=False, temp_file="STLtest_new_b3.stl")
    b = g.make_STLfile_buffer(tile_info_dict, ascii=False, temp_file="STLtest.stl")
    #f = open("STLtest_new.stl", 'wb');f.write(b);f.close()

    #b = g.make_OBJfile_buffer(no_bottom=False, temp_file="OBJtest2.obj", no_normals=False)
    print("done")


if __name__ == "__main__":
    main()

