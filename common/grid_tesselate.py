# grid_tesselate.py
# create triangles from a top and bottom numpy 2D array, including walls

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
# CH: Feb. 2018: added use of tempfile as file buffer to lower memory footprint
# CH: Feb. 2017: added calculations for normals in stl files
# CH: Jan. 22, 16: putting the vert index behind a comment makes some programs crash
#                  when loading the obj file, so I removed those.
# FIX: (CH, Nov.16,15): make the vertex index a per grid attribute rather than
#  a vertex class attribute as this seem to index not found fail eventually when
#  multiple grids are processed together.
# CH July 2015

import numpy as np
import copy   # to copy objects
import warnings # for muting warnings about nan in e.g. nanmean()
import struct # for making binary STL
from collections import OrderedDict # for vertex indices dict
import sys
import multiprocessing
import tempfile

# template for ascii STL file
ASCII_FACET =""" facet normal {face[0]:e} {face[1]:e} {face[2]:e}
  outer loop
   vertex {face[3]:e} {face[4]:e} {face[5]:e}
   vertex {face[6]:e} {face[7]:e} {face[8]:e}
   vertex {face[9]:e} {face[10]:e} {face[11]:e}
  endloop
 endfacet"""
ASCII_FACET =""" facet normal {face[0]:e} {face[1]:e} {face[2]:e} outer loop vertex {face[3]:e} {face[4]:e} {face[5]:e} vertex {face[6]:e} {face[7]:e} {face[8]:e} vertex {face[9]:e} {face[10]:e} {face[11]:e} endloop endfacet"""


# https://pypi.python.org/pypi/vectors/
from vectors import Vector, Point

# function to calculate the normal for a triangle
def get_normal(tri):
    """in: 3 verts, out normal (nx, ny,nz) with length 1
    """
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

class vertex(object):
    def __init__(self, x,y,z, vertex_idx_from_grid):
        self.coords = [x,y,z] # needs to be a list for zigzag magic to be able to change coords
        self.vert_idx = vertex_idx_from_grid

        # for non obj file this is set to -1, and there's no need to deal with vertex indices
        if self.vert_idx != -1:
            # if key does not yet exist ...
            if not self.vert_idx.has_key(tuple(self.coords)): # can't hash lists
                # hash with 3D coords with a running number as Id
                self.vert_idx[tuple(self.coords)] = len(self.vert_idx) # ... store it with current length (= number of elements) as index value
            else: # this vertex already has an Id
                #print self.coords, len(self.vert_idx) # DEBUG
                pass

    def get_id(self):
        '''return Id for my coords'''
        i = self.vert_idx[tuple(self.coords)]
        return i


    def get(self):
        "returns [x,y,z] list of vertex"
        return self.coords

    def __str__(self):
        return "%.2f %.2f %.2f " % (self.coords[0], self.coords[1], self.coords[2])

    def __getitem__(self, index):
        return self.coords[index]


class quad(object):
    " 4 vertices in counter clockwise order"

    def __init__(self, v0, v1, v2, v3):
        self.vl = [v0, v1, v2, v3]

    def get_triangles(self):
        "return list of 2 triangles (counterclockwise)"
        v0,v1,v2,v3 = self.vl[0],self.vl[1],self.vl[2],self.vl[3]
        t0 = (v0, v1, v2)  # verts of first triangle
        t1 = (v0, v2, v3)  # verts of second triangle
        return (t0,t1)

    def get_triangles_with_indexed_verts(self):
        "return list of 2 triangles (counterclockwise) as vertex indices"

        vertidx = [] # list of the 4 verts as index
        for v in self.vl: # quad as list of 4 verts, seach as (x,y,z)
            vi = v.get_id()
            vertidx.append(vi)
            #print v,vi

        t0 = (vertidx[0], vertidx[1], vertidx[2])  # verts of first triangle
        t1 = (vertidx[0], vertidx[2], vertidx[3])  # verts of second triangle
        return (t0,t1)

    def __str__(self):
        rs ="  "
        for n,v in enumerate(self.vertlist):
            rs = rs + "v" + str(n) + ": " + str(v) + "  "
        return rs


class cell(object):
    "a cell with a top and bottom quad, constructor: uses refs and does NOT copy"
    def __init__(self, topquad, bottomquad, borders):
        self.topquad = topquad
        self.bottomquad = bottomquad
        self.borders = borders
    def __str__(self):
        r = hex(id(self)) + "\n top:" + str(self.topquad) + "\n btm:" + str(self.bottomquad) + "\n borders:\n"
        for d in ["N", "S", "E", "W"]:
            if self.borders[d] != False:
                r = r + "  " + d + ": " + str(self.borders[d]) + "\n"
        return r


class grid(object):
    " makes cells from two numpy arrays (top, bottom) of the same shape. tile_info is a simple dict"

    def __init__(self, top, bottom, tile_info):
        "top: top elevation raster, must hang over by 1 row/column on each side (be already padded)\
         bottom: None => bottom elevation is 0, otherwise a 8 bit raster that will be resized to top's size\
         tile_info: dict with info about the current tile + some tile global settings"

        if tile_info["fileformat"] == 'obj':
            self.vi = OrderedDict() # set class attrib to empty dict, will be filled with vertex indices
        else:
            self.vi = -1 # means: don't use vertex indices
        self.cells = None # stores the cells, for now a 2D array of cells, but could also be a list of cells (later)

        #print top.shape, bottom.shape
        tp = top.dtype # dtype('float32')
        if not str(tp).startswith("float"): print "Warning: expecting float raster!"

        # Important: in 2D numpy arrays, x and y are "flipped" in the sense that when printing top
        # top[0,0] appears to the upper left (NW) corner and [0,1] (East) of it:
        #[[11  12 13]       top[0,1] => 12
        # [Nan 22 23]       top[2,0] => NaN (Not a value -> undefined elevation)
        # [31  32 33]       top[2,1] => 32
        # [41  42 43]]
        # i.e. height (y) is encoded in the first (0) dimension, width in the second (1),
        # the 'edge" padded version for a top left tile might be this, the right and bottom fringe
        # are part of the adjecent tiles, which must be used in the interpolation to result in no-seam edges
        #      [[11, 11, 12, 13, 14],
               #[11, 11, 12, 13, 14],
               #[Nan,Nan,22, 23, 24],
               #[31, 31, 32, 33, 34],
               #[41, 41, 42, 43, 44],
               #[41, 51, 52, 54, 55]])


        # DEBUG: normalized (0 - 1) xy coord increment per cell
        #y_norm_delta  = 1 / float(top.shape[0]) # y (north-south) direction
        #x_norm_delta  = 1 / float(top.shape[1]) # x (east-west) direction
        #print "normalized x/y delta:", x_norm_delta, y_norm_delta

        # cell size (x and y delta) in mm
        csz_mm = tile_info["pixel_mm"]

        have_nan = np.isnan(np.sum(top)) # True => we have NaN values, see http://stackoverflow.com/questions/6736590/fast-check-for-nan-in-numpy
        #print "have_nan", have_nan

        # convert top's elevation to mm
        top -= float(tile_info["min_elev"]) # subtract tile-wide max from top
        #print np.nanmin(top), np.nanmax(top)
        scz = 1 / float(tile_info["scale"]) * 1000.0 # scale z to mm
        #print tile_info["scale"], tile_info["z_scale"], scz
        top *= scz * tile_info["z_scale"] # apply z-scale
        #print np.nanmin(top), np.nanmax(top)
        top += tile_info["base_thickness_mm"] # add base thickness
        #print "top min/max:", np.nanmin(top), np.nanmax(top)

        tile_info["max_elev"] = np.nanmax(top)
        tile_info["min_elev"] = np.nanmin(top)

        # max index in x and y for "inner" raster
        xmaxidx = top.shape[1]-2
        ymaxidx = top.shape[0]-2
        #print range(1, xmaxidx+1), range(1, ymaxidx+1)

        

        # offset so that 0/0 is the center of this tile (local) or so that 0/0 is the upper left corner of all tiles (global)
        tile_width = (xmaxidx * tile_info["pixel_mm"])
        tile_height = (ymaxidx * tile_info["pixel_mm"])
        #print "model width, height (mm): %.2f x %.2f" % (tile_width, tile_height)
        

        if tile_info["tile_centered"] == False: # global offset, best for looking at all tiles together
            offsetx = -tile_width  * tile_info["tile_no_x"]-1 + tile_info["full_raster_width"] / 2.0# tile_no starts with 1!
            offsety = -tile_height * tile_info["tile_no_y"]-1 + tile_info["full_raster_height"] / 2.0
        else: # local centered for printing
            offsetx = tile_width / 2.0
            offsety = tile_height / 2.0
        #print offsetx, offsety

        # store cells in an array, init to None
        self.cells = np.empty([ymaxidx, xmaxidx], dtype=cell)

        # report progress in %
        percent = 10
        pc_step = int(ymaxidx/percent) + 1
        progress = 0
        print >> sys.stderr, "started processing", multiprocessing.current_process()

        for j in range(1, ymaxidx+1):    # y dimension for looping within the +1 padded raster
            if j % pc_step == 0:
                progress += percent
                print >> sys.stderr, progress, "%", multiprocessing.current_process()

            for i in range(1, xmaxidx+1):# x dim.
                #print "y=",j," x=",i, " elev=",top[j,i]

                # if center elevation of current cell is NaN, set it to None and skip the rest
                if np.isnan(top[j,i]):
                    self.cells[j-1,i-1] = None
                    continue


                # x/y coords of cell "walls", origin is upper left
                E = (i-1) * csz_mm - offsetx # index -1 as it's ref'ing to top, not ptop
                W = E + csz_mm
                N = -(j-1) * csz_mm + offsety # y is flipped to negative
                S = N - csz_mm
                #print i,j, " ", E,W, " ",  N,S, " ", top[j,i]


                ## Which directions will need to have a wall?
                # True means we have an adjacent cell and need a wall in that direction
                borders =   dict([[drct,False] for drct in ["N", "S", "E", "W"]]) # init
                if j == 1        : borders["N"] = True
                if j == ymaxidx  : borders["S"] = True
                if i == 1        : borders["W"] = True
                if i == xmaxidx  : borders["E"] = True
                if have_nan: #  if we have nan cells, check for walls facing an adjacent NaN cell
                    #print "NSWE", top[j-1,i], top[j+1,i], top[j,i-1], top[j,i+1]
                    with warnings.catch_warnings():
                        warnings.filterwarnings('error')
                        try:
                            if np.isnan(top[j-1,i]): borders["N"] = True
                            if np.isnan(top[j+1,i]): borders["S"] = True
                            if np.isnan(top[j,i-1]): borders["W"] = True
                            if np.isnan(top[j,i+1]): borders["E"] = True
                        except RuntimeWarning:
                            pass # nothing wrong - just here to ignore the warning

                # get elevation of four corners (array order is top[y,x]!!!!)
                if not have_nan:
                    NEelev = (top[j+0,i+0] + top[j-1,i-0] + top[j-1,i+1] + top[j-0,i+1]) / 4.0
                    NWelev = (top[j+0,i+0] + top[j+0,i-1] + top[j-1,i-1] + top[j-1,i+0]) / 4.0
                    SEelev = (top[j+0,i+0] + top[j-0,i+1] + top[j+1,i+1] + top[j+1,i+0]) / 4.0
                    SWelev = (top[j+0,i+0] + top[j+1,i+0] + top[j+1,i-1] + top[j+0,i-1]) / 4.0
                else:
                    # interpolate each corner with possible NaNs, using mean()
                    # Note: if we have 1 or more NaNs, we get a warning: warnings.warn("Mean of empty slice", RuntimeWarning)
                    # but if the result of ANY corner is NaN (b/c it used 4 NaNs), skip this cell entirely by setting it to None instead a cell object
                    with warnings.catch_warnings():
                        warnings.filterwarnings('error')
                        try:
                            NEelev = np.nanmean( np.array([top[j+0,i+0], top[j-1,i-0], top[j-1,i+1], top[j-0,i+1]]) )
                            NWelev = np.nanmean( np.array([top[j+0,i+0], top[j+0,i-1], top[j-1,i-1], top[j-1,i+0]]) )
                            SEelev = np.nanmean( np.array([top[j+0,i+0], top[j-0,i+1], top[j+1,i+1], top[j+1,i+0]]) )
                            SWelev = np.nanmean( np.array([top[j+0,i+0], top[j+1,i+0], top[j+1,i-1], top[j+0,i-1]]) )
                        except RuntimeWarning: #  corner is surrounded by NaN eleveations - skip this cell
                            print j-1, i-1, ": elevation of at least one corner of this cell is NaN - skipping cell"
                            #print " NW",NWelev," NE", NEelev, " SE", SEelev, " SW", SWelev # DEBUG
                            num_nans = sum(np.isnan(np.array([NEelev, NWelev, SEelev, SWelev]))) # is ANY of the corners NaN?
                            if num_nans > 0: # yes, set cell to None and skip it ...
                                self.cells[j-1,i-1] = None
                                continue

                #NWelev = NEelev = SEelev = SWelev = ptop[j,i] # DEBUG, set all corners to center elev
                #print " NW",NWelev," NE", NEelev, " SE", SEelev, " SW", SWelev # DEBUG

                #
                # Make top and bottom quads and wall. Note that here we flip x and y coordinate axis to the system used in 3D graphics
                #
                
                # make top quad (x,y,z)    vi is the vertex index dict of the grids
                NEt = vertex(E, N, NWelev, self.vi)  # yes, NEt gets the z of NWelev, has to do with coordinate system change
                NWt = vertex(W, N, NEelev, self.vi)
                SEt = vertex(E, S, SWelev, self.vi)
                SWt = vertex(W, S, SEelev, self.vi)
                topq = quad(NEt, SEt, SWt, NWt) # with this vertex order, a certain vertex order is needed to make the 2 triangles be counter clockwise and so point outwards
                #print topq


                # make bottom quad (x,y,z)
                NEelev = NWelev = SEelev = SWelev = 0 # uniform bottom elevation, when bottom is None
                if hasattr(bottom, "__len__"):# if bottom is not None, interpolate bottom elevation (NaN should never occur here!)
                    NEelev = (bottom[j+0,i+0] + bottom[j-1,i-0] + bottom[j-1,i+1] + bottom[j-0,i+1]) / 4.0
                    NWelev = (bottom[j+0,i+0] + bottom[j+0,i-1] + bottom[j-1,i-1] + bottom[j-1,i+0]) / 4.0
                    SEelev = (bottom[j+0,i+0] + bottom[j-0,i+1] + bottom[j+1,i+1] + bottom[j+1,i+0]) / 4.0
                    SWelev = (bottom[j+0,i+0] + bottom[j+1,i+0] + bottom[j+1,i-1] + bottom[j+0,i-1]) / 4.0
                NEb = vertex(E, N, NWelev, self.vi)
                NWb = vertex(W, N, NEelev, self.vi)
                SEb = vertex(E, S, SWelev, self.vi)
                SWb = vertex(W, S, SEelev, self.vi)
                botq = quad(NEb, NWb, SWb, SEb)
                #print botq

                # in borders dict, replace any True with a quad of that wall
                if borders["N"] == True: borders["N"] = quad(NEb, NEt, NWt, NWb)
                if borders["S"] == True: borders["S"] = quad(SWb, SWt, SEt, SEb)
                # E W needed to be flipped
                if borders["E"] == True: borders["E"] = quad(NWt, SWt, SWb, NWb)
                if borders["W"] == True: borders["W"] = quad(SEt, NEt, NEb, SEb)

                # make cell from both
                c = cell(topq, botq, borders)
                #print c


                # DEBUG: store i,j, and central elev
                #c.iy = j-1
                #c.ix = i-1
                #c.central_elev = top[j-1,i-1]

                # put cell into array of cells (self.cells is NOT padded, => -1)
                self.cells[j-1,i-1] = c
                #print self.cells[j-1,i-1]
                #print j-1,i-1, self.cells

        #print self.cells
        #print vertex.vert_idx

        print >> sys.stderr, "100%", multiprocessing.current_process()


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



    def __str__(self):
        return "TODO: implement __str__() for grid class"


    def _build_binary_stl_orig(self, facets):
        "in: list of [x,y,z]   out: list of binary STL strings"
        # en.wikipedia.org/wiki/STL_%28file_format%29#Binary_STL
        BINARY_HEADER = "80sI" # up to 80 chars ( do NOT start with the word solid!) + number of faces as UINT32
        BINARY_FACET = "12fH" # 12 32-bit floating-point numbers + 2-byte ("short") unsigned integer ("attribute byte count" -> use 0)
        l = [struct.pack(BINARY_HEADER, b'Binary STL Writer', len(facets))] #  (I)
        for facet  in facets:
            # prepend normal (0,0,0), pad the end with a unsigned short byte ("attribute byte count")
            # I assume a 0 normal forces the sw reading this to calculate it (Meshlab seems to do this) (???)
            facet = [0,0,0]  + facet + [0]        #print facet
            l.append(struct.pack(BINARY_FACET, *facet))
        return l

    def _build_ascii_stl_orig(self, facets):
        "in: list of [x,y,z]   out: list of ascii STL strings"
        l = ['solid digital_elevation_model'] # digital_elevation_model is the name of the model
        for facet in facets:
            facet = [0,0,0] + facet
            s = ASCII_FACET.format(face=facet) # ASCII string with  12 floats (3 for normal + 3 * 3 for verts )
            #print s
            l.append(s)
        l.append('endsolid digital_elevation_model')
        return l

    def _build_ascii_stl(self, tris):
        "in: list of triangles, each a list of 3 verts   out: list of ascii STL strings"
        l = ['solid digital_elevation_model'] # digital_elevation_model is the name of the model
        for t in tris:
            n = get_normal(t)
            tl = n
            for v in t:
                coords = v.get() # get() => list of coords [x,y,z]
                tl.extend(coords) # extend() unpacks that list!
            #print tl
            s = ASCII_FACET.format(face=tl) # ASCII string with  12 floats (3 for normal + 3 * 3 for verts )
            #print s
            l.append(s)
        l.append('endsolid digital_elevation_model')
        return l

    def _build_binary_stl(self, tris):
        "in: list of triangles, each a list of 3 verts   out: list of binary STL strings"
        # en.wikipedia.org/wiki/STL_%28file_format%29#Binary_STL
        BINARY_HEADER = "80sI" # up to 80 chars do NOT start with the word solid + number of faces as UINT32
        BINARY_FACET = "12fH" # 12 32-bit floating-point numbers + 2-byte ("short") unsigned integer ("attribute byte count" -> use 0)
        l = [struct.pack(BINARY_HEADER, b'Binary STL Writer', len(tris))] #  (I)
        for t  in tris:
            n = get_normal(t)
            tl = n
            for v in t:
                coords = v.get() # get() => list of coords [x,y,z]
                tl.extend(coords) # extend() unpacks that list!
                #print tl
            tl.append(0) # append attribute byte 0
            l.append(struct.pack(BINARY_FACET, *tl))
        return l

    def make_STLfile_buffer(self, ascii=False, no_bottom=False, temp_file=None):
        """"returns buffer of ASCII or binary STL file from a list of triangles, each triangle must have 9 floats (3 verts, each xyz)
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
                # list of quads for this cell,
                if no_bottom == False:
                    quads = [cell.topquad, cell.bottomquad]
                else:
                    quads = [cell.topquad] # no bottom quads, only top                     
                    
                for k in cell.borders.keys(): # plus get border quads if we have any
                    if cell.borders[k] != False: quads.append(cell.borders[k])
                    # TODO? the tris for these quads can become very skinny, should be subdivided into more quads to keep the angles high enough
                for q in quads:
                    t0,t1 = q.get_triangles()
                    triangles.append(t0)
                    triangles.append(t1)
                del cell

        #for t in triangles: print t

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


    def make_OBJfile_buffer(self, no_bottom=False, temp_file=None):
        """returns buffer of OBJ file, creates a list of triangles and a list of indexed x,y,z vertices
           if no_bottom is True, bottom triangles are omitted
           if temp_file is not None, write OBJ into it (instead of a buffer) and return it

        mtllib dontcare.mtl
        g vert
        v 0.00 0.00 -4938.15
        v 9751.96 0.00 -4944.11
        v 9751.96 9686.67 -4947.28
        v 0.00 9686.67 -4963.42
        g tris
        usemtl initialShadingGroup
        f 1 2 3
        f 3 4 1
        """

        assert self.vi != -1, "make_OBJfile_buffer: need grid with vertex indices!"

        # initially, store each line in output file as string in a list
        buf_as_list = []
        buf_as_list.append("g vert")    # header for vertex indexing section
        for v in self.vi.keys(): # self.vi is a dict of vertex indices
            #vstr = "v %f %f %f #%d" % (v[0], v[1], v[2], i+1) # putting the vert index behind a comment makes some programs crash when loading the obj file!
            vstr = "v %f %f %f" % (v[0], v[1], v[2])
            buf_as_list.append(vstr)

        buf_as_list.append("g tris")

        # number of cells in x and y     grid is cells[y,x]
        ncells_x = self.cells.shape[1]
        ncells_y = self.cells.shape[0]

        # go through all cells, get all its quads and split into triangles
        for ix in range(0, ncells_x):
          for iy in range(0, ncells_y):
            cell = self.cells[iy,ix] # get cell from 2D array of cells (grid)

            if cell != None:
                # list of quads for this cell,
                if no_bottom == False:
                    quads = [cell.topquad, cell.bottomquad]
                else:
                    quads = [cell.topquad] # no bottom quads, only top  
                    
                for k in cell.borders.keys(): # plus get border quads if we have any
                    if cell.borders[k] != False: quads.append(cell.borders[k])
                for q in quads:
                    t0,t1 = q.get_triangles_with_indexed_verts()

                    for f in (t0,t1): # output the 2 facets (triangles)
                        fstr = "f %d %d %d" % (f[0]+1, f[1]+1, f[2]+1) # OBJ indedices start at 1!
                        buf_as_list.append(fstr)
                del cell

        # concat list of strings to a single string
        buf = "\n".join(buf_as_list).encode("UTF-8")

        if temp_file ==  None: return buf

        # Write string into temp file and return it
        temp_file.write(buf)
        return temp_file

# MAIN  (left this in so I can test stuff ...)
if __name__ == "__main__":
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

    top =  np.array([[11, 11, 12, 13, 14, 15],
                     [11, 11, 12, 13, 14, 15],
               [np.nan,np.nan,22, 23, 24, 25],
               [np.nan,np.nan,32, 33, 34, 35],
                     [41, 41, 42, 43, 44, 45]])
    """
    top =  np.array([
                         [ 10, 10, 50],
                         [ 11, 150, 10 ],
                         [ 50, 10, 10 ],

                   ])


    #bottom = np.zeros((4, 3)) # num along x, num along y
    top = top.astype(float)
    print top
    #print bottom

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
        "scale"  : 10000, # horizontal scale number, defines the size of the model (= 3D map): 1000 => 1m (real) = 1000m in model
        "pixel_mm" : 10, # lateral (x/y) size of a pixel in mm
        "max_elev" : np.nanmax(top), # tilewide minimum/maximum elevation (in meter), either int or float, depending on raster
        "min_elev" : np.nanmin(top),
        "z_scale" :  1.0,     # z (vertical) scale (elevation exageration) factor, float
        "tile_no_x": 1, # tile number in x, int, starting with 1, at upper left corner
        "tile_no_y": 1,
        "tile_centered" : True, # True: each tile's center is 0/0, False: global (all-tile) 0/0
        "fileformat": "STLb",  # folder/zip file name for all tiles
        "base_thickness_mm": 2, # thickness between bottom and lowest elevation, NOT including the bottom relief.



    }
    top = np.pad(top, (1,1), 'edge')
    g = grid(top, None, tile_info_dict)

    #b = g.make_STLfile_buffer(ascii=True)
    b = g.make_STLfile_buffer(ascii=False)
    f = open("STLtest_bin.stl", 'wb');f.write(b);f.close()

    #b = g.make_OBJfile_buffer()
    #f = open("OBJtest.obj", 'wb');f.write(b);f.close()
    print "done"



else:
    #print "imported", __file__
    pass


