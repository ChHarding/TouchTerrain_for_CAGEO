import unittest 
import numpy
from touchterrain.common.TouchTerrainGPX import plotLineWithThickness

grid_width = 10
grid_height = 10
original_height = 2
height_offset = 5
line_height = original_height + height_offset

class PlotLineTests(unittest.TestCase):

    def _print_points(self):
        print(self.points)
    
    def _assert_expected_line_points(self, expected_line_points):
        # iterate over the entire grid making sure only the expected line points have the increased height
        for x in range(grid_width):
            for y in range(grid_height):
                if [x, y] in expected_line_points:
                    self.assertEqual(self.points[x][y], line_height, "Point [{},{}] expected to be on the line but actually isn't".format(x, y))
                else:
                    self.assertEqual(self.points[x][y], original_height, "Point [{},{}] expected not to be on the line but actually is".format(x, y))

    def setUp(self):
        self.points = numpy.full(shape=(grid_width, grid_height),fill_value=original_height)
        self.pathed_points = {}

    def test_plot_vertical_line_with_zero_thickness(self):
        plotLineWithThickness(3, 2, 3, 6, height_offset, self.points, self.pathed_points, 0)
        # self._print_points()
        self._assert_expected_line_points([[3,2], [3,3], [3,4], [3,5], [3,6]])

    def test_plot_horizontal_line_with_zero_thickness(self):
        plotLineWithThickness(2, 4, 5, 4, height_offset, self.points, self.pathed_points, 0)
        # self._print_points()
        self._assert_expected_line_points([[2,4], [3,4], [4,4], [5,4]])

    def test_plot_vertical_line_with_nonzero_thickness(self):
        plotLineWithThickness(3, 2, 3, 5, height_offset, self.points, self.pathed_points, 3)
        # self._print_points()
        self._assert_expected_line_points([[2,2], [3,2], [4,2], [2,3], [3,3], [4,3], [2,4], [3,4], [4,4], [2,5], [3,5], [4,5]])

    def test_plot_horizontal_line_with_nonzero_thickness(self):
        plotLineWithThickness(2, 4, 6, 4, height_offset, self.points, self.pathed_points, 3)
        # self._print_points()
        self._assert_expected_line_points([[2,3], [2,4], [2,5], [3,3], [3,4], [3,5], [4,3], [4,4], [4,5], [5,3], [5,4], [5,5], [6,3], [6,4], [6,5]])

    def test_plot_sw_ne_low_slope_diagonal_line_with_nonzero_thickness(self):
        plotLineWithThickness(1, 3, 6, 5, height_offset, self.points, self.pathed_points, 3)
        # self._print_points()
        self._assert_expected_line_points([[1,2], [1,3], [1,4], [2,2], [2,3], [2,4], [3,3], [3,4], [3,5], [4,3], [4,4], [4,5], [5,4], [5,5], [5,6], [6,4], [6,5], [6,6]])

    def test_plot_se_nw_high_slope_diagonal_line_with_nonzero_thickness(self):
        plotLineWithThickness(5, 6, 3, 1, height_offset, self.points, self.pathed_points, 3)
        # self._print_points()
        self._assert_expected_line_points([[4,6], [5,6], [6,6], [4,5], [5,5], [6,5], [3,4], [4,4], [5,4], [3,3], [4,3], [5,3], [2,2], [3,2], [4,2], [2,1], [3,1], [4,1]])

    def test_plot_line_with_nonzero_thickness_draws_flat_topped_line(self):
        # Set some of the points either side of the centre to be higher - track should not just add the offset to
        # these, it should instead create a flat raised line based on the original centre height
        self.points[3][3] = original_height + 1
        self.points[3][2] = original_height + 2
        self.points[5][5] = original_height + 3
        self.points[5][6] = original_height + 4

        plotLineWithThickness(3, 4, 5, 4, height_offset, self.points, self.pathed_points, 5)
        # self._print_points()
        self._assert_expected_line_points([[3,2], [3,3], [3,4], [3,5], [3,6], [4,2], [4,3], [4,4], [4,5], [4,6], [5,2], [5,3], [5,4], [5,5], [5,6]])


if __name__ == '__main__':
    unittest.main(verbosity=3)
