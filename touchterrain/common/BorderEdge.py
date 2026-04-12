import shapely

class BorderEdge:
    """Represents an edge on a top/bottom surface and whether it should have a vertical wall generated. Geometry is stored as a shapely.LineString.
    """
    
    geometry: shapely.LineString
    
    polygon_line: bool = False
    "Is the edge part of a polygon?"
    
    skip_future_eval_for_walls: bool = False
    "Should this edge be skipped in the next looped evaluation of edges for walls. This should be true if we have already found a matching edge on the neighboring cell."
    make_wall: bool = False
    "Should a vertical wall be generated during create_cell() during create_cell()"
    
    def __init__(self, geometry: shapely.LineString, polygon_line: bool = False, skip_future_eval_for_walls: bool = False, make_wall: bool = False):
        self.geometry = geometry
        self.polygon_line = polygon_line
        self.skip_future_eval_for_walls = skip_future_eval_for_walls
        self.make_wall = make_wall