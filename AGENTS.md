# Touch Terrain overview for agents

The "normal" mesh is the single mesh that is typically output by TouchTerrain. In interlocking-pair mode, it is the lower piece generated from the lower raster. The "difference" mesh is a secondary mesh that is output when TouchTerrainConfig.interlocking_mesh_pair is enabled. All output mesh from TouchTerrain is cell based. Every edge and face is constrained to a cuboid cell region.

In this document, "top surface" and "bottom surface" mean the upper and lower Z surfaces of an emitted mesh, not map north/south. Each surface is a triangulated XY footprint with Z assigned at its vertices. Walls close the volume between the two surfaces.

Normal mesh surfaces:
- The top surface is the raster-derived terrain surface actually emitted for the normal mesh after clipping, interpolation, and nudge/topology repairs. In interlocking-pair mode, this emitted top surface is the source of truth for the difference mesh bottom.
- The bottom surface is the normal-mode base surface, usually a flat Z=0 plane over the emitted XY footprint. This surface may be omitted by no_bottom or changed by bottom_image/bottom_elevation in non-pair modes. Z=0 nudge repairs can remove zero-height footprint from the normal mesh and record that removed area as explicit Z=0 fill for the paired difference mesh.

Difference mesh surfaces:
- The top surface is generated from the upper raster over the emitted upper footprint after clipping and repairs. For Z=0 nudge repairs this footprint stays full; for positive-Z overused-edge repairs areas can be clipped away according to `positive_z_overused_edge_nudge.md`.
- The bottom surface follows the corrected top surface actually emitted by the lower/normal mesh wherever that lower mesh owns the XY coverage. Remaining upper footprint is closed with Z=0 fill only when that fill is explicit, such as footprint removed by a Z=0 normal nudge or a missing lower-normal cell. Missing lower-normal coverage alone should not imply Z=0 fill. Therefore the difference bottom is lower-normal emitted topology plus any required Z=0 fill, not an independently triangulated copy of the lower raster.
- For emitted volume, top Z should be greater than or equal to bottom Z at the same XY.

A cell has a value that represents a pixel in a raster. A cell region has 4 corners in X/Y plane. A corner's Z value is interpolated using that cell's value and the 3 neighboring cell's values.

Order of raster processing

Raster calculations
Raster clipping
Cell creation

Cell creation logic order:
- Nudge vertices and edges towards the interior of the mesh to prevent emitting overused edges
  - Controlled by TouchTerrainConfig.nudge_in_overused_edges_vertex
  - Follow the specification in `shared_z0_edge_corner_nudge.md` and `positive_z_overused_edge_nudge.md`.
- Triangulate cell polygon surface. This should be the same in X/Y plane for top and bottom surfaces. The top and bottom polygon vertices' Z for cells with clipped borders are interpolated.
- Rotate the splitting edge of an unclipped cell based on the slope of the created edge.
  - Controlled by TouchTerrainConfig.split_rotation
  - See `user_config.py` for goals of rotating the splitting edge of a triangulated quad.
- Create vertical walls from the top polygon to the bottom polygon.
  - Each top polygon vertex should have an equivalent vertex on the bottom polygon that is less than or equal in Z. There should be an edge between these 2 vertices and form a face with the next top/bottom polygon vertex pair and connecting edge. The edges for this face should be like the below list. This quad is able to be triangulated.
    1. top1 to bottom1
    2. bottom1 to bottom2
    3. bottom2 to top2
    4. top2 to top1
  - If the top/bottom vertex pair have the same Z, there is no edge between them and no wall is created for that pair unless the next or previous top/bottom vertex pair have an edge between them (which means the next or previous pair should be different Z values within the pair). In the case where a wall is created for the top/bottom vertex pair with the same Z, the edges should be like the below list. This is a triangle already.
    1. top1/bottom1 to bottom2
    2. bottom2 to top2
    3. top2 to top1/bottom1
- Write out the cell structure to the 3d mesh as triangles.
  - Ignore/remove zero volume meshes

- Other processing steps for other userconfigs not mentioned should be left in place.

## Mesh module layout

Mesh code in `touchterrain/common` is layered. A module may import only from
layers below it. `grid_tesselate.py` does not postpone annotation evaluation,
so an import that points upward is an import error, not a warning.

| Layer | Module | Holds |
| --- | --- | --- |
| 1 | `mesh_vocabulary.py` | type aliases, cardinal and nudge corner tables, row-chunking helpers |
| 2 | `mesh_serialization.py`, `raster_interpolation.py` | serialized-coordinate identity; canonical corner elevation |
| 3 | `surface_geometry.py` | 2D footprint to 3D surface triangles, surface clipping, wall rebuilds |
| 4 | `nudge_geometry.py` | keep footprints and inserted midpoints, shared by both nudge modes |
| 5 | `nudge_cell_ops.py` | the four per-cell nudge repairs |
| 6 | `Cell.py` | `class cell`: one cell's surfaces and walls |
| 7 | `nudge_plan.py` | positive-Z candidates, then confirmation against emitted geometry |
| 8 | `nudge_apply.py` | driving nudge repair over a grid, and the cell-creation seam |
| 9 | `grid_tesselate.py` | `class grid`, cell creation, mesh writers |

Nudging sits above `Cell` because confirming a positive-Z contact builds a
throwaway cell and runs zero-height cleanup on it. The nudge operations are
therefore free functions taking the cell or grid as an argument; `cell` and
`grid` keep thin delegating methods so call sites and tests are unaffected.

`create_cells` calls nudging rather than inlining it. Keep it that way: the
generation path should stay readable without reading the nudge algorithm.

## Change guidance

- Reuse or adapt existing classes and functions if the changed logic is relevant.
- Specifications for more specific program behavior are in the markdown files in `spec` folder.
- Use existing imported libraries' features for convenience over recreating the same logic.
- Prefer minimal code changes has long as the code is self documenting and human readable.
  - Add concise comments for each major loop or step that is not immediately clear to a human what is being done.
- Modified python code must conform to PEP 8, PEP 257, PEP 484

## Development mesh output

- Output meshes into a temporary folder that is organized by folder named after the launch config or mesh name. The meshes should be uncompressed in the folder ready to manual inspection.
- Clean up temporary folders by removing old development output meshes older than 1 day if not needed for tests anymore.

## Mesh validation after code changes

- Follow `spec/mesh_validation.md` after code changes that affect emitted mesh topology, nudge behavior, clipping, bottom surfaces, or mesh serialization.
- Default validation command: `conda run -n touchterrain-dev python tools\validate_launch_topology.py --mode all --mesh-workers 0 --mesh-timeout-seconds 900`
- Use `--mode all` rather than `--mode nudge` for changes to shared mesh code. `--mode nudge` only runs the 22 configs whose name ends in `-nudge`, so it does not exercise the ordinary generation, clipping, and bottom-surface paths that the other configs cover.
- 15 of the 48 configs currently report topology errors, all of them with nudging off. That is the existing state, not a regression; compare against it rather than expecting zero failures.
- If only validation code changed, rerun validation with `--reuse-dir` pointed at a prior topology validation output folder instead of regenerating meshes.
- Do not treat mesh topology errors as expected unless the option combination is documented in `spec/mesh_validation.md`.

## Prompt output to the developer

- If referencing meshes, include a link to the mesh that is ready for manual inspection.
