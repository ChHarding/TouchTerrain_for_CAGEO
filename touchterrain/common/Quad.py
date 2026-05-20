import shapely

from touchterrain.common.Vertex import vertex

class quad:
    """return list of 2 triangles (counterclockwise) per quad
       wall quads will NOT subdivide their quad into subquads if they are too skinny
       as this would require to re-index the entire mesh. However, I left the subdive
       stuff in in case we want to re-visit it later.
    """
    # class attribute, use quad.too_skinny_ratio
    too_skinny_ratio = 0.1 # border quads with a horizontal vs vertical ratio smaller than this will be subdivided
    
    vl: list[vertex] = []
    """Vertices mapping        NW SW SE NE
    - Top                      0  1  2  3
    - Bottom                   0  3  2  1
    """

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

    def get_triangles(self, split_rotation: int=0) -> list[tuple[vertex,...]]:
        "return list of 2 triangles (counterclockwise)"
        v0,v1,v2,v3 = self.vl[0],self.vl[1],self.vl[2],self.vl[3]
        t0 = (v0, v1, v2)  # verts of first triangle

        # if v3 is None, we only return t0
        if v3 is None:
            return [t0]

        t1 = (v0, v2, v3)  # verts of second triangle
        
        if split_rotation != 1 and split_rotation != 2:
            return [t0,t1]
        
        splitting_edge_slope_1 = abs(v0.coords[2] - v2.coords[2])
        splitting_edge_slope_2 = abs(v1.coords[2] - v3.coords[2])
        if split_rotation == 1:
            if splitting_edge_slope_1 > splitting_edge_slope_2:
                t0 = (v0, v1, v3)
                t1 = (v1, v2, v3)
        elif split_rotation == 2:
            if splitting_edge_slope_1 < splitting_edge_slope_2:
                t0 = (v0, v1, v3)
                t1 = (v1, v2, v3)
        else:
            print(f"Invalid split_rotation config value of {split_rotation}")

        return [t0,t1]

    def get_triangles_in_tuple_float(self, split_rotation: int) -> list[tuple[tuple[float, ...], ...]]:
        # convert Vertex objects in the tri to tuple[float, ...]
        quad_tris_in_tuple_float: list[tuple[tuple[float, ...], ...]] = []
        
        quad_tris = self.get_triangles(split_rotation=split_rotation)
        for tri in quad_tris:
            if tri is not None:
                quad_tris_in_tuple_float.append((tri[0].coords, tri[1].coords, tri[2].coords))
            
        return quad_tris_in_tuple_float
    
    def get_triangles_in_polygons(self, split_rotation: int) -> list[shapely.Polygon]:
        # convert Vertex objects in the tri to list[shapely.Polygon]
        quad_tris_in_polygons: list[shapely.Polygon] = []
        
        quad_tris = self.get_triangles(split_rotation=split_rotation)
        for tri in quad_tris:
            if tri is not None:
                quad_tris_in_polygons.append(shapely.Polygon([tri[0].coords, tri[1].coords, tri[2].coords, tri[0].coords]))
            
        return quad_tris_in_polygons

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