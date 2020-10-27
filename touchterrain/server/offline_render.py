import open3d as o3d
import numpy as np
mesh = o3d.io.read_triangle_mesh("terrain.stl")
mesh.compute_vertex_normals()
#o3d.visualization.draw_geometries([mesh])

vis = o3d.visualization.Visualizer()
vis.create_window()
vis.add_geometry(mesh)
vis.update_renderer()
vis.capture_screen_image("render_test.jpg")

