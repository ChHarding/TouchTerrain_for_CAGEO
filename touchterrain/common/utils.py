''' TouchTerrain utilities '''

# stuff that might be useful for later ...

def store_static_Google_map(bllon, trlon, bllat, trlat, google_maps_key, temp_folder, zip_file_name):
    '''Grabs and stores a static google map of the are. 
    Returns the image file name or None (on fail)
    '''
    URL = "https://maps.googleapis.com/maps/api/staticmap?"
    URL += "maptype=terrain&"
    URL += "format=jpg-baseline&"  
    URL += "size=640x640&"  
    URL += "path=color:0xff000080|weight:1|" # thin red 50% transp
    # path for area box NE SE SW NW NE
    URL += f"{trlat},{trlon}|{bllat},{trlon}|{bllat},{bllon}|{trlat},{bllon}|{trlat},{trlon}&"
    URL += "key=" + google_maps_key
    #print(URL)
    r = requests.get(URL)
    if r.status_code == 200:
        img = Image.open(BytesIO(r.content))
        map_img_filename = temp_folder + os.sep + zip_file_name + ".jpg"
        try: 
            img.save(map_img_filename)
        except Exception as e:
            print("Error:", e, file=sys.stderr)
            return None
        else:
            return map_img_filename
    return None