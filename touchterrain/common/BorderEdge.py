import shapely

class BorderEdge:
    """Represents an edge on a top/bottom surface and whether it should have a vertical wall generated. Geometry is stored as a shapely.LineString.
    """
    
    geometry: shapely.LineString
    
    polygon_line: bool = False
    "Is the edge part of a polygon?"
    
    make_wall: bool = False
    "Should a vertical wall be generated during create_cell()"
    
    def __init__(self, geometry: shapely.LineString, polygon_line: bool = False, make_wall: bool = False):
        self.geometry = geometry
        self.make_wall = make_wall