import shapely
from touchterrain.common.Vertex import vertex

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