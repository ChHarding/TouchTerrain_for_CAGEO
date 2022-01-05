import unittest 
'''Test standalone mode 
This is a (non-complete) battery of test methods for the many different combinations that can be fed to 
TouchTerrain.get_zipped_tiles(). Each test's arguments are set in a dict (args) which are then
given as overwrite args to run_get_zipped_tiles().
I'm currently testing 12 different args, obviously NOT in all possible combinations! 
For better readability and to keep track which combos are covered, these are listed in TouchTerrain_test_matrix.csv 
inside this test folder.

As I'm pretty new to unit testing, I've just added a new test method for each new test. If you want to add your
own test it copy one of my methods, rename stuff ans set your own args. By defaults my test methods are decorated
with @unittest.skip('Skipped test') which will skip that test. To actually run a test, just comment out that decorator.

Note that the cwd when running the test will be project root, NOT the test folder in it!

EE means a test will use a only (Google Earth Engine) DEM,  local tests use a local geotiff (in test folder).
The test folder also contains a kml polygon file to test masking for EE and a 8-bit png for bottom image (relief) testing.
'''
# 




# Central function to run args
def run_get_zipped_tiles(overwrite_args, testname):
    '''utility to actually run a test with its (overwrite) args, which will override the official
    default (initial) args.'''


    # Use this to force import of local modules, required for debuging those imports
    import sys
    oldsp = sys.path
    sys.path = ["."] + sys.path
    from touchterrain.common import TouchTerrainEarthEngine as TouchTerrain
    sys.path = oldsp

    import ee
    ee.Initialize()

    # update default args with overwrite args
    args = {**TouchTerrain.initial_args, **overwrite_args}

    print(testname, "\nUsing these config values:")
    for k in sorted(args.keys()):
        print("%s = %s" % (k, str(args[k])))

    totalsize, full_zip_file_name = TouchTerrain.get_zipped_tiles(**args) 
    #print("In tmp, created zip file", full_zip_file_name,  "%.2f" % totalsize, "Mb")

    from os import getcwd, sep, remove
    folder = getcwd() + sep + "test" + sep + args["zip_file_name"] # unzip into his folder inside test

    import zipfile
    zip_ref = zipfile.ZipFile(full_zip_file_name, 'r')
    zip_ref.extractall(folder)
    zip_ref.close()
    print("unzipped files into", folder)
    remove(full_zip_file_name)

#    
# Actual tests start here !
#
class MyTests(unittest.TestCase):

    @unittest.skip("test_basic_EE")
    def test_basic_EE(self):
        '''Basic test to get Sheep Mountain via EE'''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/3DEP/10m",   # DEM source
                "bllat": 44.50185267072875,   # bottom left corner lat
                "bllon": -108.25427910156247, # bottom left corner long
                "trlat": 44.69741706507476,   # top right corner lat
                "trlon": -107.97962089843747, # top right corner long
                "tilewidth": 100,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_basic_EE_single_tile",   # base name of zipfile, .zip will be added
        }
        run_get_zipped_tiles(args, "test EE single tile")

    @unittest.skip("skipping test_basic_EE_OBJ")
    def test_basic_EE_OBJ(self):
        '''single tile EE but saves as OBJ file
        This will NOT have the simple (2 triangle) bottom that STL files would have'''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/3DEP/10m",   # DEM source
                "bllat": 44.50185267072875,   # bottom left corner lat
                "bllon": -108.25427910156247, # bottom left corner long
                "trlat": 44.69741706507476,   # top right corner lat
                "trlon": -107.97962089843747, # top right corner long
                "tilewidth": 100,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "obj",  # format of 3D model file
                "zip_file_name": "test_basic_EE_OBJ",   # base name of zipfile, .zip will be added
        }
        run_get_zipped_tiles(args, "test EE OBJ")

    @unittest.skip("skipping test_basic_EE_STLa")
    def test_basic_EE_STLa(self):
        '''single tile EE but saves as STLa (ascii STL) file'''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/3DEP/10m",   # DEM source
                "bllat": 44.50185267072875,   # bottom left corner lat
                "bllon": -108.25427910156247, # bottom left corner long
                "trlat": 44.69741706507476,   # top right corner lat
                "trlon": -107.97962089843747, # top right corner long
                "tilewidth": 100,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLa",  # format of 3D model file
                "zip_file_name": "test_basic_EE_STLa",   # base name of zipfile, .zip will be added
        }
        run_get_zipped_tiles(args, "test EE STLa")

    @unittest.skip("skipping test_EE_multi_tiles")
    def test_EE_multi_tiles(self):
        '''EE multiple tiles '''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/3DEP/10m",   # DEM source
                "bllat": 44.50185267072875,   # bottom left corner lat
                "bllon": -108.25427910156247, # bottom left corner long
                "trlat": 44.69741706507476,   # top right corner lat
                "trlon": -107.97962089843747, # top right corner long
                "tilewidth": 100,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 2, # number of tiles in x  
                "ntilesy": 2, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_EE_multi_tiles",   # base name of zipfile, .zip will be added
        }
        run_get_zipped_tiles(args, "test EE multi tiles")

    @unittest.skip("skipping test_EE_no_bottom")
    def test_EE_no_bottom(self):
        '''EE single tile no bottom'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_no_bottom",   # base name of zipfile, .zip will be added
                    "no_bottom": True,  # do not create bottom triangles
                    "no_normals": True,  # I think normals are off by default?
        }
        run_get_zipped_tiles(args, "EE single tile no bottom")

    @unittest.skip("skipping test_EE_with_normals")
    def test_EE_with_normals(self):
        '''EE single tile with normals'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_with_normals",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": False,  # Force to calculate normals for all triangles 
        }
        run_get_zipped_tiles(args, "EE single tile with normals")
    
    @unittest.skip("skipping test_EE_with_kml_with_smoothing")
    def test_EE_with_kml_with_smoothing(self):
        '''EE single tile with local kml, with smoothing'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_with_kml_with_smoothing",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles
                    "poly_file": "test/sheepMtn_outline.kml",
                    "smooth_borders":True, 
        }
        run_get_zipped_tiles(args, "EE single tile with local kml, with smoothing")
    
    @unittest.skip("skipping test_EE_with_kml_no_smoothing")
    def test_EE_with_kml_no_smoothing(self):
        '''EE single tile with local kml, no smoothing'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_with_kml_no_smoothing",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles
                    "poly_file": "test/sheepMtn_outline.kml",
                    "smooth_borders":False, 
        }
        run_get_zipped_tiles(args, "EE single tile with local kml, no smoothing")

    @unittest.skip("skipping test_EE_with_kml_no_bottom")
    def test_EE_with_kml_no_bottom(self):
        '''EE single tile with local kml, with smoothing'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_with_kml_no_bottom",   # base name of zipfile, .zip will be added
                    "no_bottom": True,
                    "no_normals": True,  # Force to calculate normals for all triangles
                    "poly_file": "test/sheepMtn_outline.kml",
                    "smooth_borders":True, 
        }
        run_get_zipped_tiles(args, "EE single tile with local kml, no_bottom")
    
    @unittest.skip("skipping test_EE_with_kml_multi_tile")
    def test_EE_with_kml_multi_tiles(self):
        '''EE single tile with local kml, with smoothing'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 2, # number of tiles in x  
                    "ntilesy": 2, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_with_kml_with_multi_tiles",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles
                    "poly_file": "test/sheepMtn_outline.kml",
                    "smooth_borders":True, 
        }
        run_get_zipped_tiles(args, "EE single tile with local kml multi tiles")

    @unittest.skip("skipping test_EE_bottom_image")
    def test_EE_bottom_image(self):
        '''EE single tile with bottom relief'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 2,   # thickness (in mm) of printed base (> 0.5 mm for bottom_image!)
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_bottom_image",   # base name of zipfile, .zip will be added
                    "no_bottom": False,  # do not create bottom triangles
                    "no_normals": True,  # no normals 
                    "bottom_image": "test/bottom_image_test.png"
        }
        run_get_zipped_tiles(args, "EE single tile with bottom relief image")
  
    @unittest.skip("skipping test_EE_bottom_image_masked")
    def test_EE_bottom_image_masked(self):
        '''EE single tile with bottom relief and a masked (NaN) top
        This should NOT work b/c it's not supported atm. It should simply ignore the bottom raster and use a constant instead'''

        args = {
                    "importedDEM": None,
                    "DEM_name": "USGS/3DEP/10m",   # DEM source
                    "bllat": 44.50185267072875,   # bottom left corner lat
                    "bllon": -108.25427910156247, # bottom left corner long
                    "trlat": 44.69741706507476,   # top right corner lat
                    "trlon": -107.97962089843747, # top right corner long
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.6,   # thickness (in mm) of printed base (> 0.5 mm for bottom_image!)
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_EE_bottom_image_masked",   # base name of zipfile, .zip will be added
                    "no_bottom": False,  # do not create bottom triangles
                    "no_normals": True,  # no normals 
                    "bottom_image": "test/bottom_image_test.png",
                    "poly_file": "test/sheepMtn_outline.kml"
        }
        run_get_zipped_tiles(args, "EE single tile with bottom relief, masked (should ignore bottom image!)")
    
    @unittest.skip('Skipped test_EE_gpx_path')
    def test_EE_gpx_path(self):
        '''Test using gpx files in stuff gpx-test '''
        args = {
                "importedDEM": None,
                "DEM_name": "USGS/3DEP/10m",   # DEM source
                # area for gpx test
                "bllat": 39.32205105794382,   # bottom left corner lat
                "bllon": -120.37497608519418, # bottom left corner long
                "trlat": 39.45763749030933,   # top right corner lat
                "trlon": -120.2002248034559, # top right corner long
                "tilewidth": 100,  # width of each tile in mm,  
                "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                "ntilesx": 1, # number of tiles in x  
                "ntilesy": 1, # number of tiles in y    
                "basethick": 0.5,   # thickness (in mm) of printed base
                "zscale": 1.5,  # elevation (vertical) scaling
                "fileformat": "STLb",  # format of 3D model file
                "zip_file_name": "test_EE_gpx_path",   # base name of zipfile, .zip will be added
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
                                    # therefore this is in meters. Negative numbers are ok and put a dent in the model  
                "gpxPixelsBetweenPoints" : 20, # GPX Files haves a lot of points. A higher number will create more space between lines drawn
                                                # on the model and can have the effect of making the paths look a bit cleaner 
                "gpxPathThickness" : 5, # Stack parallel lines on either side of primary line to create thickness. 
                                        # A setting of 1 probably looks the best 
        }
        run_get_zipped_tiles(args, "EE with GPX path, using gpx files in stuff gpx-test")
    
    @unittest.skip("skipping test_local_resampled")
    def test_local_resampled(self):
        '''single tile from local geotiff, resampled to 1 mm printres '''

        args = {
                    "importedDEM": "test/SheepMtn.tif",
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 1,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_local_resampled",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles

        }
        run_get_zipped_tiles(args, "single tile from local geotiff, resampled to 1 mm printres")

    @unittest.skip("skipping test_local_source_resolution")
    def test_local_source_resolution(self):
        '''single tile from local geotiff at source resolution  '''

        args = {
                    "importedDEM": "test/SheepMtn.tif",
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": -1,  # resolution (horizontal) of 3D printer in mm, -1 means source!
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_local_source_resolution",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles
        }
        run_get_zipped_tiles(args, "single tile from local geotiff at source resolution")

    @unittest.skip("skipping test_local_with_kml")
    def test_local_with_kml(self):
        '''tile from local geotiff with local kml''' 

        args = {
                    "importedDEM": "test/SheepMtn.tif",
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 0.5,   # thickness (in mm) of printed base
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_local_with_kml",   # base name of zipfile, .zip will be added
                    "no_bottom": False,
                    "no_normals": True,  # Force to calculate normals for all triangles
                    "poly_file": "test/sheepMtn_outline.kml",
                    "smooth_borders":True, 
        }
        run_get_zipped_tiles(args, "local geotiff, single tile, with local kml")
    
    @unittest.skip("skipping test_local_bottom_image")
    def test_local_bottom_image(self):
        '''local geotiff with bottom relief'''

        args = {
                    "importedDEM": "test/SheepMtn.tif",
                    "tilewidth": 100,  # width of each tile in mm,  
                    "printres": 0.4,  # resolution (horizontal) of 3D printer in mm
                    "ntilesx": 1, # number of tiles in x  
                    "ntilesy": 1, # number of tiles in y    
                    "basethick": 2,   # thickness (in mm) of printed base (> 0.5 mm for bottom_image!)
                    "zscale": 1.5,  # elevation (vertical) scaling
                    "fileformat": "STLb",  # format of 3D model file
                    "zip_file_name": "test_local_bottom_image",   # base name of zipfile, .zip will be added
                    "no_bottom": False,  # do not create bottom triangles
                    "no_normals": True,  # no normals 
                    "bottom_image": "test/bottom_image_test.png"
        }
        run_get_zipped_tiles(args, "local geotiff single tile with bottom relief image")
  

  # some leftovers ...
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



# main method program starts here
# runs all test methods except those with skip decorators 
if __name__ == '__main__':
    unittest.main(verbosity=3)
    