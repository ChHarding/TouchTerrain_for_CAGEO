import shapely

from touchterrain.common.Vertex import vertex


class quad:
    """A three- or four-vertex mesh surface."""

    _default_split_edge: tuple[int, int] = (0, 2)
    _rotated_split_edge: tuple[int, int] = (1, 3)
    __slots__ = ("vl", "forced_split_edge")

    vl: list[vertex | None]
    """Vertices mapping        NW SW SE NE
    - Top                      0  1  2  3
    - Bottom                   0  3  2  1
    """
    forced_split_edge: tuple[int, int] | None
    """Optional internal diagonal override for paired mesh split alignment."""

    def __init__(
        self,
        v0: vertex,
        v1: vertex,
        v2: vertex,
        v3: vertex | None = None,
        forced_split_edge: tuple[int, int] | None = None,
    ) -> None:
        self.vl = [v0, v1, v2, v3]
        self.forced_split_edge = forced_split_edge

    def get_split_edge_indices(
        self,
        split_rotation: int = 0,
    ) -> tuple[int, int]:
        """Return the internal diagonal vertex indexes for this quad."""
        v0, v1, v2, v3 = self.vl
        if v3 is None:
            return quad._default_split_edge

        if self.forced_split_edge is not None:
            return self.forced_split_edge

        if split_rotation not in (1, 2):
            return quad._default_split_edge

        splitting_edge_slope_1 = abs(v0.coords[2] - v2.coords[2])
        splitting_edge_slope_2 = abs(v1.coords[2] - v3.coords[2])
        if (
            split_rotation == 1
            and splitting_edge_slope_1 > splitting_edge_slope_2
        ) or (
            split_rotation == 2
            and splitting_edge_slope_1 < splitting_edge_slope_2
        ):
            return quad._rotated_split_edge

        return quad._default_split_edge

    def get_triangles(
        self,
        split_rotation: int = 0,
    ) -> list[tuple[vertex, ...]]:
        """Return one or two counterclockwise triangles."""
        v0, v1, v2, v3 = self.vl
        if v3 is None:
            return [(v0, v1, v2)]

        if (
            self.get_split_edge_indices(split_rotation)
            == quad._rotated_split_edge
        ):
            return [(v0, v1, v3), (v1, v2, v3)]
        return [(v0, v1, v2), (v0, v2, v3)]

    def get_triangles_in_polygons(
        self,
        split_rotation: int,
    ) -> list[shapely.Polygon]:
        """Return the emitted triangles as 3D Shapely polygons."""
        return [
            shapely.Polygon(
                [
                    triangle[0].coords,
                    triangle[1].coords,
                    triangle[2].coords,
                    triangle[0].coords,
                ]
            )
            for triangle in self.get_triangles(split_rotation)
        ]

    def __str__(self) -> str:
        vertices = "  ".join(
            f"v{index}: {mesh_vertex}"
            for index, mesh_vertex in enumerate(self.vl)
        )
        return f"  {vertices}  "
