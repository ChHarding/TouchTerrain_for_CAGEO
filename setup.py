from setuptools import find_namespace_packages, setup

setup(
    name='touchterrain',
    version='3.3',
    description='Framework for converting raster based Digital Elevation Models (online or local) into 3D printable terrain models (STL)',
	url='https://github.com/ChHarding/TouchTerrain_for_CAGEO',
	license='GPL',
	classifiers=[
		'Programming Language :: Python :: 3',
	],	
	keywords='elevation terrain 3D-printing geotiff STL',
	python_requires='>=3.6, <4',
	
    packages=find_namespace_packages(include=["touchterrain.*"]), # should only be server and common
    include_package_data=True,
    install_requires=[
        'Pillow>=6.0.0',
        'google-api-python-client=1.12.8', # util fix in 2.x use 1.12.8
        'earthengine-api>=0.1.256', # 0.1.256 fixes google-api-python-client 2.x bug by forcing it back to 1.12.8
        'Flask>=1.0.2',
        #'vectors==99.0.0',  # is now part of common folder
        'oauth2client>=4.1.3',
        'numpy>=1.17',
        'kml2geojson>=4.0.2', # for reading polygon coords from kml
        'geojson>=2.5', # for wrapping polygon data
        'defusedxml>=0.6', # safe minidom for parsing kml
        'six>=1.15.0', # earthengine apparently uses an old version of six ...

    ],
    
    # Deactivated for now b/c there's no standalone submodule, TouchTerrain_standalone.py is at root
    #entry_points={
    #    "console_scripts": [
    #        "touchterrain = touchterrain.standalone.TouchTerrain_standalone:main",
    #    ],
    #},
    
    extras_require={
        'server': [
            'gunicorn>=20.0.4',
        ],
    },
)
