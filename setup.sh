#sitepackages in C:\Users\XXX\.conda\envs\touchterrain-dev\Lib

git clone XXX
cd ./TOUCHTERRAIN_FOR_CAGEO
# create new env
conda create --name touchterrain-dev
# With a new virtual environment called touchterrain-dev
conda activate touchterrain-dev

## Option A:

# Update conda env with touch terrain requirements from environment.yml
conda env update --name touchterrain-dev --file environment.yml --prune #old env
conda env update --name touchterrain-dev --file environment-base.yml --prune # Install touchterrain as a normal package in pip (conda > dep > pip > dep > . [current touchterrain directory]).
conda env update --name touchterrain-dev --file environment-dev.yml --prune # Install touchterrain as an editable package linked to the current touchterrain code development directory so local changes are used in the package.

# Then install gdal via conda from conda-forge.
conda install -c conda-forge gdal

# --prune will remove ALL packages not specified in the current target yml file and removed packages include gdal if gdal was installed via conda. If you want to update environment from the yml file, you can either drop --prune to not remove conda gdal or reinstall gdal afterwards each time.

## Option B:

#
conda install -c conda-forge gdal

# Install touchterrain as a module in "editable" state so it links back to the local development code folder
pip install -e .

# Conda shows packages from both conda and pip and where they are from (pypi (pip) or conda-forge (conda))
conda list

# Verification
pip list -v
# should list a line for touchterrain like
# touchterrain 3.7.0 C:\Users\XXX\development\TouchTerrain_for_CAGEO


#delete env
conda env list
conda deactivate touchterrain-dev
conda env remove --name touchterrain-dev