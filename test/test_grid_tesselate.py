import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import shapely

import touchterrain.common.grid_tesselate as grid_tesselate
import touchterrain.common.mesh_serialization as mesh_serialization
import touchterrain.common.raster_interpolation as raster_interpolation
from touchterrain.common.mesh_serialization import (
    _boundary_line_map_by_serialized_xy,
    _canonicalize_clipped_triangles_by_serialized_xy,
    _line_serialized_xy_signature,
    _line_with_serialized_xy,
    boundary_edge_map_from_meshes,
    directed_edges_are_balanced,
    edge_3d_signature,
    edge_xy_signature,
    normalize_vertex_to_match_mesh_serialization,
    surface_mesh_edge_counts,
    surface_mesh_edge_usage,
)
from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.interpolate_Z import interpolate_z_planar
from touchterrain.common.nudge_corner import IntermediateCorner
from touchterrain.common.Quad import quad
from touchterrain.common.Vertex import vertex
from touchterrain.common.grid_tesselate import grid
from touchterrain.common.Cell import cell
from touchterrain.common.mesh_vocabulary import single_job_parallel_workers
from touchterrain.common.nudge_plan import (
    _positive_z_difference_neighbor_split_sides,
    _positive_z_effective_difference_corners,
    _positive_z_nudge_corners_from_values,
    build_positive_z_nudge_plan,
    filter_positive_z_nudge_plan_to_actual_overused_edges,
)
from touchterrain.common.nudge_geometry import (
    _nudge_split_side_endpoint_edges,
    _nudge_split_side_endpoint_xy,
    _surface_polygons_with_midpoint_z,
    _z0_adjusted_keep_surface_planes,
    full_cell_footprint,
    nudge_keep_footprint,
)
from touchterrain.common.surface_geometry import (
    _rebuild_matching_surface_polygon_borders,
    _triangulate_2d_geometry_to_3d_polygons,
    make_wall_without_exact_duplicate_vertices,
)


def _polygon_footprint_area(polygons):
    return shapely.union_all(
        [shapely.force_2d(polygon) for polygon in polygons]
    ).area


class TestWallMeshes(unittest.TestCase):
    def test_adjacent_walls_convert_cell_without_copying_source_quads(self):
        top = quad(
            vertex(0, 1, 1),
            vertex(0, 0, 2),
            vertex(1, 0, 3),
            vertex(1, 1, 4),
        )
        bottom = quad(
            vertex(0, 1, 0),
            vertex(1, 1, 0),
            vertex(1, 0, 0),
            vertex(0, 0, 0),
        )
        north_wall = quad(
            bottom.vl[0],
            top.vl[0],
            top.vl[3],
            bottom.vl[1],
        )
        west_wall = quad(
            top.vl[1],
            top.vl[0],
            bottom.vl[0],
            bottom.vl[3],
        )
        current_cell = cell(
            top,
            bottom,
            {"N": north_wall, "W": west_wall},
        )

        self.assertTrue(current_cell.check_for_tri_cell())
        current_cell.convert_to_tri_cell()

        self.assertTrue(current_cell.is_tri_cell)
        self.assertEqual(
            [mesh_vertex.coords for mesh_vertex in current_cell.topquad.vl[:3]],
            [top.vl[3].coords, top.vl[1].coords, top.vl[2].coords],
        )
        self.assertEqual(set(current_cell.borders), {"N"})
        self.assertFalse(current_cell.check_for_tri_cell())

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

    def test_rebuild_clipped_wall_splits_surface_boundary_edges(self):
        fileformat = "STLb"
        top_surfaces = [
            shapely.Polygon(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 2.0),
                    (0.0, 1.0, 1.2),
                    (0.0, 0.0, 1.0),
                ]
            )
        ]
        bottom_surfaces = [
            shapely.Polygon(
                [
                    (0.0, 0.0, 0.0),
                    (0.5, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 0.0),
                ]
            ),
            shapely.Polygon(
                [
                    (0.5, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.5, 0.0, 0.0),
                ]
            ),
        ]
        requested = shapely.LineString([(0.0, 0.0), (1.0, 0.0)])

        walls = _rebuild_matching_surface_polygon_borders(
            top_surfaces,
            bottom_surfaces,
            lambda footprint: requested.covers(shapely.LineString(footprint)),
            fileformat,
        )

        expected_footprints = {
            edge_xy_signature((0.0, 0.0, 0.0), (0.5, 0.0, 0.0)),
            edge_xy_signature((0.5, 0.0, 0.0), (1.0, 0.0, 0.0)),
        }
        self.assertEqual(len(walls), 2)
        self.assertTrue(
            expected_footprints.issubset(
                set(
                    boundary_edge_map_from_meshes(
                        top_surfaces,
                        output_fileformat=fileformat,
                    )
                )
            )
        )
        self.assertTrue(
            expected_footprints.issubset(
                set(
                    boundary_edge_map_from_meshes(
                        bottom_surfaces,
                        output_fileformat=fileformat,
                    )
                )
            )
        )
        wall_footprints = {
            edge_xy_signature(wall.vl[0].coords, wall.vl[1].coords)
            for wall in walls
        }
        self.assertEqual(wall_footprints, expected_footprints)


class TestSerializedSurfaceCleanup(unittest.TestCase):
    def test_clipped_triangles_share_canonical_serialized_xy_before_z(self):
        triangles = [
            shapely.Polygon(
                [
                    (0.0, 0.0),
                    (1.0000001, 0.0),
                    (0.0, 1.0),
                    (0.0, 0.0),
                ]
            ),
            shapely.Polygon(
                [
                    (1.0000004, 0.0),
                    (1.0, 1.0),
                    (0.0, 1.0),
                    (1.0000004, 0.0),
                ]
            ),
        ]

        canonical = _canonicalize_clipped_triangles_by_serialized_xy(
            triangles,
            "STLb",
        )

        xy_by_serialized = {}
        for triangle in canonical:
            for coord in triangle.exterior.coords[:-1]:
                key = normalize_vertex_to_match_mesh_serialization(
                    (coord[0], coord[1], 0.0),
                    "STLb",
                )[:2]
                xy_by_serialized.setdefault(key, set()).add(coord[:2])

        self.assertEqual(len(canonical), 2)
        self.assertEqual(len(xy_by_serialized[(1.0, 0.0)]), 1)
        self.assertIn((1.0, 1.0), xy_by_serialized[(1.0, 1.0)])

    def test_clipped_canonicalization_removes_duplicate_serialized_xy_z(self):
        triangles = _canonicalize_clipped_triangles_by_serialized_xy(
            [
                shapely.Polygon(
                    [
                        (0.0, 0.0),
                        (1.0000001, 0.0),
                        (0.0, 1.0),
                        (0.0, 0.0),
                    ]
                ),
                shapely.Polygon(
                    [
                        (1.0000004, 0.0),
                        (1.0, 1.0),
                        (0.0, 1.0),
                        (1.0000004, 0.0),
                    ]
                ),
            ],
            "STLb",
        )
        steep_plane = shapely.Polygon(
            [
                (0.0, 0.0, 0.0),
                (2.0, 0.0, 200000.0),
                (0.0, 2.0, 0.0),
                (0.0, 0.0, 0.0),
            ]
        )

        z_by_xy = {}
        for triangle in triangles:
            triangle_3d = interpolate_z_planar(
                shapely.orient_polygons(triangle, exterior_cw=False),
                [steep_plane],
            )
            normalized = mesh_serialization.polygon_normalized_to_match_mesh_serialization(
                triangle_3d,
                "STLb",
            )
            self.assertIsNotNone(normalized)
            for coord in normalized.exterior.coords[:-1]:
                z_by_xy.setdefault(coord[:2], set()).add(coord[2])

        self.assertEqual(len(z_by_xy[(1.0, 0.0)]), 1)

    def test_clipped_wall_edges_match_by_serialized_xy(self):
        raw_clip_edge = shapely.LineString(
            [(0.0, 0.0), (1.0000004, 0.0)]
        )
        canonical_surface_edge = shapely.LineString(
            [(0.0, 0.0, 0.0), (1.0000001, 0.0, 1.0)]
        )
        bottom_surface_edge = shapely.LineString(
            [(0.0, 0.0, 0.0), (1.0000001, 0.0, 0.0)]
        )

        self.assertEqual(
            _line_serialized_xy_signature(raw_clip_edge, "STLb"),
            _line_serialized_xy_signature(canonical_surface_edge, "STLb"),
        )
        wall = make_wall_without_exact_duplicate_vertices(
            vertex(*canonical_surface_edge.coords[1]),
            vertex(*canonical_surface_edge.coords[0]),
            vertex(*bottom_surface_edge.coords[1]),
            vertex(*bottom_surface_edge.coords[0]),
            output_fileformat="STLb",
        )

        self.assertIsNotNone(wall)

    def test_boundary_line_map_omits_internal_serialized_edges(self):
        boundary_edge = shapely.LineString(
            [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0)]
        )
        internal_edge = shapely.LineString(
            [(0.0, 0.5, 1.0), (1.0, 0.5, 1.0)]
        )

        edge_map = _boundary_line_map_by_serialized_xy(
            [boundary_edge, internal_edge, internal_edge],
            "STLb",
        )

        self.assertIn(
            _line_serialized_xy_signature(boundary_edge, "STLb"),
            edge_map,
        )
        self.assertNotIn(
            _line_serialized_xy_signature(internal_edge, "STLb"),
            edge_map,
        )

    def test_triangulate_helper_can_canonicalize_clipped_xy(self):
        geometry = shapely.MultiPolygon(
            [
                shapely.Polygon(
                    [
                        (0.0, 0.0),
                        (1.0000001, 0.0),
                        (0.0, 1.0),
                        (0.0, 0.0),
                    ]
                ),
                shapely.Polygon(
                    [
                        (1.0000004, 0.0),
                        (1.0, 1.0),
                        (0.0, 1.0),
                        (1.0000004, 0.0),
                    ]
                ),
            ]
        )
        steep_plane = shapely.Polygon(
            [
                (0.0, 0.0, 0.0),
                (2.0, 0.0, 200000.0),
                (0.0, 2.0, 0.0),
                (0.0, 0.0, 0.0),
            ]
        )

        polygons = _triangulate_2d_geometry_to_3d_polygons(
            geometry,
            [steep_plane],
            exterior_cw=False,
            output_fileformat="STLb",
            canonicalize_serialized_xy=True,
        )

        z_by_xy = {}
        for polygon in polygons:
            for coord in polygon.exterior.coords[:-1]:
                z_by_xy.setdefault(coord[:2], set()).add(coord[2])

        self.assertEqual(len(z_by_xy[(1.0, 0.0)]), 1)

    def test_clipped_wall_border_can_cover_split_surface_edges(self):
        raw_clip_edge = shapely.LineString(
            [(0.0, 0.0), (1.0000004, 0.0)]
        )
        border_line = _line_with_serialized_xy(raw_clip_edge, "STLb")
        self.assertIsNotNone(border_line)
        split_surface_edges = [
            shapely.LineString([(0.0, 0.0, 1.0), (0.5, 0.0, 1.5)]),
            shapely.LineString([(0.5, 0.0, 1.5), (1.0000001, 0.0, 2.0)]),
        ]

        for edge in split_surface_edges:
            edge_key = _line_serialized_xy_signature(edge, "STLb")
            self.assertIsNotNone(edge_key)
            self.assertTrue(
                border_line.covers(
                    shapely.LineString([edge_key[0], edge_key[1]])
                )
            )

    def test_clipped_wall_split_border_linework_covers_surface_edge(self):
        raw_clip_edges = [
            shapely.LineString([(0.0, 0.0), (0.5, 0.0)]),
            shapely.LineString([(0.5, 0.0), (1.0000004, 0.0)]),
        ]
        border_linework = shapely.union_all(
            [
                _line_with_serialized_xy(raw_clip_edge, "STLb")
                for raw_clip_edge in raw_clip_edges
            ]
        )
        surface_edge_key = _line_serialized_xy_signature(
            shapely.LineString(
                [(0.0, 0.0, 1.0), (1.0000001, 0.0, 1.5)]
            ),
            "STLb",
        )
        self.assertIsNotNone(surface_edge_key)

        self.assertTrue(
            border_linework.covers(
                shapely.LineString(
                    [surface_edge_key[0], surface_edge_key[1]],
                )
            )
        )

    def test_positive_z_midpoint_override_wins_after_clipped_canonicalization(self):
        canonical = _canonicalize_clipped_triangles_by_serialized_xy(
            [
                shapely.Polygon(
                    [
                        (0.0, 0.0, 1.0),
                        (0.5000001, 0.0, 2.0),
                        (0.0, 1.0, 3.0),
                        (0.0, 0.0, 1.0),
                    ]
                ),
                shapely.Polygon(
                    [
                        (0.5000004, 0.0, 4.0),
                        (1.0, 0.0, 5.0),
                        (1.0, 1.0, 6.0),
                        (0.5000004, 0.0, 4.0),
                    ]
                ),
            ],
            "STLb",
        )
        surfaces = [
            shapely.Polygon([
                *[
                    (*coord[:2], float(index + 1))
                    for index, coord in enumerate(
                        triangle.exterior.coords[:-1],
                    )
                ],
                (*triangle.exterior.coords[0][:2], 1.0),
            ])
            for triangle in canonical
        ]

        adjusted = _surface_polygons_with_midpoint_z(
            surfaces,
            W=0.0,
            E=1.0,
            N=1.0,
            S=0.0,
            midpoint_corner_vertices=None,
            output_fileformat="STLb",
            midpoint_z_by_name={"Smid": 9.0},
        )

        smid_z = set()
        for polygon in adjusted:
            for coord in polygon.exterior.coords[:-1]:
                normalized = normalize_vertex_to_match_mesh_serialization(
                    coord,
                    "STLb",
                )
                if normalized[:2] == (0.5, 0.0):
                    smid_z.add(normalized[2])

        self.assertEqual(smid_z, {9.0})

    def test_removes_surface_triangle_with_serialized_xy_line(self):
        current_cell = cell(
            quad(
                vertex(0.0, 0.0, 1.0),
                vertex(0.0, 1.0, 1.0),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
            ),
            quad(
                vertex(0.0, 0.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(0.0, 1.0, 0.0),
            ),
            {},
        )
        current_cell.topSurfacePolygons = [
            shapely.Polygon(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 2.0),
                    (0.5, 0.0, 1.5),
                    (0.0, 0.0, 1.0),
                ]
            )
        ]

        current_cell.remove_geometry_collapsed_by_mesh_serialization(
            output_fileformat="STLb",
            split_rotation=0,
        )

        self.assertIsNone(current_cell.topSurfacePolygons)
        self.assertIsNone(current_cell.topquad)
        self.assertIsNone(current_cell.bottomquad)

    def test_keeps_surface_triangle_with_serialized_xy_area(self):
        current_cell = cell(
            quad(
                vertex(0.0, 0.0, 1.0),
                vertex(0.0, 1.0, 1.0),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
            ),
            None,
            {},
        )
        current_cell.topSurfacePolygons = [
            shapely.Polygon(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 1.2),
                    (0.0, 1.0, 1.4),
                    (0.0, 0.0, 1.0),
                ]
            )
        ]

        current_cell.remove_geometry_collapsed_by_mesh_serialization(
            output_fileformat="STLb",
            split_rotation=0,
        )

        self.assertEqual(len(current_cell.topSurfacePolygons), 1)

    def test_keeps_vertical_wall_with_serialized_xy_line(self):
        current_cell = cell(
            quad(
                vertex(0.0, 0.0, 1.0),
                vertex(0.0, 1.0, 1.0),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
            ),
            None,
            {},
        )
        current_cell.surfacePolygonBorders = [
            quad(
                vertex(0.0, 0.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            )
        ]

        current_cell.remove_geometry_collapsed_by_mesh_serialization(
            output_fileformat="STLb",
            split_rotation=0,
        )

        self.assertEqual(len(current_cell.surfacePolygonBorders), 1)


class TestPositiveZNudge(unittest.TestCase):
    def _positive_difference_cell(self, w, e, n, s, bottom_z_by_corner):
        return cell(
            quad(
                vertex(w, n, 3.0),
                vertex(w, s, 3.0),
                vertex(e, s, 3.0),
                vertex(e, n, 3.0),
            ),
            quad(
                vertex(w, n, bottom_z_by_corner[IntermediateCorner.NW]),
                vertex(e, n, bottom_z_by_corner[IntermediateCorner.NE]),
                vertex(e, s, bottom_z_by_corner[IntermediateCorner.SE]),
                vertex(w, s, bottom_z_by_corner[IntermediateCorner.SW]),
            ),
            {},
        )

    def _wall_with_directed_positive_top_edge(self, start, end):
        return quad(
            vertex(end[0], end[1], end[2]),
            vertex(end[0], end[1], 0.0),
            vertex(start[0], start[1], 0.0),
            vertex(start[0], start[1], start[2]),
        )

    def _positive_z_loop_cell(self, directed_top_edges):
        current_cell = cell(
            None,
            None,
            {},
        )
        current_cell.surfacePolygonBorders = [
            self._wall_with_directed_positive_top_edge(start, end)
            for start, end in directed_top_edges
        ]
        return current_cell

    def _close_local_positive_z_caps(self, current_cell):
        current_grid = grid_tesselate.grid.__new__(grid_tesselate.grid)
        current_grid.cells = np.array([[current_cell]], dtype=object)
        current_grid._close_local_positive_z_boundary_edge_loops(
            positive_z_nudge_plan={
                (1, 1): {"difference_corners": [IntermediateCorner.SE]}
            },
            split_rotation=0,
            output_fileformat="STLb",
        )

    def _positive_top_edges(self, directed_top_edges):
        return {
            edge_3d_signature(start, end)
            for start, end in directed_top_edges
        }

    def test_local_positive_z_four_edge_cap_reverses_boundary_order(self):
        loop = [
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
        ]
        directed_top_edges = list(zip(loop, loop[1:] + loop[:1]))
        current_cell = self._positive_z_loop_cell(directed_top_edges)

        self._close_local_positive_z_caps(current_cell)

        self.assertEqual(len(current_cell.surfacePolygonBorders), 6)
        edge_counts, directed_edge_counts = surface_mesh_edge_usage(
            current_cell.meshes_for_model(),
            split_rotation=0,
            output_fileformat="STLb",
        )
        top_edges = self._positive_top_edges(directed_top_edges)
        self.assertEqual(
            {edge_key: edge_counts[edge_key] for edge_key in top_edges},
            {edge_key: 2 for edge_key in top_edges},
        )
        self.assertTrue(
            directed_edges_are_balanced(
                edge_counts,
                directed_edge_counts,
                top_edges,
            )
        )

    def test_local_positive_z_fan_cap_balances_center_edges(self):
        loop = [
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.2, 0.7, 1.0),
            (0.5, 1.2, 1.0),
            (-0.2, 0.7, 1.0),
        ]
        directed_top_edges = list(zip(loop, loop[1:] + loop[:1]))
        current_cell = self._positive_z_loop_cell(directed_top_edges)

        self._close_local_positive_z_caps(current_cell)

        self.assertEqual(len(current_cell.surfacePolygonBorders), 10)
        edge_counts, directed_edge_counts = surface_mesh_edge_usage(
            current_cell.meshes_for_model(),
            split_rotation=0,
            output_fileformat="STLb",
        )
        top_edges = self._positive_top_edges(directed_top_edges)
        self.assertEqual(
            {edge_key: edge_counts[edge_key] for edge_key in top_edges},
            {edge_key: 2 for edge_key in top_edges},
        )
        positive_two_edges = {
            edge_key
            for edge_key, count in edge_counts.items()
            if count == 2 and edge_key[0][2] > 0 and edge_key[1][2] > 0
        }
        self.assertTrue(top_edges.issubset(positive_two_edges))
        self.assertTrue(
            directed_edges_are_balanced(
                edge_counts,
                directed_edge_counts,
                positive_two_edges,
            )
        )

    def test_local_positive_z_cap_rejects_unordered_only_loop(self):
        a = (0.0, 0.0, 1.0)
        b = (1.0, 0.0, 1.0)
        c = (1.0, 1.0, 1.0)
        d = (0.0, 1.0, 1.0)
        directed_top_edges = [(a, b), (c, b), (c, d), (a, d)]
        current_cell = self._positive_z_loop_cell(directed_top_edges)

        self._close_local_positive_z_caps(current_cell)

        self.assertEqual(len(current_cell.surfacePolygonBorders), 4)
        edge_counts, _directed_edge_counts = surface_mesh_edge_usage(
            current_cell.meshes_for_model(),
            split_rotation=0,
            output_fileformat="STLb",
        )
        self.assertEqual(
            {
                edge_key: edge_counts[edge_key]
                for edge_key in self._positive_top_edges(directed_top_edges)
            },
            {
                edge_key: 1
                for edge_key in self._positive_top_edges(directed_top_edges)
            },
        )

    def test_collinear_positive_z_boundary_cycle_splits_long_edge(self):
        a = (0.0, 0.0, 1.0)
        mid = (0.5, 0.0, 0.9)
        end = (1.0, 0.0, 0.8)
        current_cell = cell(
            None,
            None,
            {},
        )
        current_cell.topSurfacePolygons = [
            shapely.Polygon([end, a, (0.0, 1.0, 0.0), end]),
            shapely.Polygon([a, mid, (0.5, -0.2, 0.0), a]),
            shapely.Polygon([mid, end, (1.0, -0.2, 0.0), mid]),
        ]

        self._close_local_positive_z_caps(current_cell)

        edge_counts, directed_edge_counts = surface_mesh_edge_usage(
            current_cell.meshes_for_model(),
            split_rotation=0,
            output_fileformat="STLb",
        )
        positive_boundary_edges = {
            edge_key
            for edge_key, count in edge_counts.items()
            if count == 1 and edge_key[0][2] > 0 and edge_key[1][2] > 0
        }
        positive_two_edges = {
            edge_key
            for edge_key, count in edge_counts.items()
            if count == 2 and edge_key[0][2] > 0 and edge_key[1][2] > 0
        }

        self.assertEqual(positive_boundary_edges, set())
        self.assertTrue(
            directed_edges_are_balanced(
                edge_counts,
                directed_edge_counts,
                positive_two_edges,
            )
        )
        self.assertEqual(len(current_cell.topSurfacePolygons), 4)

    def _normalized_surface_vertices_at_xy(self, polygons, xy, fileformat):
        vertices = set()
        for polygon in polygons or []:
            for coord in polygon.exterior.coords[:-1]:
                normalized = normalize_vertex_to_match_mesh_serialization(
                    coord,
                    fileformat,
                )
                if normalized[:2] == xy:
                    vertices.add(normalized)
        return vertices

    def _normalized_cell_vertices_at_xy(self, current_cell, xy, fileformat):
        vertices = set()
        for mesh in current_cell.meshes_for_model():
            if isinstance(mesh, quad):
                coords = [
                    mesh_vertex.coords
                    for mesh_vertex in mesh.vl
                    if mesh_vertex is not None
                ]
            else:
                coords = list(mesh.exterior.coords)[:-1]
            for coord in coords:
                normalized = normalize_vertex_to_match_mesh_serialization(
                    coord,
                    fileformat,
                )
                if normalized[:2] == xy:
                    vertices.add(normalized)
        return vertices

    def _normalized_cell_xy_edges(self, current_cell, fileformat):
        edges = set()
        for mesh in current_cell.meshes_for_model():
            if isinstance(mesh, quad):
                triangles = mesh.get_triangles(split_rotation=0)
                triangle_coords = [
                    [mesh_vertex.coords for mesh_vertex in triangle]
                    for triangle in triangles
                ]
            else:
                triangle_coords = [list(mesh.exterior.coords)[:-1]]
            for coords in triangle_coords:
                normalized = [
                    normalize_vertex_to_match_mesh_serialization(
                        coord,
                        fileformat,
                    )[:2]
                    for coord in coords
                ]
                for index, coord0 in enumerate(normalized):
                    coord1 = normalized[(index + 1) % len(normalized)]
                    edges.add(tuple(sorted((coord0, coord1))))
        return edges

    def _flat_surface_polygons(self, coords, z, exterior_cw):
        polygon = shapely.Polygon([(x, y, z) for x, y in coords])
        triangles = shapely.constrained_delaunay_triangles(
            shapely.force_2d(polygon),
        )
        return [
            shapely.Polygon(
                [(x, y, z) for x, y in triangle.exterior.coords],
            )
            for triangle in shapely.get_parts(
                shapely.orient_polygons(
                    triangles,
                    exterior_cw=exterior_cw,
                )
            )
        ]

    def test_positive_classifier_detects_supported_corner_sets(self):
        fileformat = "STLb"
        base_lower = {corner: 1.0 for corner in IntermediateCorner}

        cases = [
            [IntermediateCorner.SW],
            [IntermediateCorner.SW, IntermediateCorner.SE],
            [IntermediateCorner.SW, IntermediateCorner.NE],
            [
                IntermediateCorner.SW,
                IntermediateCorner.SE,
                IntermediateCorner.NE,
            ],
        ]
        for affected in cases:
            with self.subTest(affected=affected):
                upper = {corner: 2.0 for corner in IntermediateCorner}
                for corner in affected:
                    upper[corner] = base_lower[corner]

                self.assertEqual(
                    set(
                        _positive_z_nudge_corners_from_values(
                            (upper, base_lower),
                            fileformat,
                        )
                    ),
                    set(affected),
                )

    def test_positive_classifier_ignores_z0_unequal_and_all_four(self):
        fileformat = "STLb"
        lower = {corner: 1.0 for corner in IntermediateCorner}
        upper = {corner: 1.0 for corner in IntermediateCorner}
        self.assertEqual(
            _positive_z_nudge_corners_from_values(
                (upper, lower),
                fileformat,
            ),
            [],
        )

        lower = {corner: 1.0 for corner in IntermediateCorner}
        upper = {corner: 2.0 for corner in IntermediateCorner}
        lower[IntermediateCorner.SW] = 0.0
        upper[IntermediateCorner.SW] = 0.0
        self.assertEqual(
            _positive_z_nudge_corners_from_values(
                (upper, lower),
                fileformat,
            ),
            [],
        )

        lower = {corner: 1.0 for corner in IntermediateCorner}
        upper = {corner: 2.0 for corner in IntermediateCorner}
        self.assertEqual(
            _positive_z_nudge_corners_from_values(
                (upper, lower),
                fileformat,
            ),
            [],
        )

    def test_positive_z_plan_keeps_shared_edge_and_neighbor_split(self):
        upper = np.full((4, 4), 2.0, dtype=float)
        lower = np.full((4, 4), 3.0, dtype=float)
        lower[0:3, 1:3] = 2.0
        emit = upper.copy()

        plan = build_positive_z_nudge_plan(
            upper,
            lower,
            emit,
            emit,
            cell_size=1.0,
            offsetx=0.0,
            offsety=2.0,
            split_rotation=0,
            ymaxidx=2,
            xmaxidx=2,
            zero_threshold=0.1,
            output_fileformat="STLb",
        )

        self.assertEqual(
            set(plan[(1, 1)]["corners"]),
            {IntermediateCorner.NE, IntermediateCorner.SE},
        )
        self.assertIn("N", plan[(2, 1)]["split_sides"])

    def test_positive_z_filter_ignores_isolated_one_corner_contact(self):
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.5),
                vertex(1.0, 1.0, 0.5),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 0.5),
            ),
            {},
        )
        cells = np.empty((1, 1), dtype=object)
        cells[0, 0] = current_cell

        filtered = filter_positive_z_nudge_plan_to_actual_overused_edges(
            {
                (1, 1): {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": [IntermediateCorner.SE],
                }
            },
            cells,
            cell_size=1.0,
            offsetx=0.0,
            offsety=1.0,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertNotIn((1, 1), filtered)

    def test_positive_z_filter_ignores_one_corner_without_emitted_contact(self):
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.5),
                vertex(1.0, 1.0, 0.5),
                vertex(1.0, 0.0, 0.9),
                vertex(0.0, 0.0, 0.5),
            ),
            {},
        )
        cells = np.empty((1, 1), dtype=object)
        cells[0, 0] = current_cell

        filtered = filter_positive_z_nudge_plan_to_actual_overused_edges(
            {
                (1, 1): {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": [IntermediateCorner.SE],
                }
            },
            cells,
            cell_size=1.0,
            offsetx=0.0,
            offsety=1.0,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertNotIn((1, 1), filtered)

    def test_positive_z_filter_ignores_one_corner_without_overused_edge(self):
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.5),
                vertex(1.0, 1.0, 0.5),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 0.5),
            ),
            {},
        )
        cells = np.empty((1, 1), dtype=object)
        cells[0, 0] = current_cell

        filtered = filter_positive_z_nudge_plan_to_actual_overused_edges(
            {
                (1, 1): {
                    "corners": [IntermediateCorner.SE],
                    "split_sides": set(),
                    "contact_corners": [IntermediateCorner.SE],
                }
            },
            cells,
            cell_size=1.0,
            offsetx=0.0,
            offsety=1.0,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertNotIn((1, 1), filtered)

    def test_positive_z_filter_keeps_one_corner_contact_on_confirmed_edge(self):
        cells = np.empty((2, 2), dtype=object)
        cells[:] = None
        cells[0, 0] = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 1.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.5),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 0.5),
            ),
            {},
        )
        cells[0, 1] = cell(
            quad(
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(2.0, 0.0, 2.0),
                vertex(2.0, 1.0, 2.0),
            ),
            quad(
                vertex(1.0, 1.0, 1.0),
                vertex(2.0, 1.0, 0.5),
                vertex(2.0, 0.0, 0.5),
                vertex(1.0, 0.0, 1.0),
            ),
            {},
        )
        cells[1, 0] = cell(
            quad(
                vertex(0.0, 0.0, 2.0),
                vertex(0.0, -1.0, 2.0),
                vertex(1.0, -1.0, 2.0),
                vertex(1.0, 0.0, 1.0),
            ),
            quad(
                vertex(0.0, 0.0, 0.5),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, -1.0, 0.5),
                vertex(0.0, -1.0, 0.5),
            ),
            {},
        )

        filtered = filter_positive_z_nudge_plan_to_actual_overused_edges(
            {
                (1, 1): {
                    "corners": [
                        IntermediateCorner.NE,
                        IntermediateCorner.SE,
                    ],
                    "split_sides": set(),
                    "contact_corners": [
                        IntermediateCorner.NE,
                        IntermediateCorner.SE,
                    ],
                },
                (1, 2): {
                    "corners": [
                        IntermediateCorner.NW,
                        IntermediateCorner.SW,
                    ],
                    "split_sides": set(),
                    "contact_corners": [
                        IntermediateCorner.NW,
                        IntermediateCorner.SW,
                    ],
                },
                (2, 1): {
                    "corners": [],
                    "split_sides": set(),
                    "contact_corners": [IntermediateCorner.NE],
                },
            },
            cells,
            cell_size=1.0,
            offsetx=0.0,
            offsety=1.0,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertEqual(
            filtered[(2, 1)]["corners"],
            [IntermediateCorner.NE],
        )
        self.assertTrue(filtered[(2, 1)]["confirmed_overused_edges"])

    def test_positive_z_filter_promotes_clipped_side_overuse(self):
        fileformat = "STLb"
        cells = np.empty((2, 1), dtype=object)
        cells[:] = None
        shared_edge = ((0.25, 0.0, 1.0), (1.0, 0.0, 1.0))
        cells[0, 0] = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.5),
                vertex(1.0, 1.0, 0.5),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 0.5),
            ),
            {},
        )
        cells[0, 0].topSurfacePolygons = [
            shapely.Polygon(
                [
                    shared_edge[0],
                    shared_edge[1],
                    (0.55, 0.45, 1.8),
                    shared_edge[0],
                ]
            )
        ]
        cells[0, 0].bottomSurfacePolygons = [
            shapely.Polygon(
                [
                    shared_edge[1],
                    shared_edge[0],
                    (0.55, 0.45, 1.4),
                    shared_edge[1],
                ]
            )
        ]
        cells[1, 0] = cell(
            quad(
                vertex(0.0, 0.0, 2.0),
                vertex(0.0, -1.0, 2.0),
                vertex(1.0, -1.0, 2.0),
                vertex(1.0, 0.0, 1.0),
            ),
            quad(
                vertex(0.0, 0.0, 0.5),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, -1.0, 0.5),
                vertex(0.0, -1.0, 0.5),
            ),
            {},
        )
        cells[1, 0].topSurfacePolygons = [
            shapely.Polygon(
                [
                    shared_edge[1],
                    shared_edge[0],
                    (0.55, -0.45, 1.8),
                    shared_edge[1],
                ]
            )
        ]
        cells[1, 0].bottomSurfacePolygons = [
            shapely.Polygon(
                [
                    shared_edge[0],
                    shared_edge[1],
                    (0.55, -0.45, 1.4),
                    shared_edge[0],
                ]
            )
        ]

        filtered = filter_positive_z_nudge_plan_to_actual_overused_edges(
            {},
            cells,
            cell_size=1.0,
            offsetx=0.0,
            offsety=1.0,
            split_rotation=0,
            output_fileformat=fileformat,
        )

        self.assertEqual(
            filtered[(1, 1)]["corners"],
            [],
        )
        self.assertEqual(
            set(_positive_z_effective_difference_corners(filtered[(1, 1)])),
            {IntermediateCorner.SW, IntermediateCorner.SE},
        )
        self.assertEqual(
            filtered[(2, 1)]["corners"],
            [],
        )
        self.assertEqual(
            set(_positive_z_effective_difference_corners(filtered[(2, 1)])),
            {IntermediateCorner.NW, IntermediateCorner.NE},
        )
        self.assertTrue(filtered[(1, 1)]["confirmed_overused_edges"])
        self.assertTrue(filtered[(2, 1)]["confirmed_overused_edges"])

    def test_provider_polygon_replacement_promotes_full_top_quad(self):
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        provider_bottom = [
            shapely.Polygon(
                [
                    (0.0, 0.0, 1.0),
                    (1.0, 0.0, 1.0),
                    (0.0, 1.0, 2.0),
                    (0.0, 0.0, 1.0),
                ]
            )
        ]

        current_cell.replace_bottom_surfaces(
            bottom_surface_quad=None,
            bottom_surface_polygons=provider_bottom,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertEqual(len(current_cell.topSurfacePolygons), 1)
        self.assertEqual(len(current_cell.bottomSurfacePolygons), 1)
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            _polygon_footprint_area(provider_bottom),
        )

    def _wv_difference_top_quad(self):
        return quad(
            vertex(8.1, 18.3, 3.6585),
            vertex(8.1, 18.2, 3.6455),
            vertex(8.2, 18.2, 3.656),
            vertex(8.2, 18.3, 3.668),
        )

    def _flat_bottom_quad(self):
        return quad(
            vertex(8.1, 18.3, 0.0),
            vertex(8.2, 18.3, 0.0),
            vertex(8.2, 18.2, 0.0),
            vertex(8.1, 18.2, 0.0),
        )

    def _normal_top_as_bottom_quad(self):
        return quad(
            vertex(8.1, 18.3, 3.4785),
            vertex(8.2, 18.3, 3.668),
            vertex(8.2, 18.2, 3.656),
            vertex(8.1, 18.2, 3.6455),
        )

    def _wv_gap_difference_top_quad(self):
        return quad(
            vertex(8.2, 17.8, 3.611),
            vertex(8.2, 17.7, 3.5895),
            vertex(8.3, 17.7, 3.604),
            vertex(8.3, 17.8, 3.622),
        )

    def _wv_gap_normal_top_as_bottom_quad(self):
        return quad(
            vertex(8.2, 17.8, 3.611),
            vertex(8.3, 17.8, 3.622),
            vertex(8.3, 17.7, 3.604),
            vertex(8.2, 17.7, 3.4095),
        )

    def _internal_xy_edge(self, triangles):
        edge_counts = {}
        for triangle in triangles:
            xy_coords = [
                triangle_vertex.coords[:2]
                for triangle_vertex in triangle
            ]
            for index, coord0 in enumerate(xy_coords):
                coord1 = xy_coords[(index + 1) % len(xy_coords)]
                edge = tuple(sorted((coord0, coord1)))
                edge_counts[edge] = edge_counts.get(edge, 0) + 1
        return next(edge for edge, count in edge_counts.items() if count == 2)

    def test_pair_replacement_forces_difference_quad_to_normal_split(self):
        split_rotation = 2
        current_cell = cell(
            self._wv_difference_top_quad(),
            self._flat_bottom_quad(),
            {},
        )
        provider_bottom = self._normal_top_as_bottom_quad()

        self.assertEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            (1, 3),
        )
        self.assertEqual(
            provider_bottom.get_split_edge_indices(split_rotation),
            (0, 2),
        )

        current_cell.replace_bottom_surfaces(
            bottom_surface_quad=provider_bottom,
            bottom_surface_polygons=None,
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            (0, 2),
        )
        self.assertIs(current_cell.bottomquad, provider_bottom)
        self.assertIsNone(current_cell.topSurfacePolygons)
        self.assertIsNone(current_cell.bottomSurfacePolygons)
        self.assertEqual(
            self._internal_xy_edge(
                current_cell.topquad.get_triangles(split_rotation),
            ),
            self._internal_xy_edge(
                current_cell.bottomquad.get_triangles(split_rotation),
            ),
        )

    def test_pair_split_override_can_read_provider_polygon_diagonal(self):
        split_rotation = 2
        current_cell = cell(
            self._wv_difference_top_quad(),
            self._flat_bottom_quad(),
            {},
        )
        provider_bottom = self._normal_top_as_bottom_quad()

        current_cell._force_top_split_to_bottom_surface(
            bottom_surface_quad=None,
            bottom_surface_polygons=provider_bottom.get_triangles_in_polygons(
                split_rotation,
            ),
            split_rotation=split_rotation,
        )

        self.assertEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            (0, 2),
        )
        self.assertIsNone(current_cell.topSurfacePolygons)
        self.assertIsNone(current_cell.bottomSurfacePolygons)

    def test_zero_height_cleanup_keeps_forced_same_split_full_quad(self):
        split_rotation = 2
        current_cell = cell(
            self._wv_difference_top_quad(),
            self._normal_top_as_bottom_quad(),
            {},
        )
        current_cell._force_top_split_to_bottom_surface(
            self._normal_top_as_bottom_quad(),
            None,
            split_rotation,
        )

        current_cell.remove_zero_height_volumes(
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertIsNotNone(current_cell.topquad.vl[3])
        self.assertIsNotNone(current_cell.bottomquad.vl[3])
        self.assertEqual(
            self._internal_xy_edge(
                current_cell.topquad.get_triangles(split_rotation),
            ),
            self._internal_xy_edge(
                current_cell.bottomquad.get_triangles(split_rotation),
            ),
        )
        self.assertIsNone(current_cell.topSurfacePolygons)
        self.assertIsNone(current_cell.bottomSurfacePolygons)

    def test_zero_height_cleanup_keeps_natural_same_split_sw_ne_full_quad(self):
        split_rotation = 2
        current_cell = cell(
            self._wv_gap_difference_top_quad(),
            self._wv_gap_normal_top_as_bottom_quad(),
            {},
        )
        self.assertEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            (1, 3),
        )
        self.assertEqual(
            current_cell.bottomquad.get_split_edge_indices(split_rotation),
            (1, 3),
        )

        current_cell.remove_zero_height_volumes(
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertIsNotNone(current_cell.topquad.vl[3])
        self.assertIsNotNone(current_cell.bottomquad.vl[3])
        self.assertEqual(
            self._internal_xy_edge(
                current_cell.topquad.get_triangles(split_rotation),
            ),
            self._internal_xy_edge(
                current_cell.bottomquad.get_triangles(split_rotation),
            ),
        )

    def test_zero_height_cleanup_keeps_natural_same_split_nw_se_full_quad(self):
        split_rotation = 2
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(1.0, 1.0, 1.0),
            ),
            quad(
                vertex(0.0, 1.0, 1.5),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 1.0),
            ),
            {},
        )
        self.assertEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            (0, 2),
        )
        self.assertEqual(
            current_cell.bottomquad.get_split_edge_indices(split_rotation),
            (0, 2),
        )

        current_cell.remove_zero_height_volumes(
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertIsNotNone(current_cell.topquad.vl[3])
        self.assertIsNotNone(current_cell.bottomquad.vl[3])
        self.assertEqual(
            self._internal_xy_edge(
                current_cell.topquad.get_triangles(split_rotation),
            ),
            self._internal_xy_edge(
                current_cell.bottomquad.get_triangles(split_rotation),
            ),
        )

    def test_zero_height_cleanup_keeps_different_split_corner_fallback(self):
        split_rotation = 2
        current_cell = cell(
            self._wv_difference_top_quad(),
            self._normal_top_as_bottom_quad(),
            {},
        )
        self.assertNotEqual(
            current_cell.topquad.get_split_edge_indices(split_rotation),
            current_cell.bottomquad.get_split_edge_indices(split_rotation),
        )

        current_cell.remove_zero_height_volumes(
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertIsNone(current_cell.topquad.vl[3])
        self.assertIsNone(current_cell.bottomquad.vl[3])

    def test_serialization_cleanup_preserves_forced_quad_split(self):
        split_rotation = 2
        source_quad = self._wv_difference_top_quad()
        source_quad.forced_split_edge = (0, 2)

        normalized_quad = (
            mesh_serialization.quad_normalized_to_match_mesh_serialization(
                source_quad,
                "STLb",
                split_rotation,
            )
        )

        self.assertEqual(
            normalized_quad.get_split_edge_indices(split_rotation),
            (0, 2),
        )

    def test_pair_replacement_keeps_cardinal_wall_on_forced_quad_path(self):
        split_rotation = 2
        top_quad = self._wv_difference_top_quad()
        initial_bottom_quad = self._flat_bottom_quad()
        borders = {}
        borders["N"] = make_wall_without_exact_duplicate_vertices(
            initial_bottom_quad.vl[0],
            top_quad.vl[0],
            top_quad.vl[3],
            initial_bottom_quad.vl[1],
        )
        current_cell = cell(top_quad, initial_bottom_quad, borders)

        current_cell.replace_bottom_surfaces(
            bottom_surface_quad=self._normal_top_as_bottom_quad(),
            bottom_surface_polygons=None,
            split_rotation=split_rotation,
            output_fileformat="STLb",
        )

        self.assertIsNone(current_cell.topSurfacePolygons)
        self.assertIsNone(current_cell.bottomSurfacePolygons)
        self.assertIsInstance(current_cell.borders["N"], quad)
        self.assertNotIn("S", current_cell.borders)
        self.assertNotIn("E", current_cell.borders)
        self.assertNotIn("W", current_cell.borders)

    def test_positive_difference_nudge_removes_contact_footprint(self):
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 2.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 1.0),
                vertex(1.0, 1.0, 1.0),
                vertex(1.0, 0.0, 1.0),
                vertex(0.0, 0.0, 1.0),
            ),
            {},
        )

        changed = current_cell.apply_positive_z_difference_nudge(
            [IntermediateCorner.SW, IntermediateCorner.SE],
            W=0.0,
            E=1.0,
            N=1.0,
            S=0.0,
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertTrue(changed)
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            full_cell_footprint(0.0, 1.0, 1.0, 0.0).area / 2,
        )
        cut_footprint = edge_xy_signature(
            (0.0, 0.5, 0.0),
            (1.0, 0.5, 0.0),
        )
        wall_footprints = {
            edge_xy_signature(wall.vl[0].coords, wall.vl[1].coords)
            for wall in current_cell.surfacePolygonBorders
        }
        self.assertIn(cut_footprint, wall_footprints)

    def test_positive_difference_midpoints_use_surface_specific_z(self):
        fileformat = "STLb"
        top_corner_vertices = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 6.0),
            IntermediateCorner.NE: vertex(1.0, 1.0, 6.0),
            IntermediateCorner.SW: vertex(0.0, 0.0, 6.0),
            IntermediateCorner.SE: vertex(1.0, 0.0, 4.0),
        }
        current_cell = cell(
            quad(
                top_corner_vertices[IntermediateCorner.NW],
                top_corner_vertices[IntermediateCorner.SW],
                top_corner_vertices[IntermediateCorner.SE],
                top_corner_vertices[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 2.5),
                vertex(1.0, 1.0, 2.5),
                vertex(1.0, 0.0, 4.0),
                vertex(0.0, 0.0, 2.5),
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SE],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 5.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 5.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 3.25)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 3.25)},
        )

    def test_positive_difference_one_corner_nudge_accepts_triangular_bottom(self):
        fileformat = "STLb"
        top_corner_vertices = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 6.0),
            IntermediateCorner.NE: vertex(1.0, 1.0, 6.0),
            IntermediateCorner.SW: vertex(0.0, 0.0, 4.0),
            IntermediateCorner.SE: vertex(1.0, 0.0, 6.0),
        }
        current_cell = cell(
            quad(
                top_corner_vertices[IntermediateCorner.NE],
                top_corner_vertices[IntermediateCorner.NW],
                top_corner_vertices[IntermediateCorner.SW],
                None,
            ),
            quad(
                vertex(0.0, 0.0, 2.5),
                vertex(0.0, 1.0, 2.5),
                vertex(1.0, 1.0, 2.5),
                None,
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SW],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        bottom_edges = boundary_edge_map_from_meshes(
            current_cell.bottomSurfacePolygons,
            output_fileformat=fileformat,
        )
        self.assertIn(
            edge_xy_signature((0.0, 0.5, 0.0), (0.0, 1.0, 0.0)),
            bottom_edges,
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (0.0, 0.5),
                fileformat,
            ),
            {(0.0, 0.5, 2.5)},
        )

    def test_positive_difference_midpoint_clips_provider_coverage(self):
        fileformat = "STLb"
        top_corner_vertices = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 6.0),
            IntermediateCorner.NE: vertex(1.0, 1.0, 6.0),
            IntermediateCorner.SW: vertex(0.0, 0.0, 6.0),
            IntermediateCorner.SE: vertex(1.0, 0.0, 4.0),
        }
        current_cell = cell(
            quad(
                top_corner_vertices[IntermediateCorner.NW],
                top_corner_vertices[IntermediateCorner.SW],
                top_corner_vertices[IntermediateCorner.SE],
                top_corner_vertices[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 2.5),
                vertex(1.0, 1.0, 2.5),
                vertex(1.0, 0.0, 2.5),
                vertex(0.0, 0.0, 2.5),
            ),
            {},
        )
        current_cell.bottomSurfacePolygons = [
            shapely.Polygon(
                [
                    (0.0, 1.0, 2.5),
                    (1.0, 1.0, 2.5),
                    (0.0, 0.0, 2.5),
                    (0.0, 1.0, 2.5),
                ]
            )
        ]

        self.assertTrue(
            current_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SE],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            set(),
        )

    def test_split_only_difference_record_promotes_matching_contact_corners(
        self,
    ):
        contact_corners = [
            IntermediateCorner.SW,
            IntermediateCorner.NW,
            IntermediateCorner.NE,
        ]
        promoted_record = {
            "corners": [],
            "contact_corners": contact_corners,
            "split_sides": {"S", "E"},
        }
        partial_record = {
            "corners": [],
            "contact_corners": contact_corners,
            "split_sides": {"S"},
        }
        pair_nudge_record = {
            "corners": [],
            "contact_corners": [
                IntermediateCorner.NE,
                IntermediateCorner.SW,
            ],
            "split_sides": {"S", "E"},
        }

        self.assertEqual(
            _positive_z_effective_difference_corners(promoted_record),
            contact_corners,
        )
        self.assertEqual(
            _positive_z_effective_difference_corners(partial_record),
            [],
        )
        self.assertEqual(
            _positive_z_effective_difference_corners(pair_nudge_record),
            [
                IntermediateCorner.NW,
                IntermediateCorner.NE,
                IntermediateCorner.SW,
            ],
        )
        self.assertEqual(
            _positive_z_effective_difference_corners(
                {
                    "corners": [],
                    "contact_corners": [
                        IntermediateCorner.NE,
                        IntermediateCorner.SW,
                    ],
                    "split_sides": {"E"},
                },
            ),
            [
                IntermediateCorner.NW,
                IntermediateCorner.NE,
                IntermediateCorner.SW,
            ],
        )

    def test_promoted_difference_corners_propagate_neighbor_splits(self):
        plan = {
            (217, 495): {
                "corners": [],
                "contact_corners": [
                    IntermediateCorner.NE,
                    IntermediateCorner.SW,
                ],
                "split_sides": {"E"},
            }
        }

        self.assertEqual(
            _positive_z_difference_neighbor_split_sides(plan),
            {
                (218, 495): {"N"},
                (217, 496): {"W"},
            },
        )

    def test_positive_difference_three_corner_pa_cell_keeps_open_triangle(
        self,
    ):
        fileformat = "STLb"
        w, e, n, s = 49.4, 49.5, 37.3, 37.2
        top_z = {
            IntermediateCorner.NW: 0.94,
            IntermediateCorner.NE: 0.914,
            IntermediateCorner.SW: 0.933,
            IntermediateCorner.SE: 0.918,
        }
        bottom_z = {
            IntermediateCorner.NW: 0.94,
            IntermediateCorner.NE: 0.914,
            IntermediateCorner.SW: 0.933,
            IntermediateCorner.SE: 0.8645,
        }
        affected_corners = [
            IntermediateCorner.SW,
            IntermediateCorner.NW,
            IntermediateCorner.NE,
        ]
        current_cell = cell(
            quad(
                vertex(w, n, top_z[IntermediateCorner.NW]),
                vertex(w, s, top_z[IntermediateCorner.SW]),
                vertex(e, s, top_z[IntermediateCorner.SE]),
                vertex(e, n, top_z[IntermediateCorner.NE]),
            ),
            quad(
                vertex(w, n, bottom_z[IntermediateCorner.NW]),
                vertex(e, n, bottom_z[IntermediateCorner.NE]),
                vertex(e, s, bottom_z[IntermediateCorner.SE]),
                vertex(w, s, bottom_z[IntermediateCorner.SW]),
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_difference_nudge(
                affected_corners,
                W=w,
                E=e,
                N=n,
                S=s,
                split_rotation=1,
                output_fileformat=fileformat,
            )
        )

        expected_footprint = nudge_keep_footprint(
            affected_corners,
            w,
            e,
            n,
            s,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            expected_footprint.area,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            expected_footprint.area,
        )
        for removed_xy in [
            normalize_vertex_to_match_mesh_serialization(
                (49.4, 37.2, 0.0),
                fileformat,
            )[:2],
            normalize_vertex_to_match_mesh_serialization(
                (49.5, 37.3, 0.0),
                fileformat,
            )[:2],
        ]:
            self.assertEqual(
                self._normalized_cell_vertices_at_xy(
                    current_cell,
                    removed_xy,
                    fileformat,
                ),
                set(),
            )

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (49.450001, 37.200001),
                fileformat,
            ),
            {(49.450001, 37.200001, 0.9255)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (49.450001, 37.200001),
                fileformat,
            ),
            {(49.450001, 37.200001, 0.89875)},
        )

        edge_counts = surface_mesh_edge_counts(
            current_cell.meshes_for_model(),
            split_rotation=1,
            output_fileformat=fileformat,
        )
        positive_overused_edges = [
            edge
            for edge, count in edge_counts.items()
            if count > 2 and edge[0][2] > 0 and edge[1][2] > 0
        ]
        self.assertEqual(positive_overused_edges, [])

        current_cell.remove_zero_height_volumes(
            split_rotation=1,
            output_fileformat=fileformat,
        )
        for removed_xy in [
            normalize_vertex_to_match_mesh_serialization(
                (49.4, 37.2, 0.0),
                fileformat,
            )[:2],
            normalize_vertex_to_match_mesh_serialization(
                (49.5, 37.3, 0.0),
                fileformat,
            )[:2],
        ]:
            self.assertEqual(
                self._normalized_cell_vertices_at_xy(
                    current_cell,
                    removed_xy,
                    fileformat,
                ),
                set(),
            )

    def test_positive_normal_top_midpoints_use_normal_top_z(self):
        fileformat = "STLb"
        normal_top_corners = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 2.5),
            IntermediateCorner.NE: vertex(1.0, 1.0, 2.5),
            IntermediateCorner.SW: vertex(0.0, 0.0, 2.5),
            IntermediateCorner.SE: vertex(1.0, 0.0, 4.0),
        }
        current_cell = cell(
            quad(
                normal_top_corners[IntermediateCorner.NW],
                normal_top_corners[IntermediateCorner.SW],
                normal_top_corners[IntermediateCorner.SE],
                normal_top_corners[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_normal_nudge(
                [IntermediateCorner.SE],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 3.25)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 3.25)},
        )

    def test_positive_normal_top_midpoints_use_local_interface_override(self):
        fileformat = "STLb"
        normal_top_corners = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 2.5),
            IntermediateCorner.NE: vertex(1.0, 1.0, 2.5),
            IntermediateCorner.SW: vertex(0.0, 0.0, 2.5),
            IntermediateCorner.SE: vertex(1.0, 0.0, 4.0),
        }
        current_cell = cell(
            quad(
                normal_top_corners[IntermediateCorner.NW],
                normal_top_corners[IntermediateCorner.SW],
                normal_top_corners[IntermediateCorner.SE],
                normal_top_corners[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_normal_nudge(
                [IntermediateCorner.SE],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                top_midpoint_z_by_name={"Smid": 9.0, "Emid": 8.5},
            )
        )

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 9.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 8.5)},
        )

    def test_positive_plan_applies_interface_override_to_normal_top(self):
        fileformat = "STLb"
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.5),
                vertex(0.0, 0.0, 2.5),
                vertex(1.0, 0.0, 4.0),
                vertex(1.0, 1.0, 2.5),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        normal_grid = object.__new__(grid_tesselate.grid)
        normal_grid.cells = np.array([[current_cell]], dtype=object)
        normal_grid.cell_size = 1.0
        normal_grid.offsetx = 0.0
        normal_grid.offsety = 1.0
        normal_grid.tile = SimpleNamespace(bottom_raster_variants=None)
        normal_grid.tile_info = SimpleNamespace(
            config=SimpleNamespace(fileformat=fileformat, split_rotation=0),
        )
        plan = {
            (1, 1): {
                "corners": [IntermediateCorner.SE],
                "split_sides": set(),
                "contact_corners": [IntermediateCorner.SE],
                "midpoint_z_by_name": {"Smid": 9.0, "Emid": 8.5},
            },
        }

        normal_grid.apply_positive_z_plan_to_existing_cells(plan)

        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 9.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 8.5)},
        )

    def test_positive_normal_nudge_keeps_full_footprint(self):
        fileformat = "STLb"
        normal_top_corners = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 2.5),
            IntermediateCorner.NE: vertex(1.0, 1.0, 2.5),
            IntermediateCorner.SW: vertex(0.0, 0.0, 2.5),
            IntermediateCorner.SE: vertex(1.0, 0.0, 4.0),
        }
        current_cell = cell(
            quad(
                normal_top_corners[IntermediateCorner.NW],
                normal_top_corners[IntermediateCorner.SW],
                normal_top_corners[IntermediateCorner.SE],
                normal_top_corners[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )

        self.assertTrue(
            current_cell.apply_positive_z_normal_nudge(
                [IntermediateCorner.SE],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        full_footprint = full_cell_footprint(0.0, 1.0, 1.0, 0.0)
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            full_footprint.area,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            full_footprint.area,
        )
        self.assertIsNone(current_cell.surfacePolygonBorders)
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            {(0.5, 0.0, 3.25)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 3.25)},
        )

    def test_positive_normal_nudge_uses_difference_footprint_splitter(self):
        fileformat = "STLb"
        top_corner_vertices = {
            IntermediateCorner.NW: vertex(0.0, 1.0, 6.0),
            IntermediateCorner.NE: vertex(1.0, 1.0, 6.0),
            IntermediateCorner.SW: vertex(0.0, 0.0, 6.0),
            IntermediateCorner.SE: vertex(1.0, 0.0, 6.0),
        }
        difference_footprint = shapely.Polygon(
            [
                (0.0, 0.0),
                (0.0, 1.0),
                (1.0, 1.0),
                (0.0, 0.0),
            ],
        )
        split_point = (0.25, 0.25)
        normal_cell = cell(
            quad(
                top_corner_vertices[IntermediateCorner.NW],
                top_corner_vertices[IntermediateCorner.SW],
                top_corner_vertices[IntermediateCorner.SE],
                top_corner_vertices[IntermediateCorner.NE],
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        difference_cell = cell(
            quad(
                top_corner_vertices[IntermediateCorner.NE],
                top_corner_vertices[IntermediateCorner.NW],
                top_corner_vertices[IntermediateCorner.SW],
                None,
            ),
            quad(
                vertex(0.0, 0.0, 6.0),
                vertex(0.0, 1.0, 6.0),
                vertex(1.0, 1.0, 6.0),
                None,
            ),
            {},
        )

        self.assertTrue(
            difference_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SW],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )
        self.assertTrue(
            normal_cell.apply_positive_z_normal_nudge(
                [IntermediateCorner.SW],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                difference_footprint=difference_footprint,
            )
        )

        full_footprint = full_cell_footprint(0.0, 1.0, 1.0, 0.0)
        self.assertAlmostEqual(
            _polygon_footprint_area(normal_cell.topSurfacePolygons),
            full_footprint.area,
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                difference_cell.topSurfacePolygons,
                split_point,
                fileformat,
            ),
            {(0.25, 0.25, 6.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                normal_cell.topSurfacePolygons,
                split_point,
                fileformat,
            ),
            {(0.25, 0.25, 6.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                difference_cell.topSurfacePolygons,
                (0.5, 0.0),
                fileformat,
            ),
            set(),
        )
        self.assertIsNone(normal_cell.surfacePolygonBorders)

    def test_split_only_full_cell_inserts_side_midpoint(self):
        fileformat = "STLb"
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 3.0),
                vertex(0.0, 0.0, 3.0),
                vertex(1.0, 0.0, 3.0),
                vertex(1.0, 1.0, 3.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )

        self.assertTrue(
            current_cell.split_surface_boundary_midpoints(
                {"E"},
                [],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                include_contact_cut_walls=False,
                top_midpoint_z_by_name={"Emid": 5.0},
                bottom_midpoint_z_by_name={"Emid": 0.0},
            )
        )

        full_footprint = full_cell_footprint(0.0, 1.0, 1.0, 0.0)
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            full_footprint.area,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            full_footprint.area,
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 5.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 0.0)},
        )
        self.assertIsNone(current_cell.surfacePolygonBorders)

    def test_split_only_difference_cleanup_preserves_pair_endpoint(self):
        fileformat = "STLb"
        W, E, N, S = 50.2, 50.3, 50.4, 50.3
        current_cell = cell(
            quad(
                vertex(W, N, 1.126),
                vertex(W, S, 1.125),
                vertex(E, S, 1.0965),
                vertex(E, N, 1.099),
            ),
            quad(
                vertex(W, N, 1.126),
                vertex(E, N, 0.9065),
                vertex(E, S, 0.905),
                vertex(W, S, 1.125),
            ),
            {},
        )

        self.assertTrue(
            current_cell.split_surface_boundary_midpoints(
                {"S"},
                [IntermediateCorner.NW, IntermediateCorner.SW],
                W=W,
                E=E,
                N=N,
                S=S,
                split_rotation=0,
                output_fileformat=fileformat,
                include_contact_cut_walls=False,
                top_midpoint_z_by_name={"Smid": 1.11075},
            )
        )
        current_cell.remove_zero_height_volumes(
            split_rotation=0,
            output_fileformat=fileformat,
            preserve_zero_height_xy=_nudge_split_side_endpoint_xy(
                {"S"},
                W,
                E,
                N,
                S,
                fileformat,
            ),
            preserve_zero_height_edges=_nudge_split_side_endpoint_edges(
                {"S"},
                W,
                E,
                N,
                S,
                fileformat,
            ),
        )

        self.assertTrue(
            self._normalized_cell_vertices_at_xy(
                current_cell,
                (50.200001, 50.299999),
                fileformat,
            )
        )
        self.assertTrue(
            self._normalized_cell_vertices_at_xy(
                current_cell,
                (50.25, 50.299999),
                fileformat,
            )
        )
        self.assertIn(
            tuple(
                sorted(
                    (
                        (50.200001, 50.299999),
                        (50.25, 50.299999),
                    )
                )
            ),
            self._normalized_cell_xy_edges(current_cell, fileformat),
        )

    def test_split_only_clipped_cell_splits_existing_boundary_only(self):
        fileformat = "STLb"
        clipped_coords = [
            (0.25, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.25, 1.0),
        ]
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 3.0),
                vertex(0.0, 0.0, 3.0),
                vertex(1.0, 0.0, 3.0),
                vertex(1.0, 1.0, 3.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        current_cell.topSurfacePolygons = self._flat_surface_polygons(
            clipped_coords,
            3.0,
            exterior_cw=False,
        )
        before_area = _polygon_footprint_area(current_cell.topSurfacePolygons)

        self.assertTrue(
            current_cell.split_surface_boundary_midpoints(
                {"E", "W"},
                [],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                include_contact_cut_walls=False,
                top_midpoint_z_by_name={"Emid": 4.0, "Wmid": 9.0},
            )
        )

        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            before_area,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            before_area,
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (1.0, 0.5),
                fileformat,
            ),
            {(1.0, 0.5, 4.0)},
        )
        self.assertEqual(
            self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                (0.0, 0.5),
                fileformat,
            ),
            set(),
        )
        boundary = shapely.Polygon(clipped_coords).boundary
        for wall in current_cell.surfacePolygonBorders or []:
            wall_line = shapely.LineString(
                [wall.vl[0].coords[:2], wall.vl[1].coords[:2]],
            )
            self.assertTrue(boundary.covers(wall_line))

    def test_split_only_clipped_neighbor_matches_nudged_half_edge(self):
        fileformat = "STLb"
        left_cell = cell(
            quad(
                vertex(0.0, 1.0, 6.0),
                vertex(0.0, 0.0, 6.0),
                vertex(1.0, 0.0, 6.0),
                vertex(1.0, 1.0, 6.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        clipped_coords = [
            (0.25, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.25, 1.0),
        ]
        left_cell.topSurfacePolygons = self._flat_surface_polygons(
            clipped_coords,
            6.0,
            exterior_cw=False,
        )
        left_cell.bottomSurfacePolygons = self._flat_surface_polygons(
            clipped_coords,
            0.0,
            exterior_cw=True,
        )
        right_cell = cell(
            quad(
                vertex(1.0, 1.0, 6.0),
                vertex(1.0, 0.0, 6.0),
                vertex(2.0, 0.0, 6.0),
                vertex(2.0, 1.0, 6.0),
            ),
            quad(
                vertex(1.0, 1.0, 0.0),
                vertex(2.0, 1.0, 0.0),
                vertex(2.0, 0.0, 0.0),
                vertex(1.0, 0.0, 0.0),
            ),
            {},
        )

        self.assertTrue(
            right_cell.apply_positive_z_normal_nudge(
                [IntermediateCorner.SW],
                W=1.0,
                E=2.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                top_midpoint_z_by_name={"Wmid": 6.0},
            )
        )
        self.assertTrue(
            left_cell.split_surface_boundary_midpoints(
                {"E"},
                [],
                W=0.0,
                E=1.0,
                N=1.0,
                S=0.0,
                split_rotation=0,
                output_fileformat=fileformat,
                include_contact_cut_walls=False,
                top_midpoint_z_by_name={"Emid": 6.0},
            )
        )

        shared_half_edge = edge_xy_signature(
            (1.0, 0.5, 0.0),
            (1.0, 1.0, 0.0),
        )
        unsplit_edge = edge_xy_signature(
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
        )
        for surfaces in [
            left_cell.topSurfacePolygons + right_cell.topSurfacePolygons,
            (
                left_cell.bottomSurfacePolygons
                + right_cell.bottomSurfacePolygons
            ),
        ]:
            boundary_edges = boundary_edge_map_from_meshes(
                surfaces,
                output_fileformat=fileformat,
            )
            self.assertNotIn(shared_half_edge, boundary_edges)
            self.assertNotIn(unsplit_edge, boundary_edges)

    def test_split_only_triangular_difference_cell_preserves_footprint(self):
        fileformat = "STLb"
        current_cell = cell(
            quad(
                vertex(4.9, 1.7, 1.885),
                vertex(4.9, 1.6, 1.859),
                vertex(5.0, 1.6, 1.9085),
                None,
            ),
            quad(
                vertex(4.9, 1.7, 1.885),
                vertex(5.0, 1.6, 1.9085),
                vertex(4.9, 1.6, 1.679),
                None,
            ),
            {},
        )
        before_area = shapely.Polygon(
            [(4.9, 1.7), (4.9, 1.6), (5.0, 1.6)],
        ).area

        self.assertTrue(
            current_cell.split_surface_boundary_midpoints(
                {"E", "S", "W"},
                [],
                W=4.9,
                E=5.0,
                N=1.7,
                S=1.6,
                split_rotation=0,
                output_fileformat=fileformat,
                include_contact_cut_walls=False,
                top_midpoint_z_by_name={
                    "Emid": 9.0,
                    "Smid": 2.0,
                    "Wmid": 2.1,
                },
                bottom_midpoint_z_by_name={
                    "Emid": 9.0,
                    "Smid": 2.0,
                    "Wmid": 2.1,
                },
            )
        )

        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.topSurfacePolygons),
            before_area,
        )
        self.assertAlmostEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            before_area,
        )
        for polygons in [
            current_cell.topSurfacePolygons,
            current_cell.bottomSurfacePolygons,
        ]:
            self.assertEqual(
                self._normalized_surface_vertices_at_xy(
                    polygons,
                    (5.0, 1.7),
                    fileformat,
                ),
                set(),
            )
            self.assertEqual(
                self._normalized_surface_vertices_at_xy(
                    polygons,
                    (5.0, 1.65),
                    fileformat,
                ),
                set(),
            )
            self.assertEqual(
                self._normalized_surface_vertices_at_xy(
                    polygons,
                    (4.95, 1.6),
                    fileformat,
                ),
                {(4.95, 1.6, 2.0)},
            )
            self.assertEqual(
                self._normalized_surface_vertices_at_xy(
                    polygons,
                    (4.9, 1.65),
                    fileformat,
                ),
                {(4.9, 1.65, 2.1)},
            )

        for xy in [
            (4.9, 1.7),
            (4.9, 1.65),
            (4.9, 1.6),
            (4.95, 1.6),
            (5.0, 1.6),
        ]:
            top_vertices = self._normalized_surface_vertices_at_xy(
                current_cell.topSurfacePolygons,
                xy,
                fileformat,
            )
            bottom_vertices = self._normalized_surface_vertices_at_xy(
                current_cell.bottomSurfacePolygons,
                xy,
                fileformat,
            )
            self.assertTrue(top_vertices)
            self.assertTrue(bottom_vertices)
            self.assertGreaterEqual(
                min(vertex[2] for vertex in top_vertices),
                max(vertex[2] for vertex in bottom_vertices),
            )

    def test_clipped_zero_height_cleanup_uses_serialized_precision(self):
        current_cell = cell(
            None,
            None,
            {},
        )
        current_cell.topSurfacePolygons = [
            shapely.Polygon(
                [
                    (4.7, 4.1, 1.83200001),
                    (4.8, 4.15, 1.85050001),
                    (4.75, 4.1, 1.83600001),
                    (4.7, 4.1, 1.83200001),
                ]
            )
        ]
        current_cell.bottomSurfacePolygons = [
            shapely.Polygon(
                [
                    (4.75, 4.1, 1.83600002),
                    (4.8, 4.15, 1.85050002),
                    (4.7, 4.1, 1.83200002),
                    (4.75, 4.1, 1.83600002),
                ]
            )
        ]

        current_cell.remove_zero_height_volumes(
            split_rotation=0,
            output_fileformat="STLb",
        )

        self.assertFalse(current_cell.topSurfacePolygons)
        self.assertFalse(current_cell.bottomSurfacePolygons)

    def test_clipped_positive_contact_diagonal_flips_bottom_only(self):
        fileformat = "STLb"
        a = (0.0, 1.0, 1.0)
        b = (0.0, 0.0, 1.1)
        c = (1.0, 0.8, 0.9)
        d_top = (0.95, 0.95, 0.96)
        d_bottom = (0.95, 0.95, 0.97)
        b_bottom = (0.0, 0.0, 1.2)
        current_cell = cell(
            quad(
                vertex(0.0, 1.0, 2.0),
                vertex(0.0, 0.0, 2.0),
                vertex(1.0, 0.0, 2.0),
                vertex(1.0, 1.0, 2.0),
            ),
            quad(
                vertex(0.0, 1.0, 0.0),
                vertex(1.0, 1.0, 0.0),
                vertex(1.0, 0.0, 0.0),
                vertex(0.0, 0.0, 0.0),
            ),
            {},
        )
        current_cell.topSurfacePolygons = [
            shapely.Polygon([c, d_top, a, c]),
            shapely.Polygon([a, b, c, a]),
        ]
        current_cell.bottomSurfacePolygons = [
            shapely.Polygon([c, a, d_bottom, c]),
            shapely.Polygon([a, c, b_bottom, a]),
        ]

        shared_edge = edge_3d_signature(a, c)
        before_counts = surface_mesh_edge_counts(
            current_cell.topSurfacePolygons
            + current_cell.bottomSurfacePolygons,
            split_rotation=0,
            output_fileformat=fileformat,
        )
        self.assertEqual(before_counts[shared_edge], 4)

        self.assertTrue(
            current_cell.flip_bottom_positive_z_contact_edges(
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        after_counts = surface_mesh_edge_counts(
            current_cell.topSurfacePolygons
            + current_cell.bottomSurfacePolygons,
            split_rotation=0,
            output_fileformat=fileformat,
        )
        self.assertEqual(after_counts[shared_edge], 2)
        self.assertEqual(
            _polygon_footprint_area(current_cell.bottomSurfacePolygons),
            _polygon_footprint_area(
                [
                    shapely.Polygon([c, a, d_bottom, c]),
                    shapely.Polygon([a, c, b_bottom, a]),
                ]
            ),
        )

    def test_adjacent_positive_cells_use_same_raw_shared_edge_split_z(self):
        fileformat = "STLb"
        north_shared_z = 1.7586666666666668
        south_shared_z = 1.867
        west_cell = self._positive_difference_cell(
            1.2000000000000002,
            1.3000000000000003,
            0.9999999999999999,
            0.8999999999999999,
            {
                IntermediateCorner.NW: 1.7,
                IntermediateCorner.NE: north_shared_z,
                IntermediateCorner.SE: south_shared_z,
                IntermediateCorner.SW: 1.809,
            },
        )
        east_cell = self._positive_difference_cell(
            1.3000000000000003,
            1.4000000000000001,
            0.9999999999999999,
            0.8999999999999999,
            {
                IntermediateCorner.NW: north_shared_z,
                IntermediateCorner.NE: 1.833,
                IntermediateCorner.SE: 1.9,
                IntermediateCorner.SW: south_shared_z,
            },
        )

        self.assertTrue(
            west_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SE],
                W=1.2000000000000002,
                E=1.3000000000000003,
                N=0.9999999999999999,
                S=0.8999999999999999,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )
        self.assertTrue(
            east_cell.apply_positive_z_difference_nudge(
                [IntermediateCorner.SW],
                W=1.3000000000000003,
                E=1.4000000000000001,
                N=0.9999999999999999,
                S=0.8999999999999999,
                split_rotation=0,
                output_fileformat=fileformat,
            )
        )

        expected_split_vertex = (1.3, 0.95, 1.812833)
        west_split_vertices = self._normalized_surface_vertices_at_xy(
            west_cell.bottomSurfacePolygons,
            expected_split_vertex[:2],
            fileformat,
        )
        east_split_vertices = self._normalized_surface_vertices_at_xy(
            east_cell.bottomSurfacePolygons,
            expected_split_vertex[:2],
            fileformat,
        )

        self.assertEqual(west_split_vertices, {expected_split_vertex})
        self.assertEqual(east_split_vertices, {expected_split_vertex})

    def test_positive_z_has_no_cross_cell_split_cache(self):
        # Scan the whole package so this stays correct as nudge code moves
        # into modules that do not exist yet.
        package_dir = Path(grid_tesselate.__file__).parent

        for module_path in sorted(package_dir.glob("*.py")):
            source = module_path.read_text(encoding="utf-8")
            with self.subTest(module=module_path.name):
                self.assertNotIn(
                    "positive_z_split_linework_by_location",
                    source,
                )
                self.assertNotIn(
                    "split_surface_boundaries_for_linework",
                    source,
                )


class TestZ0NudgePrecision(unittest.TestCase):
    def test_nudged_shared_edge_keeps_neighbor_precision_until_output(self):
        fileformat = "STLb"
        w, e, n, s = 52.9, 53.0, 153.3, 153.2
        corner_vertices = {
            IntermediateCorner.NW: vertex(w, n, 1.432),
            IntermediateCorner.NE: vertex(e, n, 0.929),
            IntermediateCorner.SW: vertex(w, s, 1.189),
            IntermediateCorner.SE: vertex(e, s, 0.0),
        }
        affected_corners = [IntermediateCorner.SE]

        keep_footprint = nudge_keep_footprint(
            affected_corners,
            w,
            e,
            n,
            s,
        )
        surface_planes = _z0_adjusted_keep_surface_planes(
            affected_corners,
            corner_vertices,
            w,
            e,
            n,
            s,
        )
        nudged_surfaces = _triangulate_2d_geometry_to_3d_polygons(
            keep_footprint,
            surface_planes,
            exterior_cw=False,
            output_fileformat=fileformat,
        )

        boundary_edges = boundary_edge_map_from_meshes(
            nudged_surfaces,
            output_fileformat=fileformat,
        )
        north_footprint = edge_xy_signature(
            normalize_vertex_to_match_mesh_serialization((w, n, 0), fileformat),
            normalize_vertex_to_match_mesh_serialization((e, n, 0), fileformat),
        )
        expected_edge = tuple(
            sorted(
                (
                    normalize_vertex_to_match_mesh_serialization(
                        (w, n, 1.432),
                        fileformat,
                    ),
                    normalize_vertex_to_match_mesh_serialization(
                        (e, n, 0.929),
                        fileformat,
                    ),
                )
            )
        )

        self.assertEqual(
            tuple(sorted(boundary_edges[north_footprint])),
            expected_edge,
        )


class TestGridVertexIndexState(unittest.TestCase):
    def _grid_for_fileformat(self, fileformat):
        config = SimpleNamespace(
            fileformat=fileformat,
            bottom_thru_base=False,
            bottom_elevation=0.0,
            bottom_image=None,
            use_geo_coords=None,
            min_elev=0.0,
            zscale=1.0,
            basethick=0.0,
            tile_centered=True,
            ntilesy=1,
        )
        tile_info = SimpleNamespace(
            config=config,
            pixel_mm=1.0,
            scale=1000.0,
            tile_width=1.0,
            tile_height=1.0,
            tile_no_x=1,
            tile_no_y=1,
        )
        top = np.ones((3, 3), dtype=float)
        bottom = np.zeros((3, 3), dtype=float)
        tile = grid_tesselate.ProcessingTile(
            tile_info,
            RasterVariants(
                top.copy(),
                top.copy(),
                top.copy(),
                None,
            ),
            RasterVariants(
                bottom.copy(),
                bottom.copy(),
                bottom.copy(),
                None,
            ),
        )
        return grid_tesselate.grid(tile)

    def test_non_obj_grid_resets_vertex_index_dict(self):
        self._grid_for_fileformat("obj")
        self.assertIsInstance(vertex.vertex_index_dict, dict)

        vertex(1.0, 2.0, 3.0)
        self.assertEqual(vertex.vertex_index_dict[(1.0, 2.0, 3.0)], 0)

        self._grid_for_fileformat("STLb")
        self.assertEqual(vertex.vertex_index_dict, -1)

        vertex(4.0, 5.0, 6.0)
        self.assertEqual(vertex.vertex_index_dict, -1)


class TestSingleJobParallelWorkers(unittest.TestCase):
    def test_obj_jobs_stay_serial(self):
        config = SimpleNamespace(fileformat="obj", CPU_cores_to_use=0)

        self.assertEqual(single_job_parallel_workers(config, 1000), 1)


class TestCornerInterpolation(unittest.TestCase):
    def test_corner_grid_matches_canonical_scalar_interpolation(self):
        raster = np.array(
            [
                [1.0, np.nan, 3.0, 4.0],
                [5.0, 6.0, np.nan, 8.0],
                [9.0, 10.0, 11.0, np.nan],
                [np.nan, 14.0, 15.0, 16.0],
            ],
            dtype=np.float64,
        )
        expected = np.empty((3, 3), dtype=np.float64)
        for row in range(expected.shape[0]):
            for col in range(expected.shape[1]):
                expected[row, col] = (
                    raster_interpolation.interpolate_corner_with_canonical_order(
                        raster,
                        row,
                        col,
                    )
                )

        actual = raster_interpolation._interpolated_corner_grid(raster)

        np.testing.assert_array_equal(actual, expected)

    def test_cell_corners_reference_shared_corner_grid(self):
        corner_grid = np.arange(20, dtype=np.float64).reshape(4, 5)

        elevations = raster_interpolation._cell_corner_elevations(
            corner_grid,
            i=2,
            j=2,
        )

        self.assertEqual(
            elevations,
            (
                corner_grid[1, 2],
                corner_grid[1, 1],
                corner_grid[2, 2],
                corner_grid[2, 1],
            ),
        )


class TestSerializationNormalization(unittest.TestCase):
    def test_normalize_2d_coordinate_keeps_two_values(self):
        normalized = normalize_vertex_to_match_mesh_serialization(
            (1.25, -0.0),
            "STLb",
        )

        self.assertEqual(normalized, (1.25, 0.0))
