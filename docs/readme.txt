TouchTerrain - 3D-printing of Digital Elevation Data
=====================================================


Version 0.12 (Dec. 12, 2016)
- added auto calc of tile height (using meter based aspect ration)
- added better shwoing of raster rescaling
- added drawing of tile boundaries
- changed web layout a bit
- hillshade gamma values can now be changed (will reload as gamma is set on server side)
- added SRTM 30 m ("worldwide" but not very far north) and clarified that GMTED is 90 m (but worldwid-er_

Version 0.11 (Nov. 8, 2016)
- Levi added Apache server support
- Levi fixed noob global var for preflight request 

Version 0.10 (June 20, 2016)
- switched SRTM to GMTED2010, added ETOPO1

Version 0.09 (Jan. 20, 2015)
- DEMs will now switch at once when selected,  no need to press another push button
- SRTM DEMS will no longer use -32768 m for water


Version 0.08 (Dec. 16, 2015)
- added switch between NED (10m) and STRM (90m) DEM. Note that your area selection box will recenter when switching DEMs

Version 0.07
- added google maps zoom control UI element (thanks Ian!) 
- added fileformat option: obj, STL (binary/ascii)

Version 0.06 (Nov.23, 2015):
- still now way to give any feedback on processing state, but I added a preflight page with some notes
- after processing a new page is shown with a download button for the zip file (which will be deleted after 24 hrs)

Version 0.05 (Nov.12, 2015):
- added approximation of real-world DEM resolution to be used with the selected area box, 3D print resolution and tile size/number.

Version 0.04 (Oct. 30, 2015):
- Download tested on Firefox and Chrome (on Chrome, need to use Save as when the finished zip file is displayed)















-------------------------------------------------------

Developer Contact: Chris Harding, Iowa State University, charding@iastate.edu
Website: http://www.public.iastate.edu/~franek/gfl/gfl.html
Disclaimer: The website and the 3D model files it creates are provided as a public service without any guarantees or warranty. 
            Use of the the website and any 3D model file downloaded from it is permitted for non-commercial use only and at the user's risk. 
