from enum import Enum

import numpy

class IntermediateCorner(Enum):
    NE = 0
    NW = 1
    SW = 2
    SE = 3
       
def corner_directions_border_outward_by_lte(raster: numpy.ndarray, cell_location: tuple[int, int], lte: float) -> list[IntermediateCorner]:
    """Check which corner direction for a cell are bordered by cell values less than or equal to a specified value

    :param raster: elevation raster (bottom)
    :param cell_location: Target cell location in Y,X order
    :type cell_location: tuple[int, int]
    :param lte: less than or equal value to compare
    :type lte: float
    :return: _description_
    :rtype: IntermediateCorner
    """
    # Corners to check in form of cell locations to check and the corner direction
    corners_to_check: list[tuple[list[tuple[int, int]], IntermediateCorner]] = []
    
    # corners that border outward with lte cells
    corners_match: list[IntermediateCorner] = []
    
    # Create corner tuples
    NE_check_locations = [(cell_location[0]-1, cell_location[1]), (cell_location[0]-1, cell_location[1]+1), (cell_location[0], cell_location[1]+1)]
    corners_to_check.append((NE_check_locations, IntermediateCorner.NE))
    
    NW_check_locations = [(cell_location[0]-1, cell_location[1]), (cell_location[0]-1, cell_location[1]-1), (cell_location[0], cell_location[1]-1)]
    corners_to_check.append((NW_check_locations, IntermediateCorner.NW))
    
    SW_check_locations = [(cell_location[0]+1, cell_location[1]), (cell_location[0]+1, cell_location[1]-1), (cell_location[0], cell_location[1]-1)]
    corners_to_check.append((SW_check_locations, IntermediateCorner.SW))
    
    SE_check_locations = [(cell_location[0]+1, cell_location[1]), (cell_location[0]+1, cell_location[1]+1), (cell_location[0], cell_location[1]+1)]
    corners_to_check.append((SE_check_locations, IntermediateCorner.SE))
    
    for ctc in corners_to_check:
        all_corners_lte = True
        for cl in ctc[0]:
            if cl[0] >= 0 and cl[0] < raster.shape[0] and cl[1] >= 0 and cl[1] < raster.shape[1]:
                if raster[cl] > lte:
                    all_corners_lte = False
                
        if all_corners_lte:
            corners_match.append(ctc[1])
    
    return corners_match