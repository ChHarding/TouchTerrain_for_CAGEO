# TouchTerrain Dev Validation Environment

Use the `touchterrain-dev` conda environment for project validation. The
standalone `python` on this machine may not have project dependencies such as
`numpy` or `pytest`.

If `conda` is not on `PATH`, use the installed conda executable directly:

```powershell
& "$env:USERPROFILE\anaconda3\Scripts\conda.exe" run -n touchterrain-dev python -m pytest test/test_validate_launch_mesh_comparison.py
```

For topology validation, use:

```powershell
& "$env:USERPROFILE\anaconda3\Scripts\conda.exe" run -n touchterrain-dev python tools\validate_launch_topology.py --mode nudge --mesh-workers 0 --mesh-timeout-seconds 900
```

Run `conda run` commands sequentially. Parallel `conda run` calls can collide
on Conda temporary activation files on Windows.

Prefer `conda run -n touchterrain-dev` over calling the environment
`python.exe` directly for dependency-backed checks. Direct env Python may not
set up the same DLL/search-path environment that Conda activation provides.
