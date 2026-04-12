import shapely
from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.Quad import quad

from touchterrain.common.shapely_polygon_utils import get_polygon_coordinates_as_tuples, create_polygon_from_modified_coords
from touchterrain.common.interpolate_Z import is_point_in_triangle, interpolate_Z_on_3_point_plane

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
            flat_list.extend(flatten_geometries_borderEdge(geom.geoms, polygon_parent=polygon_parent))
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