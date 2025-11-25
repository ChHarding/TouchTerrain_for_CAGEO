import unittest
from shapely.geometry import Polygon, LineString

from touchterrain.common.polygon_clipping import mark_overlapping_edges_for_walls
from touchterrain.common.BorderEdge import BorderEdge

def createTestEdges() -> list[list[BorderEdge]]:
    return [
        [
            BorderEdge(geometry = LineString([(0,0), (0,50)]), polygon_line=True)
        ],
        [
            BorderEdge(geometry = LineString([(0,0), (0,10)]), polygon_line=False),
            BorderEdge(geometry = LineString([(0,10), (0,20)]), polygon_line=True),
            BorderEdge(geometry = LineString([(0,20), (0,30)]), polygon_line=False),
            BorderEdge(geometry = LineString([(0,30), (0,50)]), polygon_line=True)
        ]
    ]

class TestPolygonClipping(unittest.TestCase):
    
    def test_mark_overlapping_edges_for_walls(self):
        testEdges = createTestEdges()
      
        cell_A_edges = testEdges[0]
        cell_B_edges = testEdges[1]
        
        mark_overlapping_edges_for_walls(cell_1_edges=cell_A_edges, cell_2_edges=cell_B_edges)
        
        self.assertTrue(len(cell_A_edges) == 4)
        
        self.assertTrue(len(cell_A_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_A_edges[0].polygon_line == True)
        self.assertTrue(cell_A_edges[0].make_wall == True) # make wall on cell 1(A) if not flipped
        
        self.assertTrue(len(cell_A_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_A_edges[3].polygon_line == True)
        self.assertTrue(cell_A_edges[3].make_wall == False)
        
        self.assertTrue(len(cell_B_edges) == 4)
        
        self.assertTrue(len(cell_B_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_B_edges[0].polygon_line == False)
        self.assertTrue(cell_B_edges[0].make_wall == False) # don't make wall on cell 2(B) if not flipped
        
        self.assertTrue(len(cell_B_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_B_edges[3].polygon_line == True)
        self.assertTrue(cell_B_edges[3].make_wall == False)

        # Check if all edges are matched (shown by marking for skip)
        for edge in cell_A_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)
            
        for edge in cell_B_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)
            
    
    def test_mark_overlapping_edges_for_walls_flipped(self):
        testEdges = createTestEdges()
      
        cell_B_edges = testEdges[1]
        cell_A_edges = testEdges[0]
        
        mark_overlapping_edges_for_walls(cell_1_edges=cell_B_edges, cell_2_edges=cell_A_edges)
        
        self.assertTrue(len(cell_A_edges) == 4)
        
        self.assertTrue(len(cell_A_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_A_edges[0].polygon_line == True)
        self.assertTrue(cell_A_edges[0].make_wall == False) # don't make wall on cell 2(A) if flipped
        
        self.assertTrue(len(cell_A_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_A_edges[3].polygon_line == True)
        self.assertTrue(cell_A_edges[3].make_wall == False)
        
        self.assertTrue(len(cell_B_edges) == 4)
        
        self.assertTrue(len(cell_B_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_B_edges[0].polygon_line == False)
        self.assertTrue(cell_B_edges[0].make_wall == True) # make wall on cell 2(B) if flipped
        
        self.assertTrue(len(cell_B_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_B_edges[3].polygon_line == True)
        self.assertTrue(cell_B_edges[3].make_wall == False)

        # Check if all edges are matched (shown by marking for skip)
        for edge in cell_A_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)
            
        for edge in cell_B_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)
        
        # cell_2_edges: list[BorderEdge] = [
        #     BorderEdge(geometry = LineString([(0,0), (0,5)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,5), (5,10)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(5,10), (0,15)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,15), (0,20)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,20), (7,25)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(7,25), (0,30)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,30), (0,50)]), polygon_line=False),
        #     ]