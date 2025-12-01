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