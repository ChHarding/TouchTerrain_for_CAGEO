class vertex:

    # dict of index value for each vertex
    # key is tuple of coordinates, value is a unique index
    vertex_index_dict = -1
    
    coords: tuple[float, ...]

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
    
    def vertex_rounded_to_precision(self, decimals: int) -> vertex:
        def round_float_to_precision(decimals: int, input: float):
            return round(input, decimals)
        
        intermediate_list = []
        
        for c in self.coords:
            intermediate_list.append(round_float_to_precision(decimals=decimals, input=c))
            
        if len(intermediate_list) == 3:
            return vertex(*intermediate_list)
        else:
            raise ValueError(f"len(intermediate_list) was not 3, got {len(intermediate_list)}")
        