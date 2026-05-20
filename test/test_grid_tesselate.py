import unittest

from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.grid_tesselate import make_wall_without_exact_duplicate_vertices


class TestWallMeshes(unittest.TestCase):
    def test_wall_with_no_duplicate_vertices_stays_quad(self):
        wall = make_wall_without_exact_duplicate_vertices(
            vertex(0, 0, 0),
            vertex(0, 0, 1),
            vertex(1, 0, 1),
            vertex(1, 0, 0),
        )

        self.assertIsInstance(wall, quad)
        self.assertIsNotNone(wall.vl[3])

    def test_wall_with_one_exact_duplicate_endpoint_becomes_triangle(self):
        wall = make_wall_without_exact_duplicate_vertices(
            vertex(0, 0, 0),
            vertex(0, 0, 0),
            vertex(1, 0, 1),
            vertex(1, 0, 0),
        )

        self.assertIsInstance(wall, quad)
        self.assertIsNone(wall.vl[3])
        self.assertEqual([v.coords for v in wall.vl[:3]], [(0.0, 0.0, 0.0), (1.0, 0.0, 1.0), (1.0, 0.0, 0.0)])

    def test_wall_with_both_exact_duplicate_endpoints_is_omitted(self):
        wall = make_wall_without_exact_duplicate_vertices(
            vertex(0, 0, 0),
            vertex(0, 0, 0),
            vertex(1, 0, 1),
            vertex(1, 0, 1),
        )

        self.assertIsNone(wall)

    def test_wall_with_nonadjacent_exact_duplicate_endpoint_becomes_triangle(self):
        wall = make_wall_without_exact_duplicate_vertices(
            vertex(0, 0, 1),
            vertex(1, 0, 1),
            vertex(0, 0, 1),
            vertex(1, 0, 0),
        )

        self.assertIsInstance(wall, quad)
        self.assertIsNone(wall.vl[3])
        self.assertEqual([v.coords for v in wall.vl[:3]], [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 0.0)])
