import shapely
from typing import List, Dict, Union
from touchterrain.common.Vertex import vertex

import numpy as np

from shapely.ops import orient


def polygons_equal_3d(a: shapely.Polygon, b: shapely.Polygon, tol=1e-9) -> bool:
    # Same 2D footprint
    if not a.equals(b):
        return False

    # Normalize winding so clockwise/counterclockwise match
    a, b = orient(a, sign=1.0), orient(b, sign=1.0)

    # Helper to normalize rings (start position doesn’t matter; orientation is preserved by equals)
    def ring_coords(poly):
        return [np.array(poly.exterior.coords), *[np.array(r.coords) for r in poly.interiors]]

    rings_a, rings_b = ring_coords(a), ring_coords(b)
    if len(rings_a) != len(rings_b):
        return False

    for ra, rb in zip(rings_a, rings_b):
        if ra.shape != rb.shape:
            return False
        # Rotate rb so its first point matches ra’s first point (within tolerance)
        diffs = np.linalg.norm(rb[:, :2] - ra[0, :2], axis=1)
        start = int(np.argmin(diffs))
        rb_rot = np.concatenate([rb[start:], rb[:start]], axis=0)
        if not (np.allclose(ra[:, :2], rb_rot[:, :2], atol=tol) and
                np.allclose(ra[:, 2], rb_rot[:, 2], atol=tol)):
            return False
    return True

def get_polygon_coordinates_as_tuples(polygon: shapely.Polygon) -> list[tuple[float,...]]:
    """
    Extracts all coordinate points of a Shapely Polygon
    (exterior and interior rings) and returns them as a
    list of Python tuples.

    Args:
        polygon: A shapely.geometry.Polygon object.

    Returns:
        A list where each element is a tuple (x, y) representing a
        vertex coordinate of the polygon's exterior or interior rings.
    """
    if not isinstance(polygon, shapely.Polygon):
        raise TypeError("Input must be a shapely.geometry.Polygon object.")

    # List to store all coordinates as tuples
    all_coords_as_tuples = []

    # 1. Process the EXTERIOR ring
    # polygon.exterior.coords returns a CoordinateSequence
    exterior_coords = list(polygon.exterior.coords)
    # Convert each (x, y) pair in the list to a tuple
    all_coords_as_tuples.extend([tuple(coord) for coord in exterior_coords])

    # 2. Process the INTERIOR rings (holes)
    # polygon.interiors is an iterable of LinearRings
    for interior_ring in polygon.interiors:
        interior_coords = list(interior_ring.coords)
        # Convert each (x, y) pair in the list to a tuple
        all_coords_as_tuples.extend([tuple(coord) for coord in interior_coords])

    return all_coords_as_tuples

def polygon_to_list_of_vertex(polygon: shapely.Polygon) -> list[vertex]:
    if not isinstance(polygon, shapely.Polygon):
        raise TypeError("Input must be a shapely.geometry.Polygon object.")

    if len(polygon.interiors) > 0:
        raise ValueError(f"polygon_to_list_of_vertex found interior structure but it only supports exterior structures.")

    # List to store all coordinates as tuples
    all_coords_as_vertex: list[vertex] = []

    # 1. Process the EXTERIOR ring
    # polygon.exterior.coords returns a CoordinateSequence
    exterior_coords = list(polygon.exterior.coords)
    for c in exterior_coords:
        all_coords_as_vertex.append(vertex(x=c[0], y=c[1], z=c[2]))
        
    return all_coords_as_vertex

def create_polygon_from_modified_coords(original_polygon: shapely.Polygon, all_coords_as_tuples: list) -> shapely.Polygon:
    """
    Reconstructs a new Shapely Polygon from a flat list of modified coordinates,
    maintaining the structure of the original polygon (exterior and holes).

    Args:
        original_polygon: The original shapely.geometry.Polygon object.
        all_coords_as_tuples: A flat list of (x, y) tuples representing the
                              modified coordinates for both the exterior and
                              all interior rings, in the same order as they
                              were extracted.

    Returns:
        A new shapely.geometry.Polygon object.
    """
    if not isinstance(original_polygon, shapely.Polygon):
        raise TypeError("Input must be a shapely.geometry.Polygon object.")

    # 1. Determine the length of the original exterior ring
    exterior_len = len(original_polygon.exterior.coords)

    # 2. Extract the new exterior coordinates
    # The first 'exterior_len' items in the flat list belong to the exterior.
    new_exterior_coords = all_coords_as_tuples[:exterior_len]

    # 3. Extract the new interior coordinates (holes)
    new_interior_rings = []
    
    # Start the index after the exterior coordinates
    current_index = exterior_len

    # Iterate through the original interior rings to get their lengths
    for interior_ring in original_polygon.interiors:
        # Get the length of the current original hole
        interior_len = len(interior_ring.coords)
        
        # Slice the flat coordinate list to get the points for this new hole
        hole_coords = all_coords_as_tuples[current_index : current_index + interior_len]
        
        # Add the list of hole coordinates to the interior rings list
        new_interior_rings.append(hole_coords)
        
        # Move the index forward for the next hole
        current_index += interior_len

    # 4. Create the new Polygon
    # Shapely Polygon constructor is Polygon(exterior, [interior_1, interior_2, ...])
    new_polygon = shapely.Polygon(new_exterior_coords, new_interior_rings)

    return new_polygon

def get_polygon_points(polygon: shapely.geometry.Polygon) -> Dict[str, List[Union[shapely.geometry.Point, List[shapely.geometry.Point]]]]:
    """
    Extracts the coordinates of a Shapely Polygon (including all holes) 
    and returns them as a dictionary of Shapely Point objects.
    """
    if not isinstance(polygon, shapely.geometry.Polygon):
        raise TypeError("Input must be a shapely.geometry.Polygon.")

    # 1. Get Exterior Points
    # Prefix Point with 'shapely.geometry.'
    exterior_points = [shapely.geometry.Point(x, y) for x, y in polygon.exterior.coords]

    # 2. Get Interior Points (Holes)
    interior_points_list = []
    for interior_ring in polygon.interiors:
        # Prefix Point with 'shapely.geometry.'
        hole_points = [shapely.geometry.Point(x, y) for x, y in interior_ring.coords]
        interior_points_list.append(hole_points) 

    return {
        'exterior': exterior_points,
        'interior': interior_points_list
    }

# ---

def recreate_polygon_from_points(points_data: Dict[str, List[Union[shapely.geometry.Point, List[shapely.geometry.Point]]]]) -> shapely.geometry.Polygon:
    """
    Recreates a Shapely Polygon from a dictionary containing exterior and interior 
    ring points (as Shapely Point objects).
    """
    # 1. Extract coordinates for the exterior ring
    try:
        exterior_coords = [(p.x, p.y) for p in points_data['exterior']]
    except (KeyError, AttributeError):
        raise ValueError("Input data must contain a valid 'exterior' key with a list of Point objects.")

    # 2. Extract coordinates for the interior rings (holes)
    interior_coords_list = []
    if points_data.get('interior'):
        for hole_points in points_data['interior']:
            if not isinstance(hole_points, list):
                 raise ValueError("Interior data must be a list of lists of Point objects.")
            
            hole_coords = [(p.x, p.y) for p in hole_points]
            interior_coords_list.append(hole_coords)

    # 3. Create the Polygon
    # Prefix Polygon with 'shapely.geometry.'
    new_polygon = shapely.geometry.Polygon(exterior_coords, interior_coords_list)

    return new_polygon
