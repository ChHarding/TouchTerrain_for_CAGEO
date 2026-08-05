import os
import unittest

import matplotlib.pyplot as plt
import numpy
import shapely

from touchterrain.common.polygon_clipping import (
    _apply_polygon_clip_updates,
    _polygon_clip_row_ranges,
    _process_polygon_clip_rows,
    _union_clipping_polygons,
    clipping_wall_visualization_edge_records,
    clipping_wall_visualization_edges,
    find_intersection_geometries,
    mark_overlapping_edges_for_walls,
    mark_shared_edges_for_walls,
)
from touchterrain.common.BorderEdge import BorderEdge
from touchterrain.common.RasterVariants import RasterVariants
from touchterrain.common.shapely_plot import (
    border_edges_for_plot,
    border_edge_plot_style,
    plot_shapely_geometries_colormap,
)
from touchterrain.common.utils import arrayCellCoordToQuadPrint2DCoords


SHOW_WALL_PLOTS = os.environ.get("TOUCHTERRAIN_SHOW_WALL_PLOTS") == "1"


def empty_edge_buckets() -> dict[str, list[BorderEdge]]:
    return {side: [] for side in ("N", "W", "S", "E", "other")}


def createTestOverlappingEdges() -> list[list[BorderEdge]]:
    return [
        [
            BorderEdge(geometry=shapely.LineString([(0, 0), (0, 50)]), polygon_line=True)
        ],
        [
            BorderEdge(geometry=shapely.LineString([(0, 0), (0, 10)]), polygon_line=False),
            BorderEdge(geometry=shapely.LineString([(0, 10), (0, 20)]), polygon_line=True),
            BorderEdge(geometry=shapely.LineString([(0, 20), (0, 30)]), polygon_line=False),
            BorderEdge(geometry=shapely.LineString([(0, 30), (0, 50)]), polygon_line=True),
        ],
    ]


def createTestPolygonCellIntersectionData() -> tuple[shapely.Polygon, list[list[tuple[float, float]]]]:
    """
    |-------
    |      /
    |      \\
    |       | <- cell vertical boundary. Clipping portion here is (10,15)<>(10,20)
    |        \\
    |        /
    |_______|
    """
    clippingPrint2DPoly = shapely.Polygon(
        [
            (0, 0),
            (10, 0),
            (10, 5),
            (15, 10),
            (10, 15),
            (10, 20),
            (5, 25),
            (10, 30),
            (5, 30),
            (0, 25),
            (0, 0),
        ]
    )

    # quad are arranged in 3x2 (Y,X). Vertices in CCW order NW SW SE NE
    quadPrint2DCoords1 = [(1, 30), (1.0, 1), (10, 1), (10, 30), (1, 30)]
    quadPrint2DCoords2 = [(10, 30), (10.0, 1), (19, 1), (19, 30), (10, 30)]
    quadPrint2DCoords3 = [(1, 1), (1.0, -28), (10, -28), (10, 1), (1, 1)]
    quadPrint2DCoords4 = [(10, 1), (10.0, -28), (19, -28), (19, 1), (10, 1), (10, 1)]
    # quad 5 and 6 are outside below the clipping polygon
    quadPrint2DCoords5 = [(1, -28), (1.0, -57), (10, -57), (10, -28), (1, -28)]
    quadPrint2DCoords6 = [(10, -28), (10.0, -57), (19, -57), (19, -28), (10, -28)]

    return (
        clippingPrint2DPoly,
        [
            quadPrint2DCoords1,
            quadPrint2DCoords2,
            quadPrint2DCoords3,
            quadPrint2DCoords4,
            quadPrint2DCoords5,
            quadPrint2DCoords6,
        ],
    )


def create_contained_partial_clip_cell_grid_data() -> tuple[
    shapely.Polygon,
    dict[tuple[int, int], list[tuple[float, float]]],
    tuple[int, int],
    float,
]:
    """Return an interior contained cell bordering a partial clipped cell."""
    shape = (5, 5)
    cell_size = 1.0
    quad_coords_by_location = {
        (row, col): arrayCellCoordToQuadPrint2DCoords(
            array_coord_2D=(col, row),
            cell_size=cell_size,
            tile_y_shape=shape[0],
        )
        for row in range(shape[0])
        for col in range(shape[1])
    }

    return (
        shapely.box(1.75, 1.75, 3.5, 3.25),
        quad_coords_by_location,
        shape,
        cell_size,
    )


def clip_test_cell_grid(
    clipping_polygon: shapely.Polygon,
    quad_coords_by_location: dict[
        tuple[int, int],
        list[tuple[float, float]],
    ],
    shape: tuple[int, int],
) -> RasterVariants:
    """Clip a small test grid and return the resulting raster state."""
    raster_variants = RasterVariants(
        original=numpy.ones(shape),
        nan_close=None,
        dilated=None,
        edge_interpolation=None,
    )
    raster_variants.polygon_intersection_geometry = numpy.full(
        shape, None, dtype=object
    )
    raster_variants.polygon_intersection_edge_buckets = numpy.full(
        shape, None, dtype=object
    )
    raster_variants.polygon_intersection_contains_properly = numpy.zeros(
        shape, dtype=bool
    )

    disjoint_cells = []
    geom_updates = []
    edge_updates = []
    contains_updates = []
    for (row, col), quad_coords in quad_coords_by_location.items():
        disjoint, geoms, edge_buckets, contains_properly = (
            find_intersection_geometries(
                clippingPrint2DPoly=clipping_polygon,
                quadPrint2DCoords=quad_coords,
            )
        )

        if disjoint:
            disjoint_cells.append((row, col))
        if geoms:
            geom_updates.append((row, col, geoms))
        if edge_buckets and any(len(v) > 0 for v in edge_buckets.values()):
            edge_updates.append((row, col, edge_buckets))
        if contains_properly:
            contains_updates.append((row, col))

    _apply_polygon_clip_updates(
        surface_raster_variant=[raster_variants],
        top_hint=None,
        updates=(
            disjoint_cells,
            geom_updates,
            edge_updates,
            contains_updates,
        ),
    )
    return raster_variants


class TestPolygonClipping(unittest.TestCase):
    # Clipping work partitioning.
    def test_polygon_clip_row_ranges_are_balanced_and_deterministic(self):
        self.assertEqual(_polygon_clip_row_ranges(0, 4), [])
        self.assertEqual(
            _polygon_clip_row_ranges(3, 10),
            [(0, 1), (1, 2), (2, 3)],
        )
        self.assertEqual(
            _polygon_clip_row_ranges(104, 11),
            [
                (0, 10),
                (10, 20),
                (20, 30),
                (30, 40),
                (40, 50),
                (50, 59),
                (59, 68),
                (68, 77),
                (77, 86),
                (86, 95),
                (95, 104),
            ],
        )

    def test_polygon_clipping_results_match_for_chunked_and_single_row_ranges(
        self,
    ):
        clipping_poly = shapely.box(0.25, 1.25, 0.75, 1.75)
        shape = (3, 2)

        def make_variants():
            top = RasterVariants(
                original=numpy.ones(shape),
                nan_close=None,
                dilated=None,
                edge_interpolation=None,
            )
            bottom = RasterVariants(
                original=numpy.full(shape, 2.0),
                nan_close=None,
                dilated=None,
                edge_interpolation=None,
            )
            top.polygon_intersection_geometry = numpy.full(
                shape, None, dtype=object
            )
            top.polygon_intersection_edge_buckets = numpy.full(
                shape, None, dtype=object
            )
            top.polygon_intersection_contains_properly = numpy.zeros(
                shape, dtype=bool
            )
            return [top, bottom], numpy.full(shape, 3.0)

        def apply_row_ranges(row_ranges):
            variants, top_hint = make_variants()
            for row_range in row_ranges:
                updates = _process_polygon_clip_rows(
                    row_range,
                    clipping_print2d_polys=[clipping_poly],
                    cell_size_mm=1.0,
                    tile_y_shape=shape[0],
                    grid_width=shape[1],
                )
                _apply_polygon_clip_updates(
                    surface_raster_variant=variants,
                    top_hint=top_hint,
                    updates=updates,
                )
            return variants, top_hint

        def geometry_counts(raster_variant):
            counts = numpy.zeros(shape, dtype=int)
            for location, value in numpy.ndenumerate(
                raster_variant.polygon_intersection_geometry
            ):
                counts[location] = 0 if value is None else len(value)
            return counts

        def edge_bucket_counts(raster_variant):
            counts = numpy.zeros(shape, dtype=int)
            for location, value in numpy.ndenumerate(
                raster_variant.polygon_intersection_edge_buckets
            ):
                if value is not None:
                    counts[location] = sum(
                        len(edges) for edges in value.values()
                    )
            return counts

        serial_variants, serial_hint = apply_row_ranges([(0, shape[0])])
        chunked_variants, chunked_hint = apply_row_ranges(
            _polygon_clip_row_ranges(shape[0], 2)
        )

        numpy.testing.assert_array_equal(
            numpy.isnan(serial_variants[0].original),
            numpy.isnan(chunked_variants[0].original),
        )
        numpy.testing.assert_array_equal(
            numpy.isnan(serial_variants[1].original),
            numpy.isnan(chunked_variants[1].original),
        )
        numpy.testing.assert_array_equal(
            numpy.isnan(serial_hint),
            numpy.isnan(chunked_hint),
        )
        numpy.testing.assert_array_equal(
            serial_variants[0].polygon_intersection_contains_properly,
            chunked_variants[0].polygon_intersection_contains_properly,
        )
        numpy.testing.assert_array_equal(
            geometry_counts(serial_variants[0]),
            geometry_counts(chunked_variants[0]),
        )
        numpy.testing.assert_array_equal(
            edge_bucket_counts(serial_variants[0]),
            edge_bucket_counts(chunked_variants[0]),
        )

    # Clipping geometry and cell classification.
    def test_overlapping_clipping_polygons_merge_into_one_footprint(self):
        polygons = _union_clipping_polygons(
            [
                shapely.box(0.0, 0.0, 1.0, 1.0),
                shapely.box(0.5, 0.0, 1.5, 1.0),
            ]
        )

        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0].area, 1.5)

    def test_fully_contained_cell_sets_mask_without_storing_clipped_geometry(
        self,
    ):
        disjoint, geoms, edge_buckets, contains_properly = (
            find_intersection_geometries(
                clippingPrint2DPoly=shapely.box(-1.0, -1.0, 2.0, 2.0),
                quadPrint2DCoords=[
                    (0.0, 1.0),
                    (0.0, 0.0),
                    (1.0, 0.0),
                    (1.0, 1.0),
                ],
            )
        )

        self.assertFalse(disjoint)
        self.assertIsNone(geoms)
        self.assertIsNone(edge_buckets)
        self.assertTrue(contains_properly)

    # Low-level overlapping-edge matching.
    def test_long_polygon_edge_splits_to_match_neighbor_segments_and_marks_wall(
        self,
    ):
        testEdges = createTestOverlappingEdges()

        cell_A_edges = testEdges[0]
        cell_B_edges = testEdges[1]

        mark_overlapping_edges_for_walls(cell_1_edges=cell_A_edges, cell_2_edges=cell_B_edges)

        self.assertTrue(len(cell_A_edges) == 4)

        self.assertTrue(len(cell_A_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_A_edges[0].polygon_line == True)
        self.assertTrue(cell_A_edges[0].make_wall == True)

        self.assertTrue(len(cell_A_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_A_edges[3].polygon_line == True)
        self.assertTrue(cell_A_edges[3].make_wall == False)

        self.assertTrue(len(cell_B_edges) == 4)

        self.assertTrue(len(cell_B_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_B_edges[0].polygon_line == False)
        self.assertTrue(cell_B_edges[0].make_wall == False)

        self.assertTrue(cell_B_edges[1].make_wall == False)
        self.assertTrue(cell_B_edges[2].make_wall == False)

        self.assertTrue(len(cell_B_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_B_edges[3].polygon_line == True)
        self.assertTrue(cell_B_edges[3].make_wall == False)

        # Check if all edges are matched (shown by marking for skip)
        for edge in cell_A_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)

        for edge in cell_B_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)

    def test_overlapping_edge_wall_marking_is_independent_of_argument_order(
        self,
    ):
        testEdges = createTestOverlappingEdges()

        cell_B_edges = testEdges[1]
        cell_A_edges = testEdges[0]

        mark_overlapping_edges_for_walls(cell_1_edges=cell_B_edges, cell_2_edges=cell_A_edges)

        self.assertTrue(len(cell_A_edges) == 4)

        self.assertTrue(len(cell_A_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_A_edges[0].polygon_line == True)
        self.assertTrue(cell_A_edges[0].make_wall == True)  # don't make wall on cell 2(A) if flipped

        self.assertTrue(len(cell_A_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_A_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_A_edges[3].polygon_line == True)
        self.assertTrue(cell_A_edges[3].make_wall == False)

        self.assertTrue(len(cell_B_edges) == 4)

        self.assertTrue(len(cell_B_edges[0].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[0][1] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[0].geometry.coords[-1][1] == 10)
        self.assertTrue(cell_B_edges[0].polygon_line == False)
        self.assertTrue(cell_B_edges[0].make_wall == False)

        self.assertTrue(cell_B_edges[1].make_wall == False)
        self.assertTrue(cell_B_edges[2].make_wall == False)

        self.assertTrue(len(cell_B_edges[3].geometry.coords) == 2)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[0][1] == 30)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][0] == 0)
        self.assertTrue(cell_B_edges[3].geometry.coords[-1][1] == 50)
        self.assertTrue(cell_B_edges[3].polygon_line == True)
        self.assertTrue(cell_B_edges[3].make_wall == False)

        # Check if all edges are matched (shown by marking for skip)
        for edge in cell_A_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)

        for edge in cell_B_edges:
            self.assertTrue(edge.skip_future_eval_for_walls == True)

        # cell_2_edges: list[BorderEdge] = [
        #     BorderEdge(geometry = LineString([(0,0), (0,5)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,5), (5,10)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(5,10), (0,15)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,15), (0,20)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,20), (7,25)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(7,25), (0,30)]), polygon_line=False),
        #     BorderEdge(geometry = LineString([(0,30), (0,50)]), polygon_line=False),
        #     ]

    # Wall decisions between neighboring cell states.
    def test_adjacent_contained_cells_do_not_create_shared_wall_edges(self):
        buckets = numpy.full((1, 2), None, dtype=object)
        elevation = numpy.ones((1, 2))
        contains = numpy.array([[True, True]])

        mark_shared_edges_for_walls(
            polygon_intersection_edge_buckets=buckets,
            elevation_raster=elevation,
            direction=(-1, -1),
            polygon_intersection_contains_properly=contains,
            cell_size_mm=1.0,
        )

        self.assertIsNone(buckets[0, 0])
        self.assertIsNone(buckets[0, 1])

    def test_shared_edge_between_partial_and_contained_cells_does_not_make_wall(
        self,
    ):
        buckets = numpy.full((1, 2), None, dtype=object)
        buckets[0, 1] = empty_edge_buckets()
        west_edge = BorderEdge(
            geometry=shapely.LineString([(1.0, 1.0), (1.0, 0.0)]),
            polygon_line=True,
        )
        buckets[0, 1]["W"].append(west_edge)
        elevation = numpy.ones((1, 2))
        contains = numpy.array([[True, False]])

        mark_shared_edges_for_walls(
            polygon_intersection_edge_buckets=buckets,
            elevation_raster=elevation,
            direction=(-1, -1),
            polygon_intersection_contains_properly=contains,
            cell_size_mm=1.0,
        )

        self.assertFalse(west_edge.make_wall)
        self.assertTrue(west_edge.skip_future_eval_for_walls)

    # Visualization scenarios.
    def test_contained_cell_outside_boundaries_are_walls_visualization(
        self,
    ):
        buckets = numpy.full((1, 1), None, dtype=object)
        elevation = numpy.ones((1, 1))
        contains = numpy.array([[True]])

        mark_shared_edges_for_walls(
            polygon_intersection_edge_buckets=buckets,
            elevation_raster=elevation,
            direction=(-1, -1),
            polygon_intersection_contains_properly=contains,
            cell_size_mm=1.0,
        )

        edge_groups = clipping_wall_visualization_edges(
            polygon_intersection_edge_buckets=buckets,
            elevation_raster=elevation,
            polygon_intersection_contains_properly=contains,
            cell_size_mm=1.0,
        )
        wall_edges = [edge for group in edge_groups for edge in group]
        self.assertEqual(len(wall_edges), 4)
        self.assertTrue(all(edge.make_wall for edge in wall_edges))

        edge_record_groups = clipping_wall_visualization_edge_records(
            polygon_intersection_edge_buckets=buckets,
            elevation_raster=elevation,
            polygon_intersection_contains_properly=contains,
            cell_size_mm=1.0,
        )
        contained_wall_record = edge_record_groups[0][0]
        self.assertEqual(
            border_edge_plot_style(contained_wall_record)["linestyle"],
            "-.",
        )
        self.assertEqual(
            border_edge_plot_style(contained_wall_record)["linewidth"],
            4,
        )
        fig, axes = plot_shapely_geometries_colormap(
            edgeBuckets=edge_record_groups,
            show=False,
        )
        legend = axes.get_legend()
        self.assertIsNotNone(legend)
        self.assertEqual(
            [text.get_text() for text in legend.get_texts()],
            ["Wall from fully contained cell"],
        )
        plt.close(fig)

    def test_custom_polygon_clips_cell_grid_and_marks_walls_visualization(
        self,
    ):
        testData = createTestPolygonCellIntersectionData()
        clippingPrint2DPoly = testData[0]

        raster_variants = RasterVariants(
            original=numpy.ones((3, 2)),
            nan_close=None,
            dilated=None,
            edge_interpolation=None,
        )
        raster_variants.polygon_intersection_geometry = numpy.full(
            raster_variants.original.shape, None, dtype=object
        )
        raster_variants.polygon_intersection_edge_buckets = numpy.full(
            raster_variants.original.shape, None, dtype=object
        )
        raster_variants.polygon_intersection_contains_properly = numpy.zeros(
            raster_variants.original.shape, dtype=bool
        )

        clippingPrint2DPolyIndexMap = numpy.arange(6).reshape(raster_variants.original.shape)

        disjoint_cells = []
        geom_updates = []
        edge_updates = []
        contains_updates = []

        for j in range(0, raster_variants.original.shape[0]):  # Y
            for i in range(0, raster_variants.original.shape[1]):  # X
                quad_coords = testData[1][clippingPrint2DPolyIndexMap[j][i]]
                disjoint, geoms, edge_buckets, contains_properly = find_intersection_geometries(
                    clippingPrint2DPoly=clippingPrint2DPoly,
                    quadPrint2DCoords=quad_coords,
                )

                if disjoint:
                    disjoint_cells.append((j, i))

                if geoms:
                    geom_updates.append((j, i, geoms))

                if edge_buckets and any(len(v) > 0 for v in edge_buckets.values()):
                    edge_updates.append((j, i, edge_buckets))

                if contains_properly:
                    contains_updates.append((j, i))

        _apply_polygon_clip_updates(
            surface_raster_variant=[raster_variants],
            top_hint=None,
            updates=(disjoint_cells, geom_updates, edge_updates, contains_updates),
        )

        self.assertTrue(~numpy.isnan(raster_variants.original[0][0]))
        self.assertTrue(~numpy.isnan(raster_variants.original[0][1]))
        self.assertTrue(~numpy.isnan(raster_variants.original[1][0]))
        self.assertTrue(~numpy.isnan(raster_variants.original[1][1]))
        self.assertTrue(numpy.isnan(raster_variants.original[2][0]))
        self.assertTrue(numpy.isnan(raster_variants.original[2][1]))

        mark_shared_edges_for_walls(
            polygon_intersection_edge_buckets=raster_variants.polygon_intersection_edge_buckets,
            elevation_raster=raster_variants.original,
            direction=(-1, -1),
            polygon_intersection_contains_properly=(
                raster_variants.polygon_intersection_contains_properly
            ),
            cell_size_mm=29.0,
        )

        edgeBucketsFlattenedPerCell = []
        for j in range(0, raster_variants.original.shape[0]):  # Y
            for i in range(0, raster_variants.original.shape[1]):  # X
                if raster_variants.polygon_intersection_edge_buckets[j][i] is not None:
                    edgeBucketsFlattenedPerCell += [
                        raster_variants.polygon_intersection_edge_buckets[j][i]["N"]
                        + raster_variants.polygon_intersection_edge_buckets[j][i]["W"]
                        + raster_variants.polygon_intersection_edge_buckets[j][i]["S"]
                        + raster_variants.polygon_intersection_edge_buckets[j][i]["E"]
                        + raster_variants.polygon_intersection_edge_buckets[j][i]["other"]
                    ]

        self.assertTrue(len(raster_variants.polygon_intersection_edge_buckets[0][0]["N"]) == 1)
        self.assertTrue(raster_variants.polygon_intersection_edge_buckets[0][0]["N"][0].make_wall)
        self.assertTrue(len(edgeBucketsFlattenedPerCell) > 0)

        edge_groups = clipping_wall_visualization_edge_records(
            polygon_intersection_edge_buckets=(
                raster_variants.polygon_intersection_edge_buckets
            ),
            elevation_raster=raster_variants.original,
            polygon_intersection_contains_properly=(
                raster_variants.polygon_intersection_contains_properly
            ),
            cell_size_mm=29.0,
        )
        fig, _axes = plot_shapely_geometries_colormap(
            basePolys=[
                clippingPrint2DPoly,
                *(shapely.Polygon(quad_coords) for quad_coords in testData[1]),
            ],
            intersectionPolys=[
                geoms
                for geoms in raster_variants.polygon_intersection_geometry.flat
                if geoms is not None
            ],
            edgeBuckets=edge_groups,
            show=SHOW_WALL_PLOTS,
        )
        plt.close(fig)

    def test_shared_edge_between_contained_and_partial_cells_is_not_wall_visualization(
        self,
    ):
        (
            clipping_polygon,
            quad_coords_by_location,
            shape,
            cell_size,
        ) = create_contained_partial_clip_cell_grid_data()
        raster_variants = clip_test_cell_grid(
            clipping_polygon=clipping_polygon,
            quad_coords_by_location=quad_coords_by_location,
            shape=shape,
        )

        contained_location = (2, 2)
        partial_location = (2, 3)

        self.assertTrue(
            raster_variants.polygon_intersection_contains_properly[
                contained_location
            ]
        )
        self.assertIsNone(
            raster_variants.polygon_intersection_geometry[
                contained_location
            ]
        )
        self.assertIsNone(
            raster_variants.polygon_intersection_edge_buckets[
                contained_location
            ]
        )
        self.assertFalse(
            raster_variants.polygon_intersection_contains_properly[
                partial_location
            ]
        )
        self.assertIsInstance(
            raster_variants.polygon_intersection_edge_buckets[
                partial_location
            ],
            dict,
        )
        perimeter = numpy.concatenate(
            (
                raster_variants.original[0, :],
                raster_variants.original[-1, :],
                raster_variants.original[1:-1, 0],
                raster_variants.original[1:-1, -1],
            )
        )
        self.assertTrue(numpy.isnan(perimeter).all())

        mark_shared_edges_for_walls(
            polygon_intersection_edge_buckets=(
                raster_variants.polygon_intersection_edge_buckets
            ),
            elevation_raster=raster_variants.original,
            direction=(-1, -1),
            polygon_intersection_contains_properly=(
                raster_variants.polygon_intersection_contains_properly
            ),
            cell_size_mm=cell_size,
        )

        edge_groups = clipping_wall_visualization_edge_records(
            polygon_intersection_edge_buckets=(
                raster_variants.polygon_intersection_edge_buckets
            ),
            elevation_raster=raster_variants.original,
            polygon_intersection_contains_properly=(
                raster_variants.polygon_intersection_contains_properly
            ),
            cell_size_mm=cell_size,
        )
        flat_records = [
            record for group in edge_groups for record in group
        ]
        flat_edges = [record.edge for record in flat_records]
        shared_side = shapely.LineString([(3.0, 2.0), (3.0, 3.0)])
        partial_edge_buckets = (
            raster_variants.polygon_intersection_edge_buckets[
                partial_location
            ]
        )
        shared_partial_edges = [
            edge
            for edge in partial_edge_buckets["W"]
            if edge.geometry.equals(shared_side)
        ]
        self.assertEqual(len(shared_partial_edges), 1)
        non_wall_edge = shared_partial_edges[0]
        non_wall_record = next(
            record
            for record in flat_records
            if record.edge is non_wall_edge
        )
        stored_wall_record = next(
            record
            for record in flat_records
            if (
                record.source == "stored_clipped_edge"
                and record.edge.make_wall
            )
        )

        self.assertIn(non_wall_edge, flat_edges)
        self.assertIn(stored_wall_record.edge, flat_edges)
        self.assertFalse(non_wall_edge.make_wall)
        self.assertTrue(non_wall_edge.skip_future_eval_for_walls)
        self.assertEqual(
            border_edge_plot_style(non_wall_record)["linestyle"],
            ":",
        )
        self.assertEqual(
            border_edge_plot_style(non_wall_record)["linewidth"],
            3,
        )
        self.assertEqual(
            border_edge_plot_style(stored_wall_record)["linestyle"],
            "-",
        )
        self.assertEqual(
            border_edge_plot_style(stored_wall_record)["linewidth"],
            6,
        )
        ordered_plot_edges = [
            record
            for _group_index, record in border_edges_for_plot(edge_groups)
        ]
        self.assertLess(
            max(
                index
                for index, record in enumerate(ordered_plot_edges)
                if record.edge.make_wall
            ),
            min(
                index
                for index, record in enumerate(ordered_plot_edges)
                if not record.edge.make_wall
            ),
        )

        fig, axes = plot_shapely_geometries_colormap(
            basePolys=[
                clipping_polygon,
                *(
                    shapely.Polygon(quad_coords)
                    for quad_coords in quad_coords_by_location.values()
                ),
            ],
            intersectionPolys=[
                geoms
                for geoms in (
                    raster_variants.polygon_intersection_geometry.flat
                )
                if geoms is not None
            ],
            edgeBuckets=edge_groups,
            show=SHOW_WALL_PLOTS,
        )
        self.assertIsNotNone(fig)
        self.assertGreaterEqual(len(axes.lines), len(flat_edges))
        legend = axes.get_legend()
        self.assertIsNotNone(legend)
        self.assertEqual(
            [text.get_text() for text in legend.get_texts()],
            [
                "Base polygon / cell boundary",
                "Clipped intersection geometry",
                "Wall from partially clipped cell",
                "Ownership edge (no wall)",
            ],
        )
        plt.close(fig)
