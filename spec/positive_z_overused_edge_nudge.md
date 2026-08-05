# Positive-Z Contact Nudge

## Scope

This spec describes the nudge behavior for exact `Z>0` contact topology cases.
That includes positive-Z overused edges and one-corner positive contacts that
are endpoints of confirmed positive-Z overused edges. It is intentionally
paired with `spec/shared_z0_edge_corner_nudge.md`.

Use the same XY nudge geometry from `shared_z0_edge_corner_nudge.md`:

```text
- same affected-corner sets;
- same midpoint locations;
- same one-corner, two-adjacent, two-opposite, and three-corner footprints;
- same clipped-cell polygon operations;
- same exact comparisons; no tolerance.
```

The important difference is ownership. For `Z=0`, the bad contact is a
base-plane contact in the normal mesh. For `Z>0`, the bad contact is a
positive-height contact between the lower-normal interface and the difference
mesh. Therefore the normal and difference operations are swapped.

Examples of the positive-Z behavior are in:

```text
spec/positive-z-normal-difference-overused-edge-demo.3mf
```

## Problem

A positive-Z contact occurs when a lower-normal surface and a difference mesh
surface both emit the same exact positive-Z vertex or edge. The contact is not
a base-plane contact, and it should not create `Z=0` fill. It is an interlock
problem between the normal mesh generated from the lower raster and the
difference mesh generated between the lower and upper rasters.

The multi-cell failure usually appears as an overused positive-Z edge, where
the lower-normal surface and the difference mesh surface both emit the same
exact positive-Z edge. A one-corner positive contact is a candidate for local
repair only when that exact positive point is an endpoint of a confirmed
positive-Z overused edge. Isolated one-corner positive contacts do not require
nudging.

The affected vertices are exact positive contacts:

```text
upper_or_top.z == lower_or_bottom.z
and
upper_or_top.z > 0
```

Exact equality remains exact Python float equality after the current raster to
mesh coordinate conversion. No tolerance is introduced.

## Confirmation Criteria

Nudge confirmation must be tied to serialized positive-Z overuse. A cell is
confirmed for positive-Z nudging when it has a confirmed positive-Z overused
edge.

One-corner exact positive contact is a candidate only:

```text
upper_or_top.z == lower_or_bottom.z
and
upper_or_top.z > 0
```

Do not nudge an isolated one-corner positive contact. Confirm it only when the
serialized positive contact point is an endpoint of a confirmed positive-Z
overused edge. A one-corner contact stored as either an affected corner or
contact metadata is not enough by itself. When confirmed, the one-corner
contact uses the same footprint definitions as
`shared_z0_edge_corner_nudge.md`.

When a candidate positive contact is not confirmed by a serialized positive-Z
overused edge, leave the local footprints unchanged if the emitted normal and
difference pair interface remains aligned and both meshes remain closed.
Validation should check pair alignment and topology in that case, not require
intermediate nudge midpoint edges or removed contact vertices.

A split-only record with no affected removal corners may still be retained for
pair-interface seam alignment. That record inserts required side midpoints but
does not confirm an isolated one-corner contact or remove a corner footprint.
When a difference-only local promotion turns a split/contact record into a
corner-removal footprint, the adjacent difference cells may receive local
split-only side midpoints so their side edges match the clipped cell. These
derived neighbor splits are not shared affected corners, and their zero-height
cleanup does not get the endpoint-preservation exception unless the neighbor
also has an explicit split-only plan record.

For one-corner, two-adjacent, two-opposite, and three-corner contacts,
confirmation uses the positive-Z contact edges or diagonal contacts created by
the emitted surface topology. Exact comparisons remain exact; do not introduce
tolerance.

In interlocking-pair generation, the source of that emitted topology is the
paired cell being generated, not a separate probe mesh. The normal cell is
created first for the same raster cell, and its corrected emitted top surface
is used as the lower/difference bottom interface for confirming the difference
cell's positive-Z contact. Multi-corner positive-Z cases are confirmed from
the resulting provider-backed difference top/bottom surface contact edges or
diagonal contacts. One-corner positive contacts remain candidates unless their
serialized positive point is an endpoint of one of those confirmed overused
edges.

The implementation may use a serialized-coordinate copy of those provisional
paired-cell surfaces for topology comparison, but the geometry that is finally
emitted should continue to follow the precision convention: interpolate from
raw in-memory cell geometry first, then normalize only for topology keys,
collapse checks, validation, and final output serialization.

Do not treat an ordinary clipped raster boundary, preclipped null-cell boundary,
or one-corner clipped footprint as sufficient confirmation by itself. The
positive-Z nudge applies only to exact positive contact between the
lower-normal interface and the difference mesh:

```text
upper_or_top.z == lower_or_bottom.z
and
upper_or_top.z > 0
```

This keeps separate meshes generated from clipped or preclipped rasters
predictably fitted together. Nudging must not move or invent geometry along an
external clip/null boundary unless that emitted cell also satisfies the exact
positive normal/difference contact criteria above.

## Role Swap From Z=0

The `Z=0` spec defines two operations:

```text
Z=0 normal operation:
    remove affected contact area from the mesh footprint.

Z=0 difference operation:
    keep full top footprint and split the bottom into:
    corrected normal-lower coverage + complementary Z=0 coverage.
```

For positive-Z contact repairs, apply those operations with normal and
difference roles swapped:

```text
Z>0 difference operation:
    use the Z=0 normal operation.
    The difference mesh removes the positive contact area from its footprint.

Z>0 normal operation:
    use the Z=0 difference operation.
    The normal mesh keeps full footprint coverage, split into corrected
    nudged coverage plus complementary positive-Z coverage.
```

## Difference Mesh Mode

For `Z>0` contact repairs, the difference mesh is the mesh that must be
clipped away from the positive contact.

Rules:

```text
1. Detect affected corners or edges from exact positive top/bottom equality.
2. Build the same nudge keep footprint defined by
   shared_z0_edge_corner_nudge.md.
3. Replace the difference mesh top and bottom emitted footprint with that keep
   footprint.
4. Add midpoint vertices at the same XY locations as the Z=0 spec.
5. Assign inserted nudge midpoint Z from the surface that owns that side of
   the volume. Difference top midpoint Z comes from the upper-raster /
   difference-top surface. Difference bottom midpoint Z comes from the
   corrected lower-normal top surface actually emitted by the normal mesh.
   If a confirmed existing-grid repair record carries serialized
   `midpoint_z_by_name` values, those values may be used as local seam-closure
   overrides for the inserted vertices in that record. Do not promote those
   values into a global role-neutral midpoint map.
6. Rebuild exterior walls from the final nudged difference footprint.
7. Do not add base-plane fill for the removed positive-Z contact area.
```

In short:

```text
positive-Z difference-after == Z=0 normal-after footprint behavior,
but with positive interpolated Z values.
```

## Normal Mesh Mode

For `Z>0` contact repairs, the lower-normal mesh must keep full footprint
coverage so the lower raster remains the interlocking source of truth.

Rules:

```text
1. Use the same normal keep footprint from shared_z0_edge_corner_nudge.md.
2. Add the same complementary patch or patches from the Z=0 difference spec.
3. The union of keep + complementary patches covers the original footprint.
4. Internal seams between keep and complementary patches are surface seams, not
   exterior walls.
5. Midpoint vertices use the same XY locations as the Z=0 spec.
6. Inserted normal top midpoint Z uses the same local repaired interface Z as
   the difference bottom when the positive-Z plan carries a
   `midpoint_z_by_name` value for that midpoint. If no local override exists,
   interpolate from the corrected lower-normal top surface. Normal bottom/base
   midpoint vertices remain on the normal-mode base surface.
7. The normal mesh bottom/base remains its ordinary normal-mode base surface.
```

In short:

```text
positive-Z normal-after == Z=0 difference-after footprint behavior,
but the complementary patch is positive lower-normal coverage, not Z=0 fill.
```

## Clipped Cells

Clipped cells use the same role swap.

The emitted clipped cell footprint is the hard source mask for positive-Z
nudge edits. If a cell has clipped surface polygons, use their 2D union as the
cell footprint. Otherwise use the full raster-cell footprint. Every keep,
complement, and removal patch must be intersected with that emitted footprint.
Do not synthesize geometry outside the clipped/preclipped raster footprint.

For the positive-Z difference mesh:

```text
final_difference_footprint =
    existing_clipped_footprint intersected with normal_nudge_keep_footprint
```

For the positive-Z normal mesh:

```text
normal_keep_piece =
    existing_clipped_footprint intersected with normal_nudge_keep_footprint

normal_complement_piece_or_pieces =
    existing_clipped_footprint minus normal_keep_piece
```

If polygon operations produce multiple polygons, triangulate and emit each
polygon independently. Split shared keep/complement boundaries so both sides
use matching vertices. Do not generate exterior walls on internal seams.

For split-only positive-Z difference records, zero-height cleanup may preserve
matching top/bottom surface patches when those patches contain the endpoint of
a requested split side or one of that side's split half-edges. These preserved
vertices and edges keep the difference bottom aligned with the corrected normal
top at the pair interface. This exception is only for split-only records;
positive-Z corner-removal records still remove their clipped-away footprint
and must not retain removed contact corners.
When an existing split-only difference record carries `midpoint_z_by_name`,
apply that seam override to the difference top inserted midpoint. The
difference bottom midpoint should continue to come from the cell's current
bottom surface so the split-only contact does not collapse into a duplicate
zero-height top/bottom patch.

If an emitted clipped difference cell has a confirmed serialized positive-Z
overused edge on a cardinal cell side, treat that side as a local
difference-removal contact even when the clipped edge segment does not include
both original grid corners. The difference mesh uses the existing two-corner
side-removal footprint for that side, intersected with the clipped footprint.
Do not broaden the shared normal-side `corners` record for this clipped-side
inference; keep it as a difference-only local removal unless the normal cell
has its own confirmed positive-Z repair. This remains a local per-cell repair:
the confirmation comes from the current cell's emitted top/bottom contact edge,
and no cross-cell cache or tolerance-based clipped-boundary match is
introduced.

## Z Assignment

Unlike the `Z=0` fix, inserted midpoint and intersection vertices are not
forced to `0`.

For positive-Z nudging, inserted nudge midpoint vertices use the same
surface-specific source as other emitted vertices:

```text
difference inserted midpoint top vertices:
    interpolate from the upper raster / difference top surface

difference inserted midpoint bottom vertices:
    interpolate from the corrected lower-normal top surface
    or use the confirmed local seam override for an existing-grid repair

normal inserted midpoint top vertices:
    use the same local repaired interface Z as the difference bottom when
    the positive-Z plan carries a `midpoint_z_by_name` value; otherwise
    interpolate from the corrected lower-normal top surface

normal inserted midpoint bottom/base vertices:
    use the normal-mode base surface
```

Other emitted vertices still use their surface-specific source:

```text
difference top vertices:      interpolate from the upper raster surface
difference bottom vertices:   interpolate from the corrected lower-normal top
                              surface
normal top vertices:          use local `midpoint_z_by_name` interface
                              overrides for inserted nudge/split midpoints;
                              otherwise interpolate from the corrected
                              lower-normal top surface
normal bottom vertices:       use the normal-mode base surface
```

Here, the "lower raster surface" and "lower-normal top surface" refer to the
same DEM data, but not the same topology source. The difference mesh must follow
the corrected lower-normal top surface that the normal mesh actually emits. It
should not independently reconstruct a different lower surface from the raster.
The difference top may be higher than the difference bottom at inserted
positive-Z midpoint vertices. For emitted volume, difference top Z must be
greater than or equal to difference bottom Z at matching XY. Existing-grid
positive-Z pair repair may instead use a confirmed local `midpoint_z_by_name`
value on both difference surfaces and on the matching inserted normal-top seam
midpoint when adjacent repaired cells already share that serialized seam. This
is a topology closure constraint for that cell record, not a source of
independent bottom geometry and not shared state for unrelated cells.

Only vertices whose source surface is exactly `0` should have `Z=0`.

## Covered Cases

Use the footprint definitions from `shared_z0_edge_corner_nudge.md` for:

```text
- one affected corner;
- two adjacent affected corners;
- two opposite affected corners;
- three affected corners;
- clipped-cell intersections of those cases.
```

The positive-Z nudge cases are:

```text
- one-corner exact positive contacts that are endpoints of confirmed
  positive-Z overused edges;
- two-adjacent shared positive edge contacts;
- two-opposite positive diagonal contacts;
- three-corner positive contacts that create one overused positive edge.
```

When a one-corner positive contact is confirmed through a positive overused
edge endpoint, it uses the same geometry as the other nudge cases. For example,
if `SE` is the confirmed affected positive corner, the positive-Z difference
mesh removes `SE` from that cell footprint and keeps:

```text
SW -> Smid -> Emid -> NE -> NW -> SW
```

The matching positive-Z normal mesh keeps full footprint coverage by emitting
the same keep footprint plus the complementary `SE -> Emid -> Smid -> SE`
positive lower-normal patch. If the repair record carries local midpoint
interface overrides, `Emid` and `Smid` on that normal top patch use those
override Z values so they match the repaired difference bottom.

## Non-Goals

This spec does not introduce tolerance-based matching. It does not change the
Z=0 base-plane behavior. It does not define a global post-triangle flip repair;
the fix should be expressed in the same local nudge footprint language used by
`shared_z0_edge_corner_nudge.md` so the normal and difference meshes remain
predictably interlocking.
