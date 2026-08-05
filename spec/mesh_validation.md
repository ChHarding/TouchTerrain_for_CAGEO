# Mesh validation after code changes

Use this playbook when a code change can affect emitted STL/OBJ topology,
cell triangulation, clipping, bottom surfaces, nudge behavior, or mesh
serialization. New intentional mesh exceptions must be documented here before
agents treat them as expected.

## Environment

Run mesh validation through the project Conda environment:

```powershell
conda run -n touchterrain-dev python tools\validate_launch_topology.py --mode nudge --mesh-workers 0 --mesh-timeout-seconds 900
```

For validation-only changes, reuse existing generated meshes instead of
regenerating them:

```powershell
conda run -n touchterrain-dev python tools\validate_launch_topology.py --mode nudge --mesh-workers 0 --mesh-timeout-seconds 900 --reuse-dir tmp\launch_topology_nudge_<run_id>
```

`--mesh-workers 0` lets the validator parallelize topology checks within each
STL mesh. The caller may still run multiple validation scripts if independent
launch groups should run concurrently.

`--reuse-dir` points at a prior topology validation output directory containing
`*-topology-validation.zip` files. Use it after changes to validator logic,
timeout handling, reporting, or comparison code. Do not use it as the only
check after generation, clipping, nudge, raster, bottom-surface, or
serialization changes; those changes need regenerated meshes.

`--mesh-timeout-seconds` is applied to each emitted STL mesh validation, not to
the whole launch matrix. Prefer this per-mesh timeout over wrapping the entire
command in one timeout because launch configs and emitted meshes vary
substantially in size. A timeout records that mesh as failed in the validation
report and allows remaining meshes/configs to continue. Mesh generation happens
before STL topology validation, so a generation hang still needs a targeted
config run or an outer command timeout.

The topology validator prints config, mesh, triangle-count, percent-complete,
and elapsed-time progress to stderr while each STL mesh is being validated.

## Validator selection

- `tools\validate_launch_topology.py` is the primary post-change topology
  validator. Use it after mesh-generation, clipping, pair-mode, bottom-surface,
  or nudge changes.
- `tools\validate_launch_mesh_comparison.py` is for cases where output should
  remain byte-identical to the historical baseline or when checking expected
  baseline differences.
- `tools\validate_positive_z_nudge.py` is for positive-Z nudge and
  split-rotation changes.

For targeted work, validate the affected launch configs directly:

```powershell
conda run -n touchterrain-dev python tools\validate_launch_topology.py --configs PA-pair-nudge.json --mesh-workers 0 --mesh-timeout-seconds 900
```

For topology or nudge changes, run the full nudge matrix:

```powershell
conda run -n touchterrain-dev python tools\validate_launch_topology.py --mode nudge --mesh-workers 0 --mesh-timeout-seconds 900
```

For validation-only changes, run the same selector against a prior output
directory with `--reuse-dir` so the report is rebuilt from the existing ZIPs.

## Error interpretation

- `boundary_edges` are triangle edges used by only one face. They are failures
  for closed meshes.
- `overused_edges` are edges used by more than two faces. They are failures
  unless a baseline-comparison test explicitly documents the case.
- `bad_oriented_edges` are manifold edges whose two uses have mismatched
  orientation. They are always failures for emitted STL meshes.
- Missing STL entries and zero-triangle STL meshes are failures. They can hide
  generation or clipping problems because their edge counts are all zero.
- `first_overused_edges`, `first_bad_oriented_edges`, and other `first_*`
  fields are diagnostics only. They help locate a failure but are not acceptance
  criteria.

## Expected error matrix

| Option or output mode | Expected validation result |
| --- | --- |
| Normal closed STL/OBJ output | `boundary_edges=0`, `overused_edges=0`, and `bad_oriented_edges=0`. |
| `interlocking_mesh_pair=True` | Both normal and difference meshes must be closed and clean. |
| `nudge_in_overused_edges_vertex=True` | Z=0 and positive-Z overused edge contacts should be fixed, not accepted. |
| `no_bottom=True` | `boundary_edges` are expected because the mesh is intentionally open. `overused_edges` and `bad_oriented_edges` are still not expected. |
| `fileformat=GeoTiff` | Mesh topology validation is not applicable because no STL/OBJ mesh is emitted. |
| `edge_clipping_polygon`, `bottom_elevation`, `bottom_image`, `bottom_thru_base`, or multi-tile output | Meshes are still expected to be closed unless combined with `no_bottom=True`. |
| `dirty_triangles=True` | Does not make boundary, overused, or bad-oriented edges acceptable. It only affects degenerate triangle tolerance where applicable. |

## Reporting results

When reporting validation back to the developer, include links to:

- `validation_report.json`
- the extracted mesh folder
- any failed STL mesh that is ready for manual inspection

If a validation failure is considered expected, cite the row in the expected
error matrix or add a new documented exception before accepting it.
