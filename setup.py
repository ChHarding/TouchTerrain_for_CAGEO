from setuptools import find_namespace_packages, setup
 
setup(
    name='touchterrain',
    version='3.5.1',
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
        'google-api-python-client>=2.6', 
        'earthengine-api>=0.1.232', # 1.232 is required after Aug 19, 2020
        #'vectors==99.0.0',  # is now part of common folder
        'oauth2client>=4.1.3',
        'numpy>=1.17',
        'scipy>=1.2', # Only needed for hole filling functionality
        'kml2geojson>=4.0.2', # for reading polygon coords from kml
        'geojson>=2.5', # for wrapping polygon data
        'defusedxml>=0.6', # safe minidom for parsing kml
        'six>=1.15.0', # earthengine apparently uses an old version of six ...
    ],

    extras_require={
        'server': [  # Not sure which of the above could also be server-only
            'gunicorn>=20.0.4',
            'Flask>=1.0.2',
        ],
    },
)