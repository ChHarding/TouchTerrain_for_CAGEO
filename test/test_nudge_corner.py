import itertools
import numpy
import unittest

from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.nudge_corner import IntermediateCorner, corner_directions_border_outward_by_lte, find_middle_corner

# pytest -s .\test\test_nudge_corner.py

def createTestRaster() -> numpy.ndarray:
    
    '''
    00000
    01110
    00110
    00010
    00000
    '''
    return numpy.array([[0,0,0,0,0], [0,1,1,1,0], [0,0,1,1,0], [0,0,0,1,0], [0,0,0,0,0]])

class TestNudgeCorners(unittest.TestCase):
    def test_find_intersection_geometries(self):
        
        case1 = corner_directions_border_outward_by_lte(raster=createTestRaster(), cell_location=(1,1), lte=0)
        self.assertTrue(IntermediateCorner.NE not in case1)
        self.assertTrue(IntermediateCorner.NW in case1)
        self.assertTrue(IntermediateCorner.SW in case1)
        self.assertTrue(IntermediateCorner.SE not in case1)
        
        case2 = corner_directions_border_outward_by_lte(raster=createTestRaster(), cell_location=(1,2), lte=0)
        self.assertTrue(IntermediateCorner.NE not in case2)
        self.assertTrue(IntermediateCorner.NW not in case2)
        self.assertTrue(IntermediateCorner.SW not in case2)
        self.assertTrue(IntermediateCorner.SE not in case2)
        
        case3 = corner_directions_border_outward_by_lte(raster=createTestRaster(), cell_location=(1,3), lte=0)
        self.assertTrue(IntermediateCorner.NE in case3)
        self.assertTrue(IntermediateCorner.NW not in case3)
        self.assertTrue(IntermediateCorner.SW not in case3)
        self.assertTrue(IntermediateCorner.SE not in case3)
        
        case4 = corner_directions_border_outward_by_lte(raster=createTestRaster(), cell_location=(2,0), lte=0)
        self.assertTrue(IntermediateCorner.NE not in case4)
        self.assertTrue(IntermediateCorner.NW in case4)
        self.assertTrue(IntermediateCorner.SW in case4)
        self.assertTrue(IntermediateCorner.SE in case4)
        
        case4 = corner_directions_border_outward_by_lte(raster=createTestRaster(), cell_location=(2,4), lte=0)
        self.assertTrue(IntermediateCorner.NE in case4)
        self.assertTrue(IntermediateCorner.NW not in case4)
        self.assertTrue(IntermediateCorner.SW not in case4)
        self.assertTrue(IntermediateCorner.SE in case4)
        
        pass
    
    def test_find_middle_corner(self):
        
        case_NW = [IntermediateCorner.NE, IntermediateCorner.NW, IntermediateCorner.SW]
        for c in [list(p) for p in itertools.permutations(case_NW)]:
            self.assertEqual(find_middle_corner(c), IntermediateCorner.NW)
        
        case_SW = [IntermediateCorner.NW, IntermediateCorner.SW, IntermediateCorner.SE]
        for c in [list(p) for p in itertools.permutations(case_SW)]:
            self.assertEqual(find_middle_corner(c), IntermediateCorner.SW)
        
        case_SE = [IntermediateCorner.SW, IntermediateCorner.SE, IntermediateCorner.NE]
        for c in [list(p) for p in itertools.permutations(case_SE)]:
            self.assertEqual(find_middle_corner(c), IntermediateCorner.SE)
        
        case_NE = [IntermediateCorner.SE, IntermediateCorner.NE, IntermediateCorner.NW]
        for c in [list(p) for p in itertools.permutations(case_NE)]:
            self.assertEqual(find_middle_corner(c), IntermediateCorner.NE)