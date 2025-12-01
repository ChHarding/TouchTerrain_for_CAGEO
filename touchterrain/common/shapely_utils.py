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

def interpolate_geometry_with_quad(geometry: shapely.Geometry, quad: quad, split_rotation = 0) -> shapely.Geometry:
    """_summary_

    :param geometry: Geometry with 2D coordinates
    :type geometry: shapely.Geometry
    :param quad: Quad with vertices with Z info. The interpolation will be along the planes made by the quad tris.
    :type quad: quad
    :return: Geometry with 3D coordinates. Z is interpolated relative to the quad
    :rtype: shapely.Geometry
    """
    
    quad_tris_in_tuple_float: list[tuple[tuple[float, ...], ...]] = quad.get_triangles_in_tuple_float(split_rotation=split_rotation)
    
    def interpolate_coord(c:tuple[float,...], planes_3D: list[tuple[tuple[float, ...], ...]])->tuple[float,...] | bool:
        if len(c) != 2:
            raise TypeError(f"Found polygon coord to interpolate that does not have 2 dimensions. It had len of {len(c)}")
        for tri in planes_3D:
            if len(tri) == 3:
                if is_point_in_triangle(p=c, triangle=tri):
                    cz = interpolate_Z_on_3_point_plane(tri[0], tri[1], tri[2], c)
                    return (c[0], c[1], cz)
            else:
                raise TypeError(f"Found quad tri that does not have 3 vertices. It has len of {len(tri)}")
        return False
    
    if isinstance(geometry, shapely.Polygon):
        polygon_coords = get_polygon_coordinates_as_tuples(polygon=geometry)
        interpolated_polygon_coords = []
            
        for c in polygon_coords:
            ic = interpolate_coord(c, planes_3D=quad_tris_in_tuple_float)
            if ic == False:
                raise ValueError(f"Polygon coord {c} is not in {quad_tris_in_tuple_float}")
            interpolated_polygon_coords.append(ic)
        
        return create_polygon_from_modified_coords(original_polygon=geometry, all_coords_as_tuples=interpolated_polygon_coords)
    elif isinstance(geometry, shapely.LineString):
        lineString_coords = list(geometry.coords)
        interpolated_lineString_coords = []
        for c in lineString_coords:
            ic = interpolate_coord(c, planes_3D=quad_tris_in_tuple_float)
            if ic == False:
                raise ValueError(f"Polygon coord {c} is not in {quad_tris_in_tuple_float}")
            interpolated_lineString_coords.append(ic)
        return shapely.LineString(interpolated_lineString_coords)
    else:
        raise ValueError(f"geometry is unsupported provided type was {type(geometry)}")