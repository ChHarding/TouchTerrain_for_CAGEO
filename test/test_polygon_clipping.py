import numpy
import unittest
import shapely

from touchterrain.common.polygon_clipping import find_cell_and_clipping_poly_intersection, mark_overlapping_edges_for_walls, mark_shared_edges_for_walls
from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.shapely_plot import plot_shapely_geometries_colormap

def createTestOverlappingEdges() -> list[list[BorderEdge]]:
    return [
        [
            BorderEdge(geometry = shapely.LineString([(0,0), (0,50)]), polygon_line=True)
        ],
        [
            BorderEdge(geometry = shapely.LineString([(0,0), (0,10)]), polygon_line=False),
            BorderEdge(geometry = shapely.LineString([(0,10), (0,20)]), polygon_line=True),
            BorderEdge(geometry = shapely.LineString([(0,20), (0,30)]), polygon_line=False),
            BorderEdge(geometry = shapely.LineString([(0,30), (0,50)]), polygon_line=True)
        ]
    ]
    
def createTestPolygonCellIntersectionData() -> tuple[shapely.Polygon, list[list[tuple[float, float]]]]:

    '''  
    |-------
    |      /
    |      \\
    |       | <- cell vertical boundary. Clipping portion here is (10,15)<>(10,20)
    |        \\  
    |        /
    |_______|
    '''    
    clippingPrint2DPoly = shapely.Polygon([(0, 0), (10, 0), (10, 5), (15, 10), (10, 15), (10, 20), (5, 25), (10, 30), (5, 30), (0, 25), (0, 0)])
    
    # quad are arranged in 3x2 (Y,X). Vertices in CCW order NW SW SE NE
    quadPrint2DCoords1 = [(1, 30), (1.0, 1), (10, 1), (10, 30), (1, 30)]
    quadPrint2DCoords2 = [(10, 30), (10.0, 1), (19, 1), (19, 30), (10, 30)]
    quadPrint2DCoords3 = [(1, 1), (1.0, -28), (10, -28), (10, 1), (1, 1)]
    quadPrint2DCoords4 = [(10, 1), (10.0, -28), (19, -28), (19, 1), (10, 1), (10, 1)]
    # quad 5 and 6 are outside below the clipping polygon
    quadPrint2DCoords5 = [(1, -28), (1.0, -57), (10, -57), (10, -28), (1, -28)]
    quadPrint2DCoords6 = [(10, -28), (10.0, -57), (19, -57), (19, -28), (10, -28)]
    
    return (clippingPrint2DPoly, [
        quadPrint2DCoords1, 
        quadPrint2DCoords2, 
        quadPrint2DCoords3, 
        quadPrint2DCoords4,
        quadPrint2DCoords5, 
        quadPrint2DCoords6])

class TestPolygonClipping(unittest.TestCase):
    
    def test_find_intersection_geometries(self):
        testData = createTestPolygonCellIntersectionData()
        clippingPrint2DPoly = testData[0]
        
        raster_variants = RasterVariants(original=numpy.ones((3, 2)), nan_close=None, dilated=None, edge_interpolation=None)
        raster_variants.polygon_intersection_geometry = numpy.empty(raster_variants.original.shape, dtype=object)
        raster_variants.polygon_intersection_edge_buckets = numpy.empty(raster_variants.original.shape, dtype=object)
        
        clippingPrint2DPolyIndexMap = numpy.arange(6).reshape(raster_variants.original.shape)
        
        for j in range(0, raster_variants.original.shape[0]): # Y
            for i in range(0, raster_variants.original.shape[1]): # X
                find_cell_and_clipping_poly_intersection(surface_raster_variant=raster_variants, cellLocation=(j,i), clippingPrint2DPoly=clippingPrint2DPoly, quadPrint2DCoords=testData[1][clippingPrint2DPolyIndexMap[j][i]])
              
        self.assertTrue(~numpy.isnan(raster_variants.original[0][0]))
        self.assertTrue(~numpy.isnan(raster_variants.original[0][1]))
        self.assertTrue(~numpy.isnan(raster_variants.original[1][0]))
        self.assertTrue(~numpy.isnan(raster_variants.original[1][1])) 
        self.assertTrue(numpy.isnan(raster_variants.original[2][0]))
        self.assertTrue(numpy.isnan(raster_variants.original[2][1]))
        
        quadPolys = list(map(lambda x:shapely.Polygon(x),testData[1]))
        basePolys = [testData[0]] + quadPolys
        
        intersectionPolys = []
        edgeBucketsFlattenedPerCell = []
        for j in range(0, raster_variants.original.shape[0]): # Y
            for i in range(0, raster_variants.original.shape[1]): # X
                # Debug only show results from a specific cell
                # if j != 1 or i != 0:
                #     continue
                
                # if raster_variants.polygon_intersection_geometry[j][i] is not None:
                #     intersectionPolys += [
                #     raster_variants.polygon_intersection_geometry[j][i]
                #     ]
                
                
                
                if raster_variants.polygon_intersection_edge_buckets[j][i] is not None:
                    edgeBucketsFlattenedPerCell += [
                        raster_variants.polygon_intersection_edge_buckets[j][i]['N'] + 
                        raster_variants.polygon_intersection_edge_buckets[j][i]['W'] + 
                        raster_variants.polygon_intersection_edge_buckets[j][i]['S'] + 
                        raster_variants.polygon_intersection_edge_buckets[j][i]['E'] +
                        raster_variants.polygon_intersection_edge_buckets[j][i]['other']
                        ]
        
        mark_shared_edges_for_walls(polygon_intersection_edge_buckets=raster_variants.polygon_intersection_edge_buckets, direction=(-1,-1))
        
        plot_shapely_geometries_colormap(basePolys=basePolys, intersectionPolys=intersectionPolys, edgeBuckets=edgeBucketsFlattenedPerCell)
    
    def test_mark_overlapping_edges_for_walls(self):
        testEdges = createTestOverlappingEdges()
      
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
        testEdges = createTestOverlappingEdges()
      
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