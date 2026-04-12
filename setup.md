# Setup a workspace to run Touch Terrain

## Code and Environment creation

1. Get the Touch Terrain code

        ```sh
        git clone XXX
        cd ./TOUCHTERRAIN_FOR_CAGEO
        ```

1. Create or switch to the Python environment

  - Create a Python environment `touchterrain` and install deps for the current folder.

OR

  - Create the blank Python environment

        ```sh
        # create new conda env called `touchterrain-dev`
        conda create --name touchterrain-dev
        # activate the virtual environment called touchterrain-dev
        conda activate touchterrain-dev
        ```

## Update Environment with Dependencies

The environment dependencies can be installed through conda or pip.

`.` is the python package configured with `pyproject.toml` in current folder. The current folder should be the root of the Touch Terrain code folder.

- Touch Terrain dependencies are specified in `pyproject.toml`

- If you want to run Touch Terrain as server or in a juypter notebook, add `server` or `notebook` to the pip dependency path like `.` -> `.[notebook]`.

### Conda-based

Update conda env with Touch Terrain deps from an `environment.yml` variant. `conda` will install `pip` and automatically use `pip` to install `touchterrain` package and its dependencies.

Dependency structure

- `conda env ---dependency--> gdal`
- `conda env ---dependency--> pip ---dependency--> . [touchterrain] ---dependency--> other pkgs`

#### Touch Terrain (normal)

Install touchterrain as a normal package in pip. Use this if you do not plan to make changes to the Touch Terrain code.

```sh
conda env update --file environment.yml --name touchterrain-dev --prune 
```

`touchterrain` package (aka the code) will be likely be installed (aka copied) to conda env sitepackages in `C:\Users\XXX\.conda\envs\ENV_NAME\Lib`

#### Touch Terrain (development)

Install touchterrain as an **editable** package in pip. The package is linked to the current directory. Changes in source code are reflected in the "installed" package without needing to reinstall.

```sh
conda env update --file environment-dev.yml --name touchterain-dev --prune 
```

#### Install `gdal` via conda from conda-forge source

```sh
conda install -c conda-forge gdal
```

> `--prune` will remove ALL packages not specified in the current target yml file and removed packages include gdal if gdal was previously installed via conda. If you want to update environment from the yml file, you can either drop `--prune` to not remove conda gdal or reinstall gdal afterwards each time.

### pip-based

You can also install Touch Terrain and its deps directly via `pip` without calling `pip` through `conda`.

Dependency structure

- `conda env ---dependency--> gdal`
- `pip ---dependency--> . [touchterrain] ---dependency--> other pkgs`

#### Install `gdal` via conda from conda-forge source

```sh
conda install -c conda-forge gdal
```

#### Normal

```sh
pip install .
```

#### Development

Install touchterrain as a module in "editable" state so it links back to the local development code folder

```sh
pip install -e .
```

## Environment Verification

Conda shows packages from both conda and pip and where they are from (pypi (pip) or conda-forge (conda))

```sh
conda list
```

```sh
pip list -v
```

should list a line for touchterrain if installed as `editable` like

```
touchterrain 3.7.0 C:\Users\XXX\development\TouchTerrain_for_CAGEO
```


## Environment Deletion

```sh
conda env list
conda deactivate touchterrain-dev
conda env remove --name touchterrain-dev
```

```sh
conda env list
conda deactivate tt
conda env remove --name tt
conda create --name tt
conda activate tt
conda env update --file environment.yml --name tt --prune 
```
