from setuptools import find_namespace_packages, setup
 
setup(
    name='touchterrain',
    version='3.7.0', # Feb. 17, 2025
    description='Framework for converting raster based Digital Elevation Models (online or local) into 3D printable terrain models (STL)',
	url='https://github.com/ChHarding/TouchTerrain_for_CAGEO',
	license='GPLv3',
	classifiers=[
		'Programming Language :: Python :: 3',
	],	
	keywords='elevation terrain 3D-printing geotiff STL',
	python_requires='>=3.11, <4',
	author="Chris Harding",
    author_email="charding@iastate.edu",
    packages=find_namespace_packages(include=["touchterrain.*"]), # should only be server and common
    include_package_data=True,
    install_requires=[
        'defusedxml>=0.6', # safe minidom for parsing kml
        'earthengine-api>=0.1.232',  
        'geojson>=2.5', # for wrapping polygon data
        'google-api-python-client>=2.6', 
        "httplib2>=0.22.0",
        "imageio>=2.36.0",
        "k3d>=2.16.1",
        'kml2geojson>=4.0.2', # for reading polygon coords from kml
        "matplotlib>=3.9.2",
        'numpy>=1.17',
        'oauth2client>=4.1.3',
        'Pillow>=6.0.0',
        'scipy>=1.2', # Only needed for hole filling functionality
        'six>=1.15.0', # earthengine apparently uses an old version of six ...
        #'GDAL>3.4.3', # Installation via pip requires a C++ compiler: https://visualstudio.microsoft.com/visual-cpp-build-tools
        # with conda: conda install -c conda-forge gdal
        # Prebuilds (.whl) : https://www.lfd.uci.edu/~gohlke/pythonlibs/#gdal but stopped with 3.4.3
        # Still active: https://www.nuget.org/packages?q=GDAL but uses a .Net package manager
    ],

    extras_require={
        'server': [  # Not sure which of the above could also be server-only
            'Flask>=2.0.0',
            'gunicorn>=20.0.4',
        ],
    },
)
