import shapely
from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.Quad import quad

def linestring_to_segments(linestring_obj: shapely.LineString) -> list[shapely.LineString]:
    """
    Splits a Shapely LineString into a list of individual LineString segments.

    :param linestring_obj (shapely.geometry.LineString): The input LineString.

    :returns list: A list of individual LineString segments.
    """
    segments = []
    coords = linestring_obj.coords
    for i in range(len(coords) - 1):
        segment = shapely.LineString([coords[i], coords[i+1]])
        segments.append(segment)
    return segments

def flatten_geometries(geometries: list[shapely.Geometry], to_single_lines: bool = False) -> list[shapely.Geometry]:
    """Recursively flatten a list of multi geometries into a list of non-multi geometries.
    Does not keep any point geometries.
    :param geometries: List of shapely.Geometries to flatten
    :param to_single_lines: If geometries should be flattened into single lines (shapely.LineString[1])
    """
    flat_list = []
    for geom in geometries:
        if geom.geom_type.startswith('Multi') or isinstance(geom, shapely.GeometryCollection):
            # For collections, iterate over the individual parts
            flat_list.extend(flatten_geometries(geom.geoms, to_single_lines=to_single_lines))
        # Add simple, non-empty, non-point geometries to the list.
        elif geom.is_empty or isinstance(geom, shapely.Point):
            continue
        if to_single_lines:
            if isinstance(geom, shapely.Polygon):
                flat_list.extend(flatten_geometries([geom.boundary],to_single_lines=to_single_lines))
            elif isinstance(geom, shapely.LineString):
                flat_list.extend(linestring_to_segments(geom))
        else:
            flat_list.append(geom)
        
    return flat_list

def flatten_geometries_borderEdge(geometries: list[shapely.Geometry], polygon_parent: bool = False) -> list[BorderEdge]:
    """Recursively flatten a list of multi geometries into a list of line segment as BorderEdge.
    :param geometries: List of shapely.Geometries to flatten
    :param polygon_parent: If the geometries are part of a polygon
    """
    flat_list: list[BorderEdge] = []
    for geom in geometries:
        if geom.geom_type.startswith('Multi') or isinstance(geom, shapely.GeometryCollection):
            # For collections, iterate over the individual parts
            flat_list.extend(flatten_geometries_borderEdge(geom.geoms))
        elif geom.is_empty or isinstance(geom, shapely.Point):
            continue
        if isinstance(geom, shapely.Polygon):
            flat_list.extend(flatten_geometries_borderEdge([geom.boundary], polygon_parent=True))
        elif isinstance(geom, shapely.LineString):
            for ls in linestring_to_segments(geom):
                be = BorderEdge(geometry=ls, polygon_line=polygon_parent)
                flat_list.append(be)
        
    return flat_list

def sort_line_segment_based_contains(line_segment: BorderEdge, north: shapely.LineString, west: shapely.LineString, south: shapely.LineString, east: shapely.LineString) -> tuple[str, bool]:
    """_summary_

    :param line_segment: Border Edge with a LineString to check if the N W S E LineStrings contain it.
    :return: The bucket key to store it in: N W S E other and whether the line segment lies on a cardinal edge.
    :rtype: (str, bool)
    """
    if north.contains(line_segment.geometry):
        return ('N', True)
    if west.contains(line_segment.geometry):
        return ('W', True)
    if south.contains(line_segment.geometry):
        return ('S', True)
    if east.contains(line_segment.geometry):
        return ('E', True)
    
    return ('other', False)

def get_polygon_coordinates_as_tuples(polygon: shapely.Polygon) -> list:
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

def interpolate_polygon_with_quad(polygon: shapely.Polygon, quad: quad) -> shapely.Polygon:
    pass