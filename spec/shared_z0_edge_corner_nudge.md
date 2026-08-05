# Shared Z=0 Edge Corner Nudge

## Scope

This fix applies only to exact `Z=0` topology cases where a cell corner has
`top.z == bottom.z == 0`. It uses no tolerance and does not handle `Z > 0`
contact cases or all-4-corner cases.

The first implementation covers 1 affected corner, 2 adjacent affected corners,
2 opposite affected corners, and 3 affected corners.

When `nudge_in_overused_edges_vertex` is enabled, both regular square cells and
polygon-clipped cells must be handled. If clipped cells are not handled, a
nudged square cell can leave a gap or keep a nonmanifold `Z=0` edge where it
neighbors clipped-boundary geometry.

## Confirmation Criteria

Z=0 nudge confirmation must identify zero-height border/contact cells, not
every emitted `Z=0` cell and not arbitrary clipped/null raster boundaries.

A cell is confirmed for Z=0 nudging only when all of these are true:

```text
1. The cell is emitted.
2. The cell is a Z=0 candidate in the detection raster.
3. At least one of the cell's interpolation corners has a positive-Z
   contributing cell.
```

This selects Z=0 cells that sit next to positive terrain. It excludes deep
interior Z=0 cells that are completely surrounded by Z=0 or lower cells.

Within a confirmed Z=0 cell, affected corners are the corners that do not have
a positive-Z contributing cell. These are the outside zero-height contact
corners to remove from the normal mesh footprint. The all-4-corner case remains
outside the nudge behavior because it represents a fully surrounded or fully
zero-contact footprint, not a border/corner transition that needs a local
inside nudge.

Do not treat an ordinary clipped raster boundary, preclipped null-cell boundary,
or one-corner clipped footprint as sufficient confirmation by itself. Nudging
must not move or invent geometry along an external clip/null boundary unless
the emitted cell also satisfies the Z=0 border/contact criteria above.

Assume the reader already understands how cells, top surfaces, bottom surfaces,
and walls are generated in TouchTerrain.

Terminology:

```text
Corners:   SW, SE, NE, NW
Midpoints: Smid, Emid, Nmid, Wmid
```

Midpoint vertices are always placed exactly halfway along the original cell
edge, with `Z=0`. The nudge distance is exactly half a cell width.

Examples of the nudging in 3D mesh are in z0-normal-difference-nudge-demo.3mf and z0-normal-difference-nudge-clipped-demo.3mf.
normal before nudge, gray
normal after nudge, blue
difference before nudge, orange
difference after nudge, green

## Normal Mesh Mode

Normal mode removes exact `Z=0` contact regions from the mesh footprint.

Rules:

```text
1. Detect affected corners where top.z == bottom.z == 0.
2. Remove affected corner vertices from both top and bottom footprints.
3. Add midpoint vertices exactly halfway along original cell edges.
4. Use the same clipped XY footprint for top and bottom.
5. Rebuild exterior walls only from the final clipped footprint.
6. Omit wall faces whose top and bottom edge are exactly identical at Z=0.
```

### One Affected Corner

One affected corner produces a pentagon. Example, `SW` affected:

```text
SW is removed.
Smid and Wmid are added.

Final footprint:
Smid -> SE -> NE -> NW -> Wmid -> Smid
```

All rotations:

```text
SW affected: Smid -> SE -> NE -> NW -> Wmid -> Smid
SE affected: SW -> Smid -> Emid -> NE -> NW -> SW
NE affected: SW -> SE -> Emid -> Nmid -> NW -> SW
NW affected: SW -> SE -> NE -> Nmid -> Wmid -> SW
```

### Two Adjacent Affected Corners

Two adjacent affected corners produce a clipped quad / half-cell. Example,
south edge affected:

```text
SW and SE are removed.
Wmid and Emid are added.

Final footprint:
Wmid -> Emid -> NE -> NW -> Wmid
```

All rotations:

```text
south affected: Wmid -> Emid -> NE -> NW -> Wmid
east affected:  SW -> Smid -> Nmid -> NW -> SW
north affected: SW -> SE -> Emid -> Wmid -> SW
west affected:  Smid -> SE -> NE -> Nmid -> Smid
```

### Three Affected Corners

Three affected corners produce a triangle around the only nonzero-height corner.
Example, only `SE` is nonzero:

```text
SW, NW, and NE are removed.
Smid and Emid are added.

Final footprint:
Smid -> SE -> Emid -> Smid
```

All rotations:

```text
only SE is H: Smid -> SE -> Emid -> Smid
only SW is H: SW -> Smid -> Wmid -> SW
only NW is H: Wmid -> Nmid -> NW -> Wmid
only NE is H: Nmid -> Emid -> NE -> Nmid
```

## Difference Mesh Mode

Difference mode represents the volume between a lower raster and an upper
raster. The fix is applied to the lower/bottom surface of the difference mesh.
The upper/top surface keeps the original difference-mesh footprint and
upper-raster heights.

Rules:

```text
1. Do not clip the difference mesh top footprint.
2. Keep the original full top footprint.
3. Modify the difference mesh bottom surface only.
4. The bottom surface contains:
   - the same clipped surface used by normal-after top geometry;
   - plus the complementary Z=0 patch where normal mode removed coverage.
5. The complementary patch uses the opposite footprint from normal mode.
6. Midpoint vertices are exactly on original edges at Z=0.
7. Rebuild side walls from the full top footprint down to the corrected bottom boundary.
```

The key distinction is:

```text
Normal mode removes Z=0 contact area from the whole mesh footprint.

Difference mode keeps the full top footprint, but repairs the lower surface by
combining normal-after lower-raster coverage with complementary Z=0 coverage.
```

### One Affected Corner

For one affected corner, normal mode removes the corner triangle. Difference
mode keeps that removed region as a complementary `Z=0` bottom patch.

Example, `SW` affected:

```text
Normal clipped footprint:
Smid -> SE -> NE -> NW -> Wmid -> Smid

Difference complementary Z=0 bottom patch:
SW -> Smid -> Wmid -> SW

Difference top footprint remains:
SW -> SE -> NE -> NW -> SW
```

All complementary bottom patches:

```text
SW affected: SW -> Smid -> Wmid -> SW
SE affected: SE -> Emid -> Smid -> SE
NE affected: NE -> Nmid -> Emid -> NE
NW affected: NW -> Wmid -> Nmid -> NW
```

### Two Adjacent Affected Corners

For two adjacent affected corners, normal mode keeps the opposite half-cell.
Difference mode adds the removed edge-side half-cell as the complementary
`Z=0` bottom patch.

Example, south edge affected:

```text
Normal clipped footprint:
Wmid -> Emid -> NE -> NW -> Wmid

Difference complementary Z=0 bottom patch:
SW -> SE -> Emid -> Wmid -> SW

Difference top footprint remains:
SW -> SE -> NE -> NW -> SW
```

All complementary bottom patches:

```text
south affected: SW -> SE -> Emid -> Wmid -> SW
east affected:  SE -> NE -> Nmid -> Smid -> SE
north affected: NW -> Wmid -> Emid -> NE -> NW
west affected:  SW -> Smid -> Nmid -> NW -> SW
```

### Three Affected Corners

For three affected corners, normal mode keeps only the triangle around the
single high corner. Difference mode adds the remaining complementary polygon as
the `Z=0` bottom patch.

Example, only `SE` is high:

```text
Normal clipped footprint:
Smid -> SE -> Emid -> Smid

Difference complementary Z=0 bottom patch:
SW -> Smid -> Emid -> NE -> NW -> SW

Difference top footprint remains:
SW -> SE -> NE -> NW -> SW
```

All complementary bottom patches:

```text
only SE is H: SW -> Smid -> Emid -> NE -> NW -> SW
only SW is H: Smid -> SE -> NE -> NW -> Wmid -> Smid
only NW is H: SW -> SE -> NE -> Nmid -> Wmid -> SW
only NE is H: SW -> SE -> Emid -> Nmid -> NW -> SW
```

## Two Opposite Affected Corners

Include 2-opposite-corner cases in the first implementation. Treat this case as
two independent 1-corner clips in the same cell.

Unlike 2-adjacent-corner cases, opposite affected corners do not form a shared
`Z=0` edge within the cell. They are still included so the clipping behavior is
complete for all partial-corner combinations except the all-4-corner case.

Example, `SW` and `NE` affected:

```text
Normal final footprint:
Smid -> SE -> Emid -> Nmid -> NW -> Wmid -> Smid

Difference complementary Z=0 bottom patches:
SW -> Smid -> Wmid -> SW
NE -> Nmid -> Emid -> NE

Difference top footprint remains:
SW -> SE -> NE -> NW -> SW
```

Opposite rotation, `SE` and `NW` affected:

```text
Normal final footprint:
SW -> Smid -> Emid -> NE -> Nmid -> Wmid -> SW

Difference complementary Z=0 bottom patches:
SE -> Emid -> Smid -> SE
NW -> Wmid -> Nmid -> NW

Difference top footprint remains:
SW -> SE -> NE -> NW -> SW
```

## Clipped Cells

Clipped cells must be handled when `nudge_in_overused_edges_vertex` is enabled.
If they are not handled, a nudged square cell can leave a gap or keep a
nonmanifold `Z=0` edge where it neighbors clipped-boundary geometry.

Clipped cells use the same affected-corner classification and nudge footprint
definitions as regular square cells. The difference is that clipped cells start
from an irregular existing clipped footprint, so the nudge operation is a
polygon operation rather than a fixed vertex-list rewrite.

The emitted clipped cell footprint is the hard source mask for Z=0 nudge edits.
If a cell has clipped surface polygons, use their 2D union as the cell
footprint. Otherwise use the full raster-cell footprint. Every normal keep
piece and difference complementary patch must be intersected with that emitted
footprint. Do not synthesize geometry outside the clipped/preclipped raster
footprint.

The general clipped-cell rule is:

```text
1. Start with the existing clipped cell footprint.
2. Apply the normal nudge keep footprint or difference complementary patches
   against that irregular footprint.
3. Triangulate the resulting polygon or polygons.
4. Assign top and bottom Z from the nudge-adjusted surfaces.
```

If polygon operations produce multiple polygons, triangulate and emit each
polygon independently. Empty normal-mode results remove that cell's normal
geometry for the affected footprint. Exact `Z=0` comparisons remain exact; no
tolerance is introduced.

### Normal Mode For Clipped Cells

For each clipped cell, compute the affected corner set from exact
`top.z == bottom.z == 0`, using the same corner definitions as regular cells.
Build the same normal-mode nudge keep footprint for that affected-corner case.

The final normal clipped footprint is:

```text
final_normal_footprint =
    existing_clipped_footprint intersected with normal_nudge_keep_footprint
```

Top and bottom use the same final XY footprint. The bottom Z is `0`.

Top Z is interpolated from the nudged normal top surface:

```text
- original kept corners retain their top heights;
- inserted midpoint vertices are exactly on original edges at Z=0;
- new clipped/intersection vertices on nudge cut edges inherit Z from the
  nudged surface.
```

Rebuild walls only on true exterior boundaries:

```text
- preserved clipped-boundary edges that already require walls;
- new nudge cut edges introduced by removing the Z=0 region;
- preserved tile/NaN border edges.
```

Do not create walls on ordinary shared cell edges that remain internal.

### Difference Mode For Clipped Cells

The difference mesh top footprint remains the existing clipped footprint, with
upper-raster heights.

The difference mesh bottom surface is split into:

```text
existing_clipped_footprint intersected with normal_nudge_keep_footprint
    uses the same lower surface as normal-after

existing_clipped_footprint intersected with each complementary_Z0_patch
    uses Z=0
```

The union of those bottom pieces must cover the same XY footprint as the clipped
top footprint. Internal seams between the normal-lower-surface part and the
complementary `Z=0` patches are bottom-surface seams, not vertical walls.

Exterior side walls connect the clipped top boundary to the corrected bottom
boundary. Split boundary edges at inserted midpoint/intersection vertices as
needed, and omit exact duplicate zero-height wall faces.
