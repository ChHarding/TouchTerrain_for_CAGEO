// touchterrain JS

"use strict";  // http://javascript.info/strict-mode


// global variables
let rectangle = -1 // red area box
let map = -1      // Google map
let eemap = -1    // Google Earth Engine map
let div_lines_x = []; // internal division lines for tile boundaries
let div_lines_y = [];
let polygon = -1  // optional masking polygon


/**
* This page will be called from a Python script that uses
* Jinja templates to pass information from the script to the web page.
* Here we get the mapid and token for the map tiles that were generated
* by Earth Engine using the Python script
*/
// gets values inlined from python calling the jinja template
let MAPID = "{{ mapid }}"; // {{ stuff }}
let TOKEN = "{{ token }}";
let map_lat = Number("{{ map_lat }}");  // center of map
let map_lon = Number("{{ map_lon }}");
let map_zoom = Number("{{ map_zoom }}"); // zoom level
let trlat = "{{ trlat }}"; // bounding box top right corner
let trlon = "{{ trlon }}";
let bllat = "{{ bllat }}"; // bottom left corner
let bllon = "{{ bllon }}";
let DEM_name = "{{ DEM_name }}"; // name of DEM layer
let printres = "{{ printres }}"; // in mm
let ntilesx = "{{ ntilesx }}";
let ntilesy = "{{ ntilesy }}";
let tilewidth = "{{ tilewidth }}"; // in mm
let basethick = "{{ basethick }}";
let zscale = "{{ zscale }}";
let fileformat = "{{ fileformat }}";
let manual = "{{ manual }}";
manual = manual.replace(/&#34;/g, '\"')
manual = manual.replace(/&amp;quot;/g, '\"')
let polyURL = "{{ polyURL }}";

// map visualization parameters: maptype, transparency, gamma, hsazi, hzelev
let maptype = "{{ maptype }}";
let transp = "{{ transp }}";
let gamma = "{{ gamma }}";
let hsazi = "{{ hsazi }}";
let hselev = "{{ hselev }}";


// run this once the browser is ready
window.onload = function () {

    // init google map
    let myLatLng = new google.maps.LatLng( map_lat, map_lon);
    let mapOptions = {
        center: myLatLng,
        zoom: map_zoom,
        //maxZoom: 10,
        zoomControl: true,
        scaleControl: true,
        streetViewControl: false,
        mapTypeId: maptype
    };
    
    map = new google.maps.Map(document.getElementById("map"), mapOptions);
    eemap = create_overlay(MAPID, map); // (global) hillshade overlay from google earth engine
    init_print_options(); //update all print option values in the GUI to what was inlined by jinja
    update_options_hidden(); // also store values in hidden ids
    SetDEM_name();  // sets DEM_name pulldown to what was inlined by jinja
    polygon = new google.maps.Polygon({ // make empty polygon for now, will set paths later
                    strokeColor: "#FFFF00",
                    strokeOpacity: 1,
                    strokeWeight: 0.75,
                    fillColor: "#FFFF00",
                    fillOpacity: 0.05
              });
    
    // Init map Overlay GUI settings
    updateTransparency(transp); // set initial transparency 
    updateGamma(gamma); // initial gamma value
    document.getElementById('hsazi2').value = hsazi;
    document.getElementById('hselev2').value = hselev;
    
    // Area selection box
    rectangle = new google.maps.Rectangle({
        editable: true,
        draggable: true,
        strokeColor: '#FF0000',
        strokeOpacity: 0.8,
        strokeWeight: 2,
        fillColor: '#FF0000',
        fillOpacity: 0.01,
        map: map
    });

    // if we got rectangle bounds from jinja args, draw box
    if (trlat != "" && trlon != "" && bllat != "" && bllon != ""){
        let tr = new google.maps.LatLng(Number(bllat),Number(trlon));
        let bl = new google.maps.LatLng(Number(trlat), Number(bllon));
        let initial_bounds = new google.maps.LatLngBounds();
        initial_bounds.extend(tr);
        initial_bounds.extend(bl);

        //alert(initial_bounds.toUrlValue(2))
        // draw rectangle and put coords in form
        rectangle.setBounds(initial_bounds);
        update_corners_form();
    }
    else{ // at this stage we don't have map bounds to make the box bounds b/c it hasn't been
            // drawn yet, so we need to defer that until the map bounds_changed is called.
            google.maps.event.addListenerOnce(map, 'bounds_changed', function(){
            center_rectangle();
            });
    }
    
    // show link for current DEM source
    let link = "https://developers.google.com/earth-engine/datasets"
    switch(DEM_name){
        case "USGS/NED": link = "https://developers.google.com/earth-engine/datasets/catalog/USGS_NED"; break;
        case "NRCan/CDEM": link = "https://developers.google.com/earth-engine/datasets/catalog/NRCan_CDEM"; break;
        case "USGS/SRTMGL1_003": link ="https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003"; break;
        case "JAXA/ALOS/AW3D30/V2_2": link = "https://developers.google.com/earth-engine/datasets/catalog/JAXA_ALOS_AW3D30_V2_2"; break;
        case "USGS/GMTED2010": link = "https://developers.google.com/earth-engine/datasets/catalog/USGS_GMTED2010"; break;
        case "USGS/GTOPO30" : link = "https://developers.google.com/earth-engine/datasets/catalog/USGS_GTOPO30"; break;
        case "CPOM/CryoSat2/ANTARCTICA_DEM" : link = "https://developers.google.com/earth-engine/datasets/catalog/CPOM_CryoSat2_ANTARCTICA_DEM"; break;
        case "NOAA/NGDC/ETOPO1": link ="https://developers.google.com/earth-engine/datasets/catalog/NOAA_NGDC_ETOPO1"; break;
    }
    document.getElementById('DEM_link').href = link;

    // 
    // Callbacks
    //
    
    // Add an event listener on the rectangle.
    rectangle.addListener('bounds_changed', update_corners_form);
    rectangle.addListener('dragstart', remove_divison_lines);
    rectangle.addListener('dragend', create_divison_lines);

    // Add event for when map becomes idle again after zoom or pan, saves map center and zoom in element
    map.addListener("idle", saveMapSettings);

    // add callbacks to recalc and display real world resolution when these options are changed
    document.getElementById('options_print_resolution').addEventListener("click", setApproxDEMResolution_meters);
    document.getElementById('options_tile_width').addEventListener("click", setApproxDEMResolution_meters);
    document.getElementById('options_numTiles_x').addEventListener("click", setApproxDEMResolution_meters);

    // add callbacks to make/change division lines when number of tiles change
    document.getElementById('options_numTiles_x').addEventListener("click", create_divison_lines);
    document.getElementById('options_numTiles_y').addEventListener("click", create_divison_lines);

    // add change callback for kml_file button
    let fileInput = document.getElementById('kml_file');
    fileInput.addEventListener('change', function(e) {
    if (fileInput.files.length) {
        let file = fileInput.files[0];
        let reader = new FileReader();
        reader.onload = function(e) {
            let s = reader.result;
            const [bbox, latloncoords] = processKMLFile(s);
            if(!!bbox){ // not null => valid bounding box
                rectangle.setBounds(bbox);
                update_corners_form();
                map.fitBounds(bbox); // makes the map fit around the box
                polygon.setPath(latloncoords);
                polygon.setMap(map);
            }else{
                alert("Error: invalid KML file!");
            }
        }
        reader.readAsText(file);
    }
    });

}; // end of onload()

//
// FUNCTIONS
//

// Create an ImageOverlay using the MapID, which encodes all the vis params (besides opacity, which is set browser-side)
function create_overlay(MAPID, map){
    const EE_MAP_PATH = 'https://earthengine.googleapis.com/v1alpha';
    const tileSource = new ee.layers.EarthEngineTileSource({
                                MAPID,
                                TOKEN,
                                formatTileUrl: (x, y, z) =>
                                `${EE_MAP_PATH}/${MAPID}/tiles/${z}/${x}/${y}`
    });
    eemap = new ee.layers.ImageOverlay(tileSource); // eemap is a global so we can change its gamma later 
    map.overlayMapTypes.removeAt(0); // remove old overlay
    map.overlayMapTypes.insertAt(0, eemap); // insert as index 0, use this for opacity: map.overlayMapTypes.getAt(0).setOpacity(0.25)
    return eemap;
}

// Function to return an arc-degree distance in meters at a given latitude
// as an array (along_east, along_north)
// see http://www.csgnetwork.com/degreelenllavcalc.html
// should conform to WGS84
function arcDegr_in_meter(latitude_in_degr){
    let lat = (2.0 * Math.PI)/360.0 * latitude_in_degr; // convert lat to rads
    let m1 = 111132.954;	// latitude calculation term 1
    let m2 = -559.822;		// latitude calculation term 2
    let m3 = 1.175;		// latitude calculation term 3
    let m4 = -0.0023;		// latitude calculation term 4
    let p1 = 111412.84;		// longitude calculation term 1
    let p2 = -93.5;		// longitude calculation term 2
    let p3 = 0.118;		// longitude calculation term 3

    // Calculate the length of a degree of latitude and longitude in meters
    let latlen =  m1 + (m2 * Math.cos(2 * lat)) + (m3 * Math.cos(4 * lat)) + (m4 * Math.cos(6 * lat));
    let longlen = (p1 * Math.cos(lat)) + (p2 * Math.cos(3 * lat)) + (p3 * Math.cos(5 * lat));
    return [latlen, longlen];
}


// create a centered LatLngBounds box
function make_center_box(){
    let bounds = map.getBounds();
    let projection = map.getProjection();
    let topRight = bounds.getNorthEast(); // not sure if these have to be projected first ...
    let bottomLeft = bounds.getSouthWest();
    let c = bounds.getCenter();
    let cx = c.lng()
    let cy = c.lat()
    let nex = topRight.lng()
    let ney = topRight.lat()
    let swx = bottomLeft.lng()
    let swy = bottomLeft.lat()

    let box_size_x = (nex - swx) / 3.0
    let box_size_y = (ney - swy) / 3.0
    let box = new google.maps.LatLngBounds();
    let p = new google.maps.LatLng(cy - box_size_y, cx - box_size_x);
    box.extend(p);
    p = new google.maps.LatLng(cy + box_size_y, cx + box_size_x);
    box.extend(p)
    return(box);
}

// set bounding box of rectangle so it's centered
function center_rectangle(){
    polygon.setMap(null); // remove polygon
    let box = make_center_box();
    rectangle.setBounds(box);
    update_corners_form();
}

// callback to update corner lat/lon in form to current rectangle
function update_corners_form(event) {
    let b = rectangle.getBounds()
    let trlat = b.getNorthEast().lat();
    let trlon = b.getNorthEast().lng();
    let bllat = b.getSouthWest().lat();
    let bllon = b.getSouthWest().lng();

    // update GUI values
    document.getElementById('trlat2').value=trlat;
    document.getElementById('trlon2').value=trlon;
    document.getElementById('bllat2').value=bllat;
    document.getElementById('bllon2').value=bllon;

    // also update hidden id values
    document.getElementById('trlat').value=trlat;
    document.getElementById('trlon').value=trlon;
    document.getElementById('bllat').value=bllat;
    document.getElementById('bllon').value=bllon;

    setApproxDEMResolution_meters();
    calcTileHeight();

    create_divison_lines();
}

function update_box(event){

    // read values from GUI
    trlat = document.getElementById('trlat2').value;
    trlon = document.getElementById('trlon2').value;
    bllat = document.getElementById('bllat2').value;
    bllon = document.getElementById('bllon2').value;

    // update hidden id values
    document.getElementById('trlat').value=trlat;
    document.getElementById('trlon').value=trlon;
    document.getElementById('bllat').value=bllat;
    document.getElementById('bllon').value=bllon;

    // make and new bounds
    var newbounds = new google.maps.LatLngBounds(
        new google.maps.LatLng(bllat,bllon), // sw
        new google.maps.LatLng(trlat, trlon) // ne
    );
    rectangle.setBounds(newbounds);
}


// calculate the approximate meter resolution of each pixel at the current lat
// from the width (lon) of the rectangle and the print resolution
function setApproxDEMResolution_meters() {
    let b = rectangle.getBounds();
    let trlat = b.getNorthEast().lat();
    let trlon = b.getNorthEast().lng();
    let bllat = b.getSouthWest().lat();
    let bllon = b.getSouthWest().lng();
    let print_res_mm = document.getElementById('options_print_resolution').value;

    // Negative print_res_mm means that "source resolution" is selected, in this case just set field to "same"
    if(print_res_mm <= 0){
        document.getElementById('DEMresolution').value = 'the same'
    }
    else{
        let tw_mm = document.getElementById('options_tile_width').value;
        let num_tiles_x = document.getElementById('options_numTiles_x').value;
        let num_cells_per_tile = tw_mm /  print_res_mm;
        let total_cells = num_cells_per_tile * num_tiles_x;

        let lat_of_center = (trlat + bllat) / 2.0;
        let box_width_in_degr = Math.abs(trlon - bllon);
        let one_degr_in_m = arcDegr_in_meter(lat_of_center)[1]; // returns meters for [lat,lon] => lon = with = [1]
        let box_width_in_m = box_width_in_degr * one_degr_in_m;

        let cell_resolution_meter = box_width_in_m / total_cells;
        //console.log(cell_resolution_meter);
        cell_resolution_meter = Math.round( cell_resolution_meter * 100 ) / 100; // round to 2 digits
        document.getElementById('DEMresolution').value = cell_resolution_meter;
    }
}

function remove_divison_lines(){
    for (let i = 0; i < div_lines_x.length; i++) {
        div_lines_x[i].setMap(null) // remove from map
    }
    div_lines_x = [];

    for (let i = 0; i < div_lines_y.length; i++) {
        div_lines_y[i].setMap(null) // remove from map
    }
    div_lines_y = [];
}


function create_divison_lines(event) {
    remove_divison_lines(); // also re-sets array to []

    let bounds = rectangle.getBounds(); // bounds of red box
    let ne = bounds.getNorthEast();
    let sw = bounds.getSouthWest();
    let span = rectangle.getBounds().toSpan() // height/width of box

    let num_lines = document.getElementById('options_numTiles_x').value -1; //requested number of lines
    if(num_lines > 0){
    let width = span.lng() / (num_lines + 1) // width of a tile
    for (let i = 0; i < num_lines; i++) {
        let x = sw.lng() + (i+1) * width; // x-coord (lng) of line
        let line_coords = [{lat: ne.lat(), lng: x }, {lat: sw.lat(), lng: x }];
        div_lines_x[i] = new google.maps.Polyline({ path: line_coords,
                        geodesic: false, strokeColor: '#FF0000',
                        strokeOpacity: 1.0, strokeWeight: 1 });
        div_lines_x[i].setMap(map);
    }
    }

    num_lines = document.getElementById('options_numTiles_y').value-1;
    if(num_lines > 0){
        let height = span.lat() / (num_lines + 1) // height of a tile
        for (let i = 0; i < num_lines; i++) {
            let y = sw.lat() + (i+1) * height; // y coord (lat) of line
            let line_coords = [{lat: y, lng: sw.lng()},
                            {lat: y, lng: ne.lng()}];
            div_lines_y[i] = new google.maps.Polyline({ path: line_coords,
                                                        geodesic: false, strokeColor: '#FF0000',
                                                        strokeOpacity: 1.0, strokeWeight: 1 });
            div_lines_y[i].setMap(map);
        }
    }
}

// update functions, called from HTML
function SetDEM_name(){
    document.getElementById('DEM_name').value = DEM_name // hidden
    document.getElementById('DEM_name2').value = DEM_name // GUI

    let res = "unknown resolution"
    switch(DEM_name){
    case "USGS/NED": res = "10 m"; break;
        case "NRCan/CDEM": res = "20 m"; break;
    case "USGS/SRTMGL1_003": res = "30 m"; break;
        case "JAXA/ALOS/AW3D30/V2_2": res = "30 m"; break;
    case "USGS/GMTED2010": res = "90 m"; break;
        case "USGS/GTOPO30" : res = "1000 m"; break;
        case "CPOM/CryoSat2/ANTARCTICA_DEM" : res = "1000 m"; break;
    case "NOAA/NGDC/ETOPO1": res = "2000 m"; break;
    }

    // set resolution of DEM source
    document.getElementById('source_resolution').innerHTML = res
}


// set opacity of hillshade as inverse of transparency given
function updateTransparency(transparency_pct) {
    let op = 1.0 - transparency_pct / 100.0 // opacity
    map.overlayMapTypes.getAt(0).setOpacity(op)
    //document.getElementById('hillshade_transparency').value=transparency_pct;
    document.getElementById('hillshade_transparency_slider').value=transparency_pct;
    document.getElementById('transp').value=transparency_pct; // id in hidden reload
}

//Update gamma in both places
function updateGamma(val) {
    document.getElementById('gamma').value=val;  // id in reload form  (hidden)
    document.getElementById('gamma2').value=val; // gui text field
    //document.getElementById('hs_slider').value=val; // gui slider
}

// update hillshade elevation(angle above horizon) and adjust gamma
function updateHillshadeElevation(elev) {
    document.getElementById('hselev').value=elev;   // hidden id
    document.getElementById('hselev2').value=elev;  // gui list
    switch(Number(elev)) {
    case 55: // steep
        updateGamma(0.3); break;
    case 45: // normal
        updateGamma(1.0); break;
    case 35: // somewhat flat
        updateGamma(1.2); break;
    case 25: // very flat
        updateGamma(1.5); break;
    case 10: // super flat
        updateGamma(2.5); break;
    case 5: // extremely flat
        updateGamma(4.5); break;
    default:
        alert(elev + "is bad!");
    } 
}  

// update the hidden ids in reload form
function update_options_hidden(){
    //alert("update_options_hidden")
    document.getElementById('tilewidth').value = document.getElementById('options_tile_width').value;
    document.getElementById('ntilesx').value = document.getElementById('options_numTiles_x').value;
    document.getElementById('ntilesy').value = document.getElementById('options_numTiles_y').value;
    document.getElementById('printres').value = document.getElementById('options_print_resolution').value;
    document.getElementById('basethick').value = document.getElementById('options_base_thickness').value;
    document.getElementById('zscale').value = document.getElementById('options_z_scale').value;
    document.getElementById('fileformat').value= document.getElementById('options_fileformat').value;
    document.getElementById('manual').value= document.getElementById('options_manual').value;
    document.getElementById('polyURL').value= document.getElementById('options_polyURL').value;
}

// update the print option values in the GUI from the global vars
function init_print_options(){
    //alert("init_print_options")
    document.getElementById('options_tile_width').value = tilewidth;
    document.getElementById('options_numTiles_x').value = ntilesx;
    document.getElementById('options_numTiles_y').value = ntilesy;
    document.getElementById('options_print_resolution').value = printres;
    document.getElementById('options_base_thickness').value = basethick;
    document.getElementById('options_z_scale').value = zscale;
    document.getElementById('options_fileformat').value = fileformat;
    document.getElementById('options_manual').value = manual;
    document.getElementById('options_polyURL').value = polyURL; 
}

// called on idle (after map pan/zoom), sets current lat, lon and zoom
function saveMapSettings(){
    let  c = map.getCenter();
    let cx = c.lng();
    let cy = c.lat();
    
    // hidden ids in reloadform
    document.getElementById('map_lat').value = c.lat();
    document.getElementById('map_lon').value = c.lng();
    document.getElementById('map_zoom').value = map.getZoom(); 
}

function submit_for_reload(trans_method){
    saveMapSettings();
    
    // save current settings into hidden ids
    document.getElementById('maptype').value = map.getMapTypeId();
    document.getElementById('hsazi').value = document.getElementById('hsazi2').value;
    document.getElementById('hselev').value = document.getElementById('hselev2').value;
    
    // trigger a reload with all the vars in reloadform
    let f = document.forms["reloadform"];
    f.method = trans_method
    f.submit();
}

// calc tile height from given mm width and red box ratio
// not that ratio has to be calculated from the meters, not degrees!
function calcTileHeight(){
    let tw = document.getElementById('options_tile_width').value;
    document.getElementById('tilewidth').value = tw // set hidden id for reload
    let bounds = rectangle.getBounds(); // bounds of red box
    let n = bounds.getNorthEast().lat();
    let s = bounds.getSouthWest().lat();
    let center_lat = (n + s ) / 2.0;
    let degr_in_m  = arcDegr_in_meter(center_lat);
    let span = rectangle.getBounds().toSpan();
    let hm = span.lat() * degr_in_m[0]; // height in meters at center lat
    let wm = span.lng() * degr_in_m[1]; // width

    let hw_in_meter_ratio = hm / wm; // height/width of box
    let th = tw * hw_in_meter_ratio;

    //console.log(tw, span.lat(),  span.lng(), center_lat, hm, wm, hw_in_meter_ratio, );
    let tile_height_rounded  = parseInt(th * 10) / 10;
    document.getElementById('options_tile_height').value = th;
    document.getElementById('options_tile_height').innerHTML = tile_height_rounded + "&nbsp mm";
}

// return bounds of polygon in kml file or null on parse error or if <3 coords
function processKMLFile(xmlfile){
    if (xmlfile && xmlfile.length){  // file exists and is not empty
        // parse XML file
        let xmlDoc = null;
        try {
            xmlDoc = $.parseXML(xmlfile);
        }
        catch(e) {
            console.dir(e);
            return null;
        }

        let $xml = $(xmlDoc);
        if (typeof xmlDoc === 'undefined'){ /// === means == but w/o implicit type conversion
            alert('Please upload a KML file');
            return null;
        }else{
            let coords = $xml.find("coordinates").text();
            //console.dir(JSON.stringify(coords)); //"\n\t\t\t1\n\t\t\t\n\t\t\t\t\n\t\t\t\t\t -109.5396705603448,38.47691322695024,0 -109.5396705603448,38.47691322695024,0 \n\t\t\t\t\t\n\t\t\t\t\n\t\t\t\n\t\t"

            // remove tabs and newlines and trim
            coords = coords.replace(/\t/g, '');
            coords = coords.replace(/\n/g, '');
            coords = coords.trim();
            //console.dir(JSON.stringify(coords)) //"-109.5396705603448,38.47691322695024,0 -109.5396705603448,38.47691322695024,0"

            // split at space in array of strings with "x,y,z"
            coords = coords.split(" ");
            //console.dir(JSON.stringify(coords))

            // if we have less than 3 coords, bail out
            if (coords.length < 3){
                alert("Error: KML file does not contain polygon (need >2 coordinates)!");
                return(null);
            }

            // make arrays of x and y coords
            let xcoords = [];
            let ycoords = [];
            let llcoords = []; // array of lat/lon coords, used for polygon path later
            for (let i=0; i < coords.length; i++) {
                let c = coords[i].split(","); // split in 3 x,y,z strings
                //console.log(c[0], c[1]);
                xcoords.push(c[0]);
                ycoords.push(c[1]);

                let ll = new google.maps.LatLng(c[1], c[0])
                llcoords.push(ll)
            }

            // convert string array to number array
            xcoords = xcoords.map(Number);
            ycoords = ycoords.map(Number);

            // get min/max of arrays
            let xmax = Math.max(...xcoords); // ... is spread operator
            let ymax = Math.max(...ycoords);
            let xmin = Math.min(...xcoords);
            let ymin = Math.min(...ycoords);
            //console.log(xmin, xmax, ymin, ymax)

            // make bounds
            let southWest = new google.maps.LatLng(ymin, xmin);
            let northEast = new google.maps.LatLng(ymax, xmax);
            let bounds = new google.maps.LatLngBounds(southWest,northEast);
            //console.log(southWest.toString(), northEast.toString(), bounds.toString());
            
            return [bounds, llcoords] 
        }
    }
}