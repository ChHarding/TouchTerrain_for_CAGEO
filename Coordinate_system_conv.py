"""
Coordinate_system_conv  - some utility functions for coordinate system conversion
"""


# CH 6/2014

import math

def arcDegr_in_meter(latitude_in_degr):   
    """Calculate the meter distance for one arc-degree latitude and longitude at a given latitude
    see http://www.csgnetwork.com/degreelenllavcalc.html
    should conform to WGS84 (???)

    Arg: latitude_in_degr: float
    returns tuple of floats (latitude_in_m, longitude_in_m)
    
    """    
    lat = math.radians(latitude_in_degr) # convert lat to rads
    m1 = 111132.954;		# latitude calculation term 1
    m2 = -559.822;		# latitude calculation term 2
    m3 = 1.175;			# latitude calculation term 3
    m4 = -0.0023;		# latitude calculation term 4
    p1 = 111412.84;		# longitude calculation term 1
    p2 = -93.5;			# longitude calculation term 2
    p3 = 0.118;			# longitude calculation term 3

    latlen =  m1 + (m2 * math.cos(2.0 * lat)) + (m3 * math.cos(4.0 * lat)) + (m4 * math.cos(6.0 * lat));
    longlen = (p1 * math.cos(lat)) + (p2 * math.cos(3 * lat)) + (p3 * math.cos(5 * lat));
    return (latlen, longlen);
      

def LatLon_to_UTM(arg1, arg2=None):
    """ given latitude (easting) and longitude (northing) as floats,
        return the UTM zone number (1 to 60) and "N" for North or "S" for South as a tuple
        or -1 on error
        
        Can be called with only one arg as a tuple: LatLon_to_UTM((e,n)) or with
        two args: LatLon_to_UTM(e,n)
    """
    #if there's no arg2 the lat/long is in a tuple in arg1
    if not arg2:
        easting = arg1[0]
        northing = arg1[1]
    else:
        easting = arg1
        northing = arg2
        
    
    if not -180.0 <= easting <= 180.0 and -90.0 <= nothing <= 90.0: return -1
    utm_zone = int(easting) // 6 + 31 # whole number divison
    if northing >= 0: return (utm_zone, "N")
    else: return (utm_zone, "S")

    
def UTM_zone_to_EPSG_code(utm, NorS):
    """ converts a utm zone to EPSG (WGS84) e.g. UTM zone 17 "N" to EPSG code 32717
    utm : zone as int
    NorS:  "N" for north, "S" for South
    return: EPSG code (SRID) for WGS84 as int, -1 on error
    """
    
    # Sanity checks
    if not 1 <= utm <= 60: return -1
    if not NorS in "NS": return -1
    
    # base SRID
    if NorS == "N": SRID = 32600
    else: SRID = 32700
    
    SRID += utm
    return SRID


# test

#utm,h = LatLon_to_UTM((-108.343,45.2))
#utm,h = LatLon_to_UTM(-108.343,45.2)
#print UTM_zone_to_EPSG_code(utm, h)

#for lat in range(0,80,10): 
#    print lat, arcDegr_in_meter(lat)



####################################    
""" as csv table:
UTM Zone,EPSG Code
"UTM Zone 1 Northern Hemisphere (WGS 84)",32601
"UTM Zone 1 Southern Hemisphere (WGS 84)",32701
"UTM Zone 2 Northern Hemisphere (WGS 84)",32602
"UTM Zone 2 Southern Hemisphere (WGS 84)",32702
"UTM Zone 3 Northern Hemisphere (WGS 84)",32603
"UTM Zone 3 Southern Hemisphere (WGS 84)",32703
"UTM Zone 4 Northern Hemisphere (WGS 84)",32604
"UTM Zone 4 Southern Hemisphere (WGS 84)",32704
"UTM Zone 5 Northern Hemisphere (WGS 84)",32605
"UTM Zone 5 Southern Hemisphere (WGS 84)",32705
"UTM Zone 6 Northern Hemisphere (WGS 84)",32606
"UTM Zone 6 Southern Hemisphere (WGS 84)",32706
"UTM Zone 7 Northern Hemisphere (WGS 84)",32607
"UTM Zone 7 Southern Hemisphere (WGS 84)",32707
"UTM Zone 8 Northern Hemisphere (WGS 84)",32608
"UTM Zone 8 Southern Hemisphere (WGS 84)",32708
"UTM Zone 9 Northern Hemisphere (WGS 84)",32609
"UTM Zone 9 Southern Hemisphere (WGS 84)",32709
"UTM Zone 10 Northern Hemisphere (WGS 84)",32610
"UTM Zone 10 Southern Hemisphere (WGS 84)",32710
"UTM Zone 11 Northern Hemisphere (WGS 84)",32611
"UTM Zone 11 Southern Hemisphere (WGS 84)",32711
"UTM Zone 12 Northern Hemisphere (WGS 84)",32612
"UTM Zone 12 Southern Hemisphere (WGS 84)",32712
"UTM Zone 13 Northern Hemisphere (WGS 84)",32613
"UTM Zone 13 Southern Hemisphere (WGS 84)",32713
"UTM Zone 14 Northern Hemisphere (WGS 84)",32614
"UTM Zone 14 Southern Hemisphere (WGS 84)",32714
"UTM Zone 15 Northern Hemisphere (WGS 84)",32615
"UTM Zone 15 Southern Hemisphere (WGS 84)",32715
"UTM Zone 16 Northern Hemisphere (WGS 84)",32616
"UTM Zone 16 Southern Hemisphere (WGS 84)",32716
"UTM Zone 17 Northern Hemisphere (WGS 84)",32617
"UTM Zone 17 Southern Hemisphere (WGS 84)",32717
"UTM Zone 18 Northern Hemisphere (WGS 84)",32618
"UTM Zone 18 Southern Hemisphere (WGS 84)",32718
"UTM Zone 19 Northern Hemisphere (WGS 84)",32619
"UTM Zone 19 Southern Hemisphere (WGS 84)",32719
"UTM Zone 20 Northern Hemisphere (WGS 84)",32620
"UTM Zone 20 Southern Hemisphere (WGS 84)",32720
"UTM Zone 21 Northern Hemisphere (WGS 84)",32621
"UTM Zone 21 Southern Hemisphere (WGS 84)",32721
"UTM Zone 22 Northern Hemisphere (WGS 84)",32622
"UTM Zone 22 Southern Hemisphere (WGS 84)",32722
"UTM Zone 23 Northern Hemisphere (WGS 84)",32623
"UTM Zone 23 Southern Hemisphere (WGS 84)",32723
"UTM Zone 24 Northern Hemisphere (WGS 84)",32624
"UTM Zone 24 Southern Hemisphere (WGS 84)",32724
"UTM Zone 25 Northern Hemisphere (WGS 84)",32625
"UTM Zone 25 Southern Hemisphere (WGS 84)",32725
"UTM Zone 26 Northern Hemisphere (WGS 84)",32626
"UTM Zone 26 Southern Hemisphere (WGS 84)",32726
"UTM Zone 27 Northern Hemisphere (WGS 84)",32627
"UTM Zone 27 Southern Hemisphere (WGS 84)",32727
"UTM Zone 28 Northern Hemisphere (WGS 84)",32628
"UTM Zone 28 Southern Hemisphere (WGS 84)",32728
"UTM Zone 29 Northern Hemisphere (WGS 84)",32629
"UTM Zone 29 Southern Hemisphere (WGS 84)",32729
"UTM Zone 30 Northern Hemisphere (WGS 84)",32630
"UTM Zone 30 Southern Hemisphere (WGS 84)",32730
"UTM Zone 31 Northern Hemisphere (WGS 84)",32631
"UTM Zone 31 Southern Hemisphere (WGS 84)",32731
"UTM Zone 32 Northern Hemisphere (WGS 84)",32632
"UTM Zone 32 Southern Hemisphere (WGS 84)",32732
"UTM Zone 33 Northern Hemisphere (WGS 84)",32633
"UTM Zone 33 Southern Hemisphere (WGS 84)",32733
"UTM Zone 34 Northern Hemisphere (WGS 84)",32634
"UTM Zone 34 Southern Hemisphere (WGS 84)",32734
"UTM Zone 35 Northern Hemisphere (WGS 84)",32635
"UTM Zone 35 Southern Hemisphere (WGS 84)",32735
"UTM Zone 36 Northern Hemisphere (WGS 84)",32636
"UTM Zone 36 Southern Hemisphere (WGS 84)",32736
"UTM Zone 37 Northern Hemisphere (WGS 84)",32637
"UTM Zone 37 Southern Hemisphere (WGS 84)",32737
"UTM Zone 38 Northern Hemisphere (WGS 84)",32638
"UTM Zone 38 Southern Hemisphere (WGS 84)",32738
"UTM Zone 39 Northern Hemisphere (WGS 84)",32639
"UTM Zone 39 Southern Hemisphere (WGS 84)",32739
"UTM Zone 40 Northern Hemisphere (WGS 84)",32640
"UTM Zone 40 Southern Hemisphere (WGS 84)",32740
"UTM Zone 41 Northern Hemisphere (WGS 84)",32641
"UTM Zone 41 Southern Hemisphere (WGS 84)",32741
"UTM Zone 42 Northern Hemisphere (WGS 84)",32642
"UTM Zone 42 Southern Hemisphere (WGS 84)",32742
"UTM Zone 43 Northern Hemisphere (WGS 84)",32643
"UTM Zone 43 Southern Hemisphere (WGS 84)",32743
"UTM Zone 44 Northern Hemisphere (WGS 84)",32644
"UTM Zone 44 Southern Hemisphere (WGS 84)",32744
"UTM Zone 45 Northern Hemisphere (WGS 84)",32645
"UTM Zone 45 Southern Hemisphere (WGS 84)",32745
"UTM Zone 46 Northern Hemisphere (WGS 84)",32646
"UTM Zone 46 Southern Hemisphere (WGS 84)",32746
"UTM Zone 47 Northern Hemisphere (WGS 84)",32647
"UTM Zone 47 Southern Hemisphere (WGS 84)",32747
"UTM Zone 48 Northern Hemisphere (WGS 84)",32648
"UTM Zone 48 Southern Hemisphere (WGS 84)",32748
"UTM Zone 49 Northern Hemisphere (WGS 84)",32649
"UTM Zone 49 Southern Hemisphere (WGS 84)",32749
"UTM Zone 50 Northern Hemisphere (WGS 84)",32650
"UTM Zone 50 Southern Hemisphere (WGS 84)",32750
"UTM Zone 51 Northern Hemisphere (WGS 84)",32651
"UTM Zone 51 Southern Hemisphere (WGS 84)",32751
"UTM Zone 52 Northern Hemisphere (WGS 84)",32652
"UTM Zone 52 Southern Hemisphere (WGS 84)",32752
"UTM Zone 53 Northern Hemisphere (WGS 84)",32653
"UTM Zone 53 Southern Hemisphere (WGS 84)",32753
"UTM Zone 54 Northern Hemisphere (WGS 84)",32654
"UTM Zone 54 Southern Hemisphere (WGS 84)",32754
"UTM Zone 55 Northern Hemisphere (WGS 84)",32655
"UTM Zone 55 Southern Hemisphere (WGS 84)",32755
"UTM Zone 56 Northern Hemisphere (WGS 84)",32656
"UTM Zone 56 Southern Hemisphere (WGS 84)",32756
"UTM Zone 57 Northern Hemisphere (WGS 84)",32657
"UTM Zone 57 Southern Hemisphere (WGS 84)",32757
"UTM Zone 58 Northern Hemisphere (WGS 84)",32658
"UTM Zone 58 Southern Hemisphere (WGS 84)",32758
"UTM Zone 59 Northern Hemisphere (WGS 84)",32659
"UTM Zone 59 Southern Hemisphere (WGS 84)",32759
"UTM Zone 60 Northern Hemisphere (WGS 84)",32660
"UTM Zone 60 Southern Hemisphere (WGS 84)",32760
"""