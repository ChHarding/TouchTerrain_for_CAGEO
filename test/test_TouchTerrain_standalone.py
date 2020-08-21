import unittest
'''test standalone mode '''
# Note that the cwd when running the test will be project root, NOT the test folder in it!


''' FOR LATER
# if we want to work on a local raster, get the full pathname to it
if args["importedDEM"] != None: 
    from os.path import abspath
    args["importedDEM"]= abspath(args["importedDEM"]) 
    print("reading in local DEM:", args["importedDEM"])
'''

def run_get_zipped_tiles(args):
    '''utility to actually run get_zipped_tiles()'''
    
    import ee
    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain
    ee.Initialize()

    print("\nUsing these config values:")
    for k in sorted(args.keys()):
        print("%s = %s" % (k, str(args[k])))

    totalsize, full_zip_file_name = TouchTerrain.get_zipped_tiles(**args) 
    print("In tmp, created zip file", full_zip_file_name,  "%.2f" % totalsize, "Mb")

    from os import getcwd, sep
    folder = getcwd() + sep + "test" + sep + args["zip_file_name"] # unzip into his folder inside test

    import zipfile
    zip_ref = zipfile.ZipFile(full_zip_file_name, 'r')
    zip_ref.extractall(folder)
    zip_ref.close()
    print("unzipped STL file into", folder)

class TestStringMethods(unittest.TestCase):



    def test_get_zipped_tiles_gpx(self):
        '''Test using gpx files in stuff gpx-test '''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/NED",   # DEM source
                # area for gpx test
                "bllat": 39.32205105794382,   # bottom left corner lat
                "bllon": -120.37497608519418, # bottom left corner long
                "trlat": 39.45763749030933,   # top right corner lat
                "trlon": -120.2002248034559, # top right corner long
                "tilewidth": 120,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_get_zipped_tiles_gpx",   # base name of zipfile, .zip will be added
                "importedGPX": # Plot GPX paths from these files onto the model.
                            ["stuff/gpx-test/DLRTnML.gpx",
                            "stuff/gpx-test/DonnerToFrog.gpx",
                            "stuff/gpx-test/CinTwistToFrog.gpx",
                            "stuff/gpx-test/sagehen.gpx",
                            "stuff/gpx-test/dd-to-prosser.gpx",
                            "stuff/gpx-test/alder-creek-to-crabtree-canyon.gpx",
                            "stuff/gpx-test/ugly-pop-without-solvang.gpx",
                            "stuff/gpx-test/tomstrail.gpx"   
                            ],
                "gpxPathHeight": 100,  # Currently we plot the GPX path by simply adjusting the raster elevation at the specified lat/lon,
                                    # therefore this is in meters. Negative numbers are ok and put a dent in the mdoel  
                "gpxPixelsBetweenPoints" : 20, # GPX Files haves a lot of points. A higher number will create more space between lines drawn
                                                # on the model and can have the effect of making the paths look a bit cleaner 
                "gpxPathThickness" : 5, # Stack parallel lines on either side of primary line to create thickness. 
                                        # A setting of 1 probably looks the best 
        }
        run_get_zipped_tiles(args)
        

    def test_get_zipped_tiles_basic_EE(self):
        '''Basic test to get Sheep Mountain via EE'''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/NED",   # DEM source
                "bllat": 44.50185267072875,   # bottom left corner lat
                "bllon": -108.25427910156247, # bottom left corner long
                "trlat": 44.69741706507476,   # top right corner lat
                "trlon": -107.97962089843747, # top right corner long
                "tilewidth": 80,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_get_zipped_tiles_basic_EE",   # base name of zipfile, .zip will be added
        }
        run_get_zipped_tiles(args)

    '''
    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

    def test_isupper(self):
        self.assertTrue('FOO'.isupper())
        self.assertFalse('Foo'.isupper())

    def test_split(self):
        s = 'hello world'
        self.assertEqual(s.split(), ['hello', 'world'])
        # check that s.split fails when the separator is not a string
        with self.assertRaises(TypeError):
            s.split(2)
    '''

if __name__ == '__main__':
    unittest.main(verbosity=2)