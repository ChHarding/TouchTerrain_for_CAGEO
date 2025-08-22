#sitepackages in C:\Users\XXX\.conda\envs\touchterrain-dev\Lib

git clone XXX
cd ./TOUCHTERRAIN_FOR_CAGEO
# With a new virtual environment called touchterrain-dev
conda activate touchterrain-dev
# Update conda env with touch terrain requirements from environment.yml
conda env update --name touchterrain-dev --file environment.yml --prune
# Install touchterrain as a module in "editable" state so it links back to the local development code folder
pip install -e .