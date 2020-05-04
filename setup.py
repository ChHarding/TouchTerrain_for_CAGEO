from setuptools import find_namespace_packages, setup

setup(
    name='touchterrain',
    #packages=find_packages(),
    packages=find_namespace_packages(include=["touchterrain.*"]), # should only be server and common
    include_package_data=True,
    install_requires=[
        #'Jinja2>=2.10.1',  # not needed, part of Flask
        'Pillow>=6.0.0',
        'earthengine-api>=0.1.216', # had some big changes at 0.1.216
        'Flask>=1.0.2',
        #'vectors==99.0.0',  # is now part of common folder
        'oauth2client>=4.1.3',
        'numpy>=1.17',
    ],
    entry_points={
        "console_scripts": [
            "touchterrain = touchterrain.standalone.TouchTerrain_standalone:main",
        ],
    },
    extras_require={
        'server': [
            'gunicorn>=19.9.0',
        ],
    },
)
