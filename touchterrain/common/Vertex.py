class vertex:
    """A mesh vertex identified by its immutable XYZ coordinates."""

    # dict of index value for each vertex
    # key is tuple of coordinates, value is a unique index
    vertex_index_dict = -1
    __slots__ = ("coords",)

    coords: tuple[float, float, float]

    def __init__(self, x: float, y: float, z: float) -> None:
        self.coords = (float(x), float(y), float(z))
        vertex_indexes = vertex.vertex_index_dict

        # for non obj file this is set to -1, and there's no need to deal with vertex indices
        if vertex_indexes != -1:
            # The grid-level dictionary assigns each unique coordinate tuple
            # one shared, monotonically increasing OBJ index.
            if self.coords not in vertex_indexes:
                vertex_indexes[self.coords] = len(vertex_indexes)

    def get_id(self) -> int:
        """Return the OBJ vertex index for these coordinates."""
        return vertex.vertex_index_dict[self.coords]

    def get(self) -> tuple[float, float, float]:
        """Return the XYZ coordinates."""
        return self.coords

    def __str__(self) -> str:
        return "%.2f %.2f %.2f " % (self.coords[0], self.coords[1], self.coords[2])

    def __getitem__(self, index: int) -> float:
        """Return one coordinate by index."""
        return self.coords[index]

    def vertex_rounded_to_precision(self, decimals: int) -> "vertex":
        """Return a vertex rounded to the requested decimal precision."""
        return vertex(*(round(coord, decimals) for coord in self.coords))
