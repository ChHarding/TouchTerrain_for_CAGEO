import numpy as np

# Mostly math functions generated from Gemini

def sign(p1: tuple[float, ...], p2: tuple[float, ...], p3: tuple[float, ...]):
    """Calculates the signed area of the triangle formed by p1, p2, and p3.
    A positive value indicates p3 is to the left of the vector p1p2.
    A negative value indicates p3 is to the right.
    Zero indicates p3 is collinear with p1p2.
    """
    # Calculate 2D cross product (determinant) of 2x2 matrix
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])

def is_point_in_triangle(p: tuple[float, ...], triangle: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]):
    """Checks if a point p is inside the triangle defined by the tuple."""
    s1 = sign(triangle[0], triangle[1], p)
    s2 = sign(triangle[1], triangle[2], p)
    s3 = sign(triangle[2], triangle[0], p)

    # All signs must be the same (or zero for points on edges)
    # to be inside the triangle.
    has_neg = (s1 < 0) or (s2 < 0) or (s3 < 0)
    has_pos = (s1 > 0) or (s2 > 0) or (s3 > 0)

    return not (has_neg and has_pos)

def interpolate_Z_on_3_point_plane(p1, p2, p3, p_new):
    """
    Interpolates the Z-value of a new point (x_new, y_new) 
    on the plane defined by three non-collinear points.

    Args:
        p1 (tuple/list/np.array): (x1, y1, z1) of the first point.
        p2 (tuple/list/np.array): (x2, y2, z2) of the second point.
        p3 (tuple/list/np.array): (x3, y3, z3) of the third point.
        p_new (tuple/list/np.array): (x_new, y_new) of the point to interpolate.

    Returns:
        float: The interpolated Z-value (z_new).
    """

    # 1. Separate coordinates (x, y) and values (z)
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    x3, y3, z3 = p3
    x_new, y_new = p_new
    
    # 2. Define the matrix M (the coordinate matrix) and the vector Z
    # M represents the system of equations: M * [A, B, C] = Z
    
    # M = | x1 y1 1 |
    #     | x2 y2 1 |
    #     | x3 y3 1 |
    M = np.array([
        [x1, y1, 1],
        [x2, y2, 1],
        [x3, y3, 1]
    ])
    
    # Z = | z1 |
    #     | z2 |
    #     | z3 |
    Z = np.array([z1, z2, z3])

    # 3. Solve for the coefficients [A, B, C]
    # np.linalg.solve(M, Z) finds the solution vector X such that M @ X = Z
    try:
        coefficients = np.linalg.solve(M, Z)
    except np.linalg.LinAlgError:
        # This occurs if the determinant is zero (points are collinear or identical)
        raise ValueError("Error: The three points are collinear or identical and do not define a unique plane.")

    A, B, C = coefficients

    # 4. Interpolate the new point using the plane equation: z_new = A*x_new + B*y_new + C
    z_new = A * x_new + B * y_new + C
    
    # Optional: Print the plane equation for reference
    # print(f"Plane Equation: Z = {A:.4f} * X + {B:.4f} * Y + {C:.4f}")

    return z_new

# # --- Example Usage ---
# # Known points (x, y, z)
# point1 = (1.0, 1.0, 5.0)  # P1
# point2 = (5.0, 1.0, 10.0) # P2
# point3 = (3.0, 5.0, 7.0)  # P3

# # New point (x, y) to interpolate
# new_point = (3.0, 3.0) 

# # Perform the interpolation
# z_interpolated = interpolate_Z_on_3_point_plane(point1, point2, point3, new_point)

# if z_interpolated is not None:
#     print(f"\nCoordinates of the new point: ({new_point[0]}, {new_point[1]})")
#     print(f"The interpolated Z-value is: {z_interpolated:.4f}")
    
# # Expected output for this example is 7.5

import shapely
import numpy as np
from typing import List, Union

def interpolate_z_planar(
    geometry_2d: shapely.Geometry, 
    planes_3d: List[shapely.geometry.Polygon]
) -> shapely.Geometry:
    """
    Interpolates the Z-dimension onto a 2D Shapely geometry based on 
    containment within a list of 3D Shapely polygons. The Z value is 
    interpolated using the plane equation defined by the first three 
    vertices of the containing 3D polygon.

    Args:
        geometry_2d: The 2D Shapely geometry (Point, LineString, Polygon, etc.).
        planes_3d: A list of 3D Shapely Polygon objects.

    Returns:
        The new 3D Shapely geometry (same type as input).

    Raises:
        ValueError: If any point in the 2D geometry is not contained, if 
                    polygons are not 3D, or if the first three points are collinear.
    """

    # --- Helper function to get the interpolated Z value ---
    def get_interpolated_z(point_2d: shapely.geometry.Point) -> float:
        """Finds the containing 3D polygon and returns the interpolated Z."""
        
        interpolating_poly: shapely.Polygon = None
        
        for poly_3d in planes_3d:
            # Check for 2D containment or intersection along an exterior edge (ignores Z)
            if point_2d.intersects(poly_3d):
                interpolating_poly = poly_3d
                
        
        # If loop completes without getting an intersecting polygon, the point is outside all polygons
        
        # Pick the plane with the closest exterior or interior ring to interpolate off of
        if interpolating_poly is None:
            distance_to_closest_poly_boundary = float('inf')
            for poly_3d in planes_3d:
                distance_to_poly_boundary = poly_3d.boundary.distance(point_2d)
                if distance_to_poly_boundary < distance_to_closest_poly_boundary:
                    distance_to_closest_poly_boundary = distance_to_poly_boundary
                    interpolating_poly = poly_3d
        
        if interpolating_poly is None:
            raise ValueError(f"Point {point_2d.wkt} is not within any of the provided 3D polygons and could not get distance to polygon boundaries.")
        
        coords_3d = interpolating_poly.exterior.coords
                
        # Check if polygon is 3 unique points (4th point should close the polygon)
        if len(coords_3d) != 4 or len(coords_3d[0]) < 3:
            raise ValueError(
                f"Polygon {planes_3d.index(interpolating_poly)} must have 3 vertices and be 3D."
            )
        
        # Use the first three unique vertices to define the plane
        P1 = np.array(coords_3d[0][:3])
        P2 = np.array(coords_3d[1][:3])
        P3 = np.array(coords_3d[2][:3])
        
        # Calculate two vectors lying on the plane
        V1 = P2 - P1
        V2 = P3 - P1
        
        # Calculate the Normal Vector (A, B, C) using the cross product
        Normal_Vector = np.cross(V1, V2)
        A, B, C = Normal_Vector[0], Normal_Vector[1], Normal_Vector[2]

        # Check for near-zero C (This means the plane is near-vertical)
        if abs(C) < 1e-6:
            raise ValueError(
                "The plane defined by the first three points is near-vertical or collinear. Cannot uniquely solve for Z."
            )
        
        # Plane Equation: A(x - x0) + B(y - y0) + C(z - z0) = 0
        # Solving for z:
        # z = z0 - (A/C)*(x - x0) - (B/C)*(y - y0)
        
        x_p, y_p = point_2d.x, point_2d.y
        x0, y0, z0 = P1[0], P1[1], P1[2]
        
        new_z = z0 - (A / C) * (x_p - x0) - (B / C) * (y_p - y0)
        
        return float(new_z)


    # --- Function to handle the interpolation based on geometry type ---
    if isinstance(geometry_2d, shapely.geometry.Point):
        # 1. Handle Point
        new_z = get_interpolated_z(geometry_2d)
        new_coords = (geometry_2d.x, geometry_2d.y, new_z)
        return shapely.geometry.Point(new_coords)

    elif isinstance(geometry_2d, (shapely.geometry.LineString, shapely.geometry.LinearRing)):
        # 2. Handle LineString or LinearRing
        new_coords = []
        for x, y in geometry_2d.coords:
            point_2d = shapely.geometry.Point(x, y)
            new_z = get_interpolated_z(point_2d)
            new_coords.append((x, y, new_z))
        
        if isinstance(geometry_2d, shapely.geometry.LineString):
            return shapely.geometry.LineString(new_coords)
        else: # LinearRing
            return shapely.geometry.LinearRing(new_coords)
    
    elif isinstance(geometry_2d, shapely.geometry.Polygon):
        # 3. Handle Polygon
        
        # A. Process Exterior Ring
        exterior_coords_3d = []
        for x, y in geometry_2d.exterior.coords:
            point_2d = shapely.geometry.Point(x, y)
            new_z = get_interpolated_z(point_2d)
            exterior_coords_3d.append((x, y, new_z))

        # B. Process Interior Rings (Holes)
        interior_coords_3d_list = []
        for interior_ring in geometry_2d.interiors:
            hole_coords_3d = []
            for x, y in interior_ring.coords:
                point_2d = shapely.geometry.Point(x, y)
                new_z = get_interpolated_z(point_2d)
                hole_coords_3d.append((x, y, new_z))
            interior_coords_3d_list.append(hole_coords_3d)

        # Recreate the 3D Polygon
        return shapely.geometry.Polygon(exterior_coords_3d, interior_coords_3d_list)
    
    elif isinstance(geometry_2d, shapely.geometry.MultiPolygon):
        # 4. Handle MultiPolygon (NEW)
        
        new_polygons = []
        # Iterate over the constituent Polygons in the MultiPolygon
        for polygon_2d in geometry_2d.geoms:
            # Recursively call the function for each Polygon
            # The result is a 3D Polygon
            polygon_3d = interpolate_z_planar(polygon_2d, planes_3d)
            new_polygons.append(polygon_3d)
            
        # Combine the new 3D Polygons into a 3D MultiPolygon
        return shapely.geometry.MultiPolygon(new_polygons)

    else:
        # 4. Handle unsupported types
        raise TypeError(f"Unsupported geometry type: {type(geometry_2d).__name__}")