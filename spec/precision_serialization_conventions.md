# Precision And Serialization Conventions

## Summary

TouchTerrain cell geometry should stay at full in-memory precision while it is
being constructed. Rounding and mesh-serialization normalization are topology
comparison tools and final-output cleanup tools, not geometry construction
tools.

This convention exists so neighboring cells compute the same shared vertices,
walls close without cracks, and validation checks compare the same coordinates
that the emitted mesh actually contains.

## Core Rule

Use raw in-memory coordinates for geometry construction and interpolation.
Normalize only when code needs to compare against final emitted mesh semantics.

Keep raw precision for:

```text
- raster-derived corner heights;
- cell W/E/N/S coordinates;
- nudge midpoint creation;
- Z interpolation;
- clipped polygon interpolation;
- provider surface interpolation;
- local cell surface construction.
```

Do not round, decimal-truncate, or `STLb` float32-normalize before Z
interpolation. Adjacent cells that share an edge must interpolate split points
from the same raw shared endpoints. If one side interpolates from normalized
endpoints while the other side uses raw endpoints, the same serialized XY point
can receive different Z values and create a boundary crack.

## Serialized Coordinates

Serialized-coordinate comparison means "the coordinate as the output mesh will
effectively contain it."

For `STLb`, this means:

```text
1. Convert the coordinate to binary STL float32.
2. Convert it back to Python float.
3. Round to 6 decimals.
4. Convert negative zero to positive zero.
```

This matches `normalize_coordinate_to_match_mesh_serialization()`.

For `STLa`, this means:

```text
1. Keep the Python float value.
2. Round to 6 decimals, matching ASCII STL text precision.
3. Convert negative zero to positive zero.
```

Use `normalize_vertex_to_match_mesh_serialization()` when comparing full 3D
vertices.

## When To Normalize

Normalize when the code is intentionally asking a final-output topology
question:

```text
- Does this emitted triangle edge match another emitted triangle edge?
- Is this serialized 3D edge overused?
- Is this serialized edge a boundary edge?
- Does this triangle collapse after mesh serialization?
- Does this surface triangle lose all XY area after mesh serialization?
- Do top and bottom boundary edges match closely enough to rebuild a wall?
- Does a validation script see the same coordinates as the emitted STL?
```

Common production helpers for this include:

```text
- normalize_coordinate_to_match_mesh_serialization()
- normalize_vertex_to_match_mesh_serialization()
- polygon_normalized_to_match_mesh_serialization()
- surface_polygon_normalized_to_match_mesh_serialization()
- remove_geometry_collapsed_by_mesh_serialization()
```

Final per-cell cleanup should be the central safety net for geometry that only
becomes invalid after output serialization. Do not compensate for those cases by
rounding earlier during interpolation.

## Edge And Footprint Keys

Use orientation-independent serialized 3D edge keys when comparing emitted mesh
edges. The key should contain the two serialized 3D endpoints sorted without
regard to triangle winding.

Use serialized XY edge keys only when the comparison is intentionally about a
2D footprint, such as matching top and bottom boundary edges while rebuilding
walls.

Do not apply surface XY-area collapse rules to vertical wall faces. Walls may
intentionally have line-like XY footprints while still being valid 3D geometry.
Surface polygons represent area-bearing top or bottom coverage and may be
removed when their serialized XY area collapses.

## Do

```text
- Do construct cell, nudge, and clipped geometry with raw coordinates.
- Do interpolate Z from raw in-memory surface planes.
- Do let neighboring cells compute shared split-point Z from their own raw
  shared endpoints.
- Do normalize for emitted edge identity, edge counts, duplicate checks,
  collapse checks, wall-boundary matching, and validation.
- Do keep validation scripts aligned with the same serialized-coordinate rule
  used by production topology checks.
```

## Do Not

```text
- Do not round cell coordinates before interpolation.
- Do not normalize nudge interpolation planes before computing midpoint or
  split-point Z.
- Do not pass normalized split vertices between cells as a substitute for each
  cell's own local raw interpolation.
- Do not normalize one side of a shared edge earlier than the neighboring side.
- Do not use ad hoc string or decimal rounding for topology keys when the
  mesh-serialization helper already exists.
- Do not remove vertical wall geometry only because its XY footprint is a line.
```

## Relationship To Nudging

The Z=0 and positive-Z nudge specs rely on this precision convention.

For Z=0 nudging, inserted midpoint XY coordinates are exact half-cell positions,
and midpoint Z is exactly `0`. New clipped/intersection vertices should still be
interpolated from raw nudge-adjusted surfaces before final serialization
cleanup.

For positive-Z nudging, inserted midpoint and split vertices are not forced to
`0`. Their Z values come from the positive upper or lower-normal surface. The
normal and difference meshes should agree at the interface because both consume
the same nudge plan and interpolate from raw surfaces before serialization.

See also:

```text
- spec/shared_z0_edge_corner_nudge.md
- spec/positive_z_overused_edge_nudge.md
```
