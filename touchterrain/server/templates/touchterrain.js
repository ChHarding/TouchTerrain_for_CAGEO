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
let warning = "{{ warning }}";

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
    document.getElementById("maptype").value = maptype
    document.getElementById("maptype3").value = maptype
    let map_width = document.getElementById("map").getBoundingClientRect().width
    if(map_width > 900){ map_width = 900} // for very wide screens, setting height to a very large number (>900) doesn't seem to work(?)
    document.getElementById("map").style.height = map_width; // make square map

    
    // Create the search box and link it to the UI element.
    // https://developers.google.com/maps/documentation/javascript/examples/places-autocomplete
    
    // Make an icon and a marker for showing result of place search
    const icon = {
        url: "https://maps.gstatic.com/mapfiles/place_api/icons/v1/png_71/geocode-71.png",
        size: new google.maps.Size(71, 71),
        origin: new google.maps.Point(0, 0),
        anchor: new google.maps.Point(17, 34),
        scaledSize: new google.maps.Size(25, 25),
    };
    let marker = new google.maps.Marker({
        map,
        icon,
        //title: place.name,
        //position: place.geometry.location,
        //animation: google.maps.Animation.DROP,
        //animation: google.maps.Animation.BOUNCE,
    });
   
    // Drawing manager  (for later?)
    /*
    const drawingManager = new google.maps.drawing.DrawingManager({
        drawingMode: null, //google.maps.drawing.OverlayType.RECTANGLE,
        drawingControl: true,
        drawingControlOptions: {
          position: google.maps.ControlPosition.TOP_RIGHT,
          drawingModes: [
            google.maps.drawing.OverlayType.RECTANGLE,
            google.maps.drawing.OverlayType.POLYGON,
            google.maps.drawing.OverlayType.CIRCLE,
          ],
        },
        circleOptions: {
            editable: true,
            draggable: true,
            strokeColor: '#FF0000',
            strokeOpacity: 0.8,
            strokeWeight: 2,
            fillColor: '#FF0000',
            fillOpacity: 0.02,
        },
        rectangleOptions: {
            editable: true,
            draggable: true,
            strokeColor: '#FF0000',
            strokeOpacity: 0.8,
            strokeWeight: 2,
            fillColor: '#FF0000',
            fillOpacity: 0.02,
        },
        polygonOptions: {
            editable: true,
            draggable: true,
            strokeColor: '#FF0000',
            strokeOpacity: 0.8,
            strokeWeight: 2,
            fillColor: '#FF0000',
            fillOpacity: 0.02,
        },
      
      });
      drawingManager.setMap(map);
      
      google.maps.event.addListener(drawingManager, 'overlaycomplete', function(event) {
        if (event.type == 'rectangle') {
          rectangle = event.overlay;
        }
      });
      */
    
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
    document.getElementById('hsazi3').value = hsazi;
    document.getElementById('hselev3').value = hselev;
    
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
        let tr = new google.maps.LatLng(Number(bllat), Number(trlon));
        let bl = new google.maps.LatLng(Number(trlat), Number(bllon));
        let initial_bounds = new google.maps.LatLngBounds();
        initial_bounds.extend(tr);
        initial_bounds.extend(bl);

        //alert(initial_bounds.toUrlValue(2))
        // draw rectangle and put coords in form
        rectangle.setBounds(initial_bounds);
        update_corners_form();
    }
    else{// at this stage we don't have map bounds to make the box bounds b/c it hasn't been
        // drawn yet, so we need to defer that until the map's bounds_changed is called.
        google.maps.event.addListenerOnce(map, 'bounds_changed', 
            function(){
                center_rectangle();
            }
        );
    }
    
    // show link for current DEM source
    let link = "https://developers.google.com/earth-engine/datasets"
    switch(DEM_name){
        case "USGS/NED": link = "https://developers.google.com/earth-engine/datasets/catalog/USGS_NED"; break;
        case "NRCan/CDEM": link = "https://developers.google.com/earth-engine/datasets/catalog/NRCan_CDEM"; break;
        case "AU/GA/AUSTRALIA_5M_DEM": link = "https://developers.google.com/earth-engine/datasets/catalog/AU_GA_AUSTRALIA_5M_DEM"; break;
        case "USGS/SRTMGL1_003": link ="https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003"; break;
        case "MERIT/DEM/v1_0_3": link = "https://developers.google.com/earth-engine/datasets/catalog/MERIT_DEM_v1_0_3"; break;
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
    
    // Add an event listener on the rectangle (red box).
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
        if(file.name.endsWith(".kml")){
            let reader = new FileReader();
            reader.onload = function(e) {
                let s = reader.result;
                const [bbox, latloncoords] = processKMLFile(s);
                if(!!bbox){ // not null => valid bounding box
                    rectangle.setBounds(bbox); 
                    update_corners_form();
                    map.fitBounds(bbox); // makes the map fit around the box
                    polygon.setPath(latloncoords); // make polygon ...
                    polygon.setMap(map); // and draw
                    fileInput.name = "kml_file"; // will be a key in response.files dict
                    $('#kml_file_name').html(file.name); // show valid filename in label
                }else{
                    $('#kml_file_name').html("Error: " + file.name + " not a valid kml file!");
                    fileInput.name.value = null; // invalidate previous kml file
                    polygon.setMap(null); // remove any earlier polygon
                    // bad file will be read-in in Python and generate a warning there
                }
            }
            reader.readAsText(file);
        }
      
        // unzip kmz file into kml first
        else if(file.name.endsWith(".kmz")){
            const reader = new zip.ZipReader(new zip.BlobReader(file));
            const entries =  reader.getEntries(); // get all entries from the zip
            reader.getEntries().then(function(entries){
                //console.log(entries);
                if (entries.length) {
                    // get first entry content as text by using a TextWriter
                    const text =  entries[0].getData(
                        new zip.TextWriter()
                    ).then(function(text) {
                        const [bbox, latloncoords] = processKMLFile(text);
                        if(!!bbox){ // not null => valid bounding box
                            rectangle.setBounds(bbox); 
                            update_corners_form();
                            map.fitBounds(bbox); // makes the map fit around the box
                            polygon.setPath(latloncoords); // make polygon ...
                            polygon.setMap(map); // and draw
                            fileInput.name = "kml_file"; // will be a key in response.files dict
                            $('#kml_file_name').html(file.name); // show valid filename in label
                        }else{
                            $('#kml_file_name').html("Error: " + file.name + " not a valid kmz file!")
                            fileInput.name.value = null // invalidate previous kml file
                            polygon.setMap(null); // remove any earlier polygon
                            // bad file will be read-in in Python and generate a warning there
                        }
                    });
                }
            })
        }
        else{ // neither kml nor kmz
            $('#kml_file_name').html("Error: " + file.name + " not a valid kml/kmz file!")
            fileInput.name.value = null // invalidate previous kml file
            polygon.setMap(null); // remove any earlier polygon
        }
      } // if (fileInput.files.length)
    });

    // Place Search
    const input = document.getElementById("pac-input");
    map.controls[google.maps.ControlPosition.TOP_LEFT].push(input);

    /*
    // Version A: Autocomplete and FindPlace but only gets back the geometry
    const autocomplete = new google.maps.places.Autocomplete(input);
    autocomplete.bindTo("bounds", map); // bias results to current viewport
    autocomplete.setOptions({ strictBounds: false }); //false: do NOT restrict, just bias

    // Set the data fields to return when the user selects a place.
    autocomplete.setFields(["geometry"]); // "icon", "name"

    autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        marker.setVisible(false);

        if (!place.geometry) {
          // User entered the name of a Place that was not suggested and
          // pressed the Enter key, or the Place Details request failed.
          window.alert("Nothing found for input: " + 
                        document.getElementById("pac-input").value);
          return;
        }

        // Jump to place
        if (place.geometry.viewport) {
          map.fitBounds(place.geometry.viewport);
        } else {
          map.setCenter(place.geometry.location);
          map.setZoom(17); // Why 17? Because it looks good.
        }

        // Configure marker
        marker.setPosition(place.geometry.location);
        marker.setTitle(document.getElementById("pac-input").value);
        marker.setVisible(true);

        // throw auto found place name (from search box) at GA
        ga('send', 'event', 'placename', 'SearchBoxText',
            document.getElementById("pac-input").value , {nonInteraction: true});

        // Update place id in form 2
        document.getElementById("place").value = document.getElementById("pac-input").value;

    }); // end version A
    */

    
    // Version B: no autocomplete, uses FindPlace with ONLY the Place id (free) and uses
    // the cheaper Geocoding API to look up info on that Place id
    document.getElementById("pac-input").addEventListener("keydown", function(e){
      if (e.key === "Enter") {  // checks whether the pressed key is "Enter"
    
        const search_term = document.getElementById("pac-input").value;
        const request = {
            query: search_term,
            fields: ["place_id"] //"geometry", "name", "formatted_address", "types"] 
        };
        const service = new google.maps.places.PlacesService(map);
        service.findPlaceFromQuery(request, (results, status) => {
            if (status === google.maps.places.PlacesServiceStatus.OK) {
                const place_id = results[0].place_id;
                marker.setVisible(false);

                // Look up info on place_id
                const geocoder = new google.maps.Geocoder();
                geocoder.geocode({placeId: place_id}, (results, status) => {
                    if (status !== "OK") {
                      window.alert("Geocoder failed due to: " + status);
                      return;
                    }
                    if (results.length < 1 || !results[0].geometry) {
                        window.alert("No results for " + search_term + ", please try a different search (be more specific?)")
                        return;
                    }
                    const place = results[0];
                
                    // Fly to place
                    if (place.geometry.viewport) {
                        map.fitBounds(place.geometry.viewport);
                    } else {
                        map.setCenter(place.geometry.location);
                        map.setZoom(17); // Why 17? Because it looks good.
                    }

                    // Create marker
                    marker.setPosition(place.geometry.location);
                    var name = "";
                    if(typeof place.name == "undefined"){ // FU JS! 
                        name = place.formatted_address }
                    else {
                        name = place.name};
                    marker.setTitle(name + "\n" + place.types + "\n" + place.formatted_address);
                    marker.setVisible(true);

                    // Update search field
                    document.getElementById("pac-input").value = "";
                    document.getElementById("pac-input").placeholder = "Search for a place (last search result: " + name + ")";

                    // throw place name at GA
                    ga('send', 'event', 'placename', 'SearchBoxText',name , {nonInteraction: true});

                    // Update place id in form 2
                    document.getElementById("place").value = name;

                    // center print area box
                    center_rectangle();
                });
            } else {
                window.alert("No results for " + search_term + ", please try a different search (be more specific?)");
                return;
            }
        });
      }
    }); // end version B
    
    // help popovers
    $('#Whats_new__popover').popover({
        content: 'Mouse over the question marks to see the help text or click on it to toggle the text on/off<br><br>\
                  New in 3.4: fixed kml file issues<br><br>\
                  New in 3.3:<br>\
                  <ul><li>Help popups explain the different options and settings.</li>\
                      <li>Better z-scaling: will let you define how tall you want your printed model to be (model height), \
                        automatically calculates the required z-scale value.</li>\
                      <li>Help hints for CNC users.</li>\
                      <li>.kmz files (compressed kml) can now be used for polygons, in addition to .kml files.</li>\
                      </ul>',
        html: true,
        trigger: 'click hover',
        placement: 'auto'
    });

    $('#terrain_settings_popover').popover({
        //title: '<h6>Help for Terrain settings:</h6>',
        content: 'Click on the Terrain settings label to expand or compact this section. <br> \
                  Terrain settings define the type and appearance of the gray hillshade overlay.\
                  You can change the type of the Google map (Streetmap, Terrain, Satellite) via its upper left corner.<br>',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });

    $('#elevation_data_source_popover').popover({
        //title: '<h6>Help for Elevation data source:</h6>',
        content: ' Elevation data source defines which DEM (Digital Elevation Model) will be used and at what resolution.\
                   The highest resolution DEM, the 10m USGS/NED DEM, is only available for the lower 48 US states. Outside the US,\
                   use AW3D30 (30m resolution). For more info on the current DEM source, click on the (DEM info) link.\
                   The current DEM will appear as a gray hillshade (relief) layer overlaying the Google Map.',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'left'
    });
    $('#transparency_popover').popover({
        //title: '<h6>Help for Transparency:</h6>',
        content: 'This slider sets the transparency of the gray hillshade overlay. Full transparency (full right) completely hides the hillshade,\
                  completely to the left, completely hides the Google Map.',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });
 
    $('#gamma_popover').popover({
        content: 'Gamma (default 1.0) can be used to change contrast and brightness of the hillshade overlay \
                  Gamma > 1.0 will brighten, Gamma < 1.0 will darken the overlay. To set the gamma value directly, \
                  type in your new value and hit Enter. Note, however, that setting a sun angle will automatically set a gamma value in order\
                  to account for illumination differences.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });
    
    $('#sun_direction_popover').popover({
        content: 'Hillshading is based on rays from a virtual sun illuminating the terrain. Sun direction defines at which compass heading (0 - 360) the sun sits\
                  on the horizon (default: North-West). Changing the direction can be useful to better illuminate directional slope patterns\
                  e.g. sun shining from the North will accentuate East-West stretching hills. Note that some directions, especially sun from the South,\
                  can lead to hills and valleys appearing inverted!',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });

    $('#sun_angle_popover').popover({
        content: 'Hillshading is based on rays from a virtual sun illuminating the terrain. Sun angle defines the vertical angle of the sun above the horizon \
                  (default: 45 degr.). Lower sun angles can be useful to better illuminate low relief areas, such as river deltas. \
                  Note that changing sun angle adjusts the gamma value to counteract the darkening effect of lower angles.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });

    $('#area_selection_box_popover').popover({
        content: 'Click on the Area Selection Box label to expand or compact this section. <br> \
                  This section deals with selecting the area to be printed, shown by the red box inside the Google Map.\
                  <br>If you don\'t see a red box, click on the blue button to the right (Re-center box on map).<br> Drag the box around and\
                  adjust the sides and corners to your liking.<a href="https://iastate.box.com/s/r7jzwoqfv75f1kok4t81cxrjx64p52bg" target="_blank">(video)</a><br>\
                  You can also type in the lat./long. coordinates of the top-right and\
                  bottom-left corners of the box.<a href="https://iastate.box.com/s/pg6xwp92jynvhb439vevi4he0cminom6" target="_blank">(video)</a><br>\
                  Or, you can upload Google Earth kml/kmz files with a single polygon to define the boundary of your print area. \
                  The polygon will be shown in yellow with the re box wrapped around it.<a href="https://iastate.box.com/s/qbs56sh0grboq7nxyg19ixj20m4p4i6o" target="_blank">(video)</a>',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'right'
    });

    $('#3D_printer_options_popover').popover({
        content: 'Click on the 3D printer options label to expand or compact this section. <br> \
                  This section defines specific parameters for your model, such as its  physical dimensions.\
                  This works best if you know a bit about the 3D printer, such as the width and height of the printer\'s\
                  buildplate to help you decide the maximum size of the terrain model it can print.<br>\
                  A a minimum you only need to set the size, however, you should also look at the z-scale.<br>\
                  Once values are set, hit the green Export button below to download your model.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'right'
    });

    $('#3D_printer_CNC_options_popover').popover({
        content: 'Some tips for CNC users: <br> \
                  For model size (Width, Height) and Nozzle diameter (below), select from the CNC presets.\
                  These should give you a reasonable overall level of detail for your model, but verify this with the Preview.<br>\
                  If the Effective DEM Resolution field turn yellow, lower either your size or detail.<br>\
                  Leave all other 3D printer options at their defaults.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'right'
    });

    $('#tile_width_popover').popover({
        content: 'This defines the desired size for your 3D terrain model in mm. <a href="https://iastate.box.com/s/0gid32di66grinm85pj2733fnmx16f5l" target="_blank">(video)</a>\
                  You only need to set the width (corresponding to the East/West\
                  extent of your box), the height (North-South extent) will be calculated automatically. Ensure that your model fits within the dimensions of\
                  your 3D printer\'s buildplate. If you are subdividing your model into multiple tiles, each tile will be of the size set here.<br>',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'right'
    });

    $('#print_resolution_popover').popover({
        content: 'This value defines how much detail your terrain model can contain. 3D printed terrain models are essentially limited by the size of the\
                  nozzle used by your 3D printer (typically 0.4 mm diameter). Adjust this value if you are using a different nozzle size. \
                  Setting it to an artificially smaller value may improve some prints marginally. If you run into server limitations, \
                  increase the nozzle size.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });

    $('#tile_config_popover').popover({
        content: 'If you want to print out a terrain model at a larger size than your buildplate permits, you can subdivide it into smaller parts (tiles)\
                  <a href="https://iastate.box.com/s/ccem0equbdmzvz1v9oimujqa7c7cfv1el" target="_blank">(video)</a>. Set the number of subdivions\
                  in the x and y direction here, which will be shown inside your box.<br>\
                  Each tile will be of the size defined under Width/Height (see above).',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });
    
    $('#effective_resolution_popover').popover({
        content: 'This value indicates to which (effective) resolution the DEM will be down-sampled to from it\'s original resolution. Depending\
                  on the width and nozzle size, this value will typically be considerably larger than the original resolution.<br>\
                  However, if this field turns yellow, you should increase the nozzle size a bit, otherwise you\'re oversampling the DEM, \
                  which is pointless.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });

    $('#base_thickness_popover').popover({
        content: 'This value defines how thick a base will be placed beneath the actual terrain model.\
                  <a href="https://iastate.box.com/s/rcg8b1ttsjy09tdoe3hxxk1tc9q8oi22" target="_blank">(video)</a>',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });
    
    $('#zscale_popover').popover({
        content: 'This value defines if the terrain should be artificially exaggerated (scaled). The default (x 1.0) performs no exaggeration and is\
                  fine for mountainous terrain. Larger z-scale values are recommended if the terrain does not have a lot of relief. \
                  <a href="https://iastate.box.com/s/vakstntrd80oxmgfa83mq0tjg52kgbsg" target="_blank">(video)</a>.<br>\
                  Instead of setting an explicit z-scale value, you can also request your model to be scaled automatically to a certain\
                  height ("tallness"), which is the z-distance (in mm or inches) from the lowest to the highest elevation on you model.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });
    
    $('#fileformat_popover').popover({
        content: 'This selects the mesh file format (type) in which you model will be saved as. STLb (binary STL) is recommended.\
                  Use OBJ if you plan to use the terrain with 3D modeling software.',  
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });

    $('#manual_settings_popover').popover({
        content: 'This field can be used to enter expert options or to override GUI settings via JSON format.\
                  <a href="https://github.com/ChHarding/TouchTerrain_for_CAGEO#processing-parameters" target="_blank">(reference))</a>\
                  <br>Examples: <ul>\
                  <li>\"zscale\":4.5 - overwrites the z-scale with a non-GUI value of 4.5</li>\
                  <li>\"smooth_borders\":false - prevents the smoothing of polygon borders (default: true)</li>\
                  <li>\"lower_leq\":[0,2] - lowers elevations <= 0 by 2m, useful to emphasize shorelines\
                  </ul>\
                  Separate multiple settings with a comma:<br>\"zscale\":4.5, \"smooth_borders\":false, \"lower_leq\":[0,2]',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });

    $('#recenter-box-button').popover({
        content: 'Will place the red print area box at the center of the Google Map',
        html: true,
        trigger: 'hover',
        placement: 'auto',
        delay: { "show": 2000, "hide": 0 },
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
    let topRight = bounds.getNorthEast();  
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
    polygon.setMap(null); // remove polygon
    $('#kml_file_name').html('Optional Polygon KML file: ') // default string
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
    polygon.setMap(null); // remove polygon
    $('#kml_file_name').html('Optional Polygon KML file: ') // default string
  
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
    // -1 print res was removed in 2.5 (as google doesn't let us d/l large geotiffs!) but it could still be come up as a manual option
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

        // warn if current resolution is SMALLER than source resolution
        if(cell_resolution_meter < document.getElementById('source_resolution').value){
            document.getElementById('DEMresolution').style.background = "yellow";
        }
        else{
            document.getElementById('DEMresolution').style.background = ""; // default bg
        }
        
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
        case "USGS/NED": res = "10"; break;
        case "NRCan/CDEM": res = "20"; break;
        case "AU/GA/AUSTRALIA_5M_DEM": res = "5"; break;
        case "USGS/SRTMGL1_003": res = "30"; break;
        case "MERIT/DEM/v1_0_3": res= "90"; break;
        case "JAXA/ALOS/AW3D30/V2_2": res = "30"; break;
        case "USGS/GMTED2010": res = "230"; break;
        case "USGS/GTOPO30" : res = "1000"; break;
        case "CPOM/CryoSat2/ANTARCTICA_DEM" : res = "1000"; break;
        case "NOAA/NGDC/ETOPO1": res = "2000"; break;
    }
    
    // set resolution of DEM source
    document.getElementById('source_resolution').value = parseInt(res);
    document.getElementById('source_resolution').innerHTML = res + " m";
}


// set opacity of hillshade as inverse of transparency given
function updateTransparency(transparency_pct) {
    let op = 1.0 - transparency_pct / 100.0 // opacity
    map.overlayMapTypes.getAt(0).setOpacity(op)
    document.getElementById('hillshade_transparency_slider').value=transparency_pct;
    document.getElementById('transp').value=transparency_pct; // id in hidden reload 1
    document.getElementById('transp3').value=transparency_pct; // id in hidden reload 2
}

//Update gamma in both places
function updateGamma(val) {
    document.getElementById('gamma').value=val;  // id in reload form 1 (hidden)
    document.getElementById('gamma2').value=val; // gui text field
    document.getElementById('gamma3').value=val; // id in reload form 2 (hidden)
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

    // in hidden form 2
    document.getElementById('tilewidth').value = document.getElementById('options_tile_width').value;
    document.getElementById('ntilesx').value = document.getElementById('options_numTiles_x').value;
    document.getElementById('ntilesy').value = document.getElementById('options_numTiles_y').value;
    document.getElementById('printres').value = document.getElementById('options_print_resolution').value;
    document.getElementById('basethick').value = document.getElementById('options_base_thickness').value;
    document.getElementById('zscale').value = document.getElementById('options_z_scale').value;
    document.getElementById('fileformat').value= document.getElementById('options_fileformat').value;
    document.getElementById('manual').value= document.getElementById('options_manual').value;
    document.getElementById('polyURL').value= document.getElementById('options_polyURL').value;

    document.getElementById('maptype3').value = map.getMapTypeId();
    document.getElementById('hsazi3').value = document.getElementById('hsazi2').value;
    document.getElementById('hselev3').value = document.getElementById('hselev2').value;

    // in hidden form 1
    //console.log(map.getMapTypeId());
    //console.log(document.getElementById('hsazi2').value);
    //console.log(document.getElementById('hselev2').value);
    //document.getElementById('maptype').value = map.getMapTypeId();
    document.getElementById('hsazi').value = document.getElementById('hsazi2').value;
    document.getElementById('hselev').value = document.getElementById('hselev2').value;

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
    document.getElementById('warning').value = warning; 
}

// called on idle (after map pan/zoom), sets current lat, lon and zoom
function saveMapSettings(){
    let  c = map.getCenter();
    
    // hidden ids in reloadform 1
    document.getElementById('map_lat').value = c.lat();
    document.getElementById('map_lon').value = c.lng();
    document.getElementById('map_zoom').value = map.getZoom(); 

    // hidden ids in reloadform 1
    document.getElementById('map_lat3').value = c.lat();
    document.getElementById('map_lon3').value = c.lng();
    document.getElementById('map_zoom3').value = map.getZoom(); 
}

// updates hidden fields and submits a form (1 or 2) to the server
// for form 1, trans_method is GET, for form 2 it's POST b/c of the
// file upload, which can't be done via get.
function submit_for_reload(trans_method){

    // check that red box is at least partially visiable, otherwise warn
    const viewport = map.getBounds(); //sw and ne corners
    const vpne = viewport.getNorthEast();
    const vpsw = viewport.getSouthWest();
    const bounds = rectangle.getBounds(); // bounds of red box
    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();

    if(ne.lat() < vpne.lat() && ne.lng() < vpne.lng() &&
       sw.lat() > vpsw.lat() && sw.lng() > vpsw.lng()){
        // fully inside
    }
    else{
        document.getElementById('warning').value = 
                  "Warning: your red area selection box was at least partially outside the \
                  Google Map viewport when you click on Export. This could be OK but maybe \
                  you forgot to click on the Re-center box button?" ;
    }

    saveMapSettings();       // saves map stuff into hidden ids
    update_options_hidden(); // saves more hidden settings

    // trigger a reload with all the vars in reloadform
    let f = document.forms["reloadform"];
    f.method = trans_method;
    
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
            //console.dir(e);
            $('#kml_file_name').html("Error: file could not be parsed!");
            return null;
        }

        let $xml = $(xmlDoc);
        if (typeof xmlDoc === 'undefined'){ /// === means == but w/o implicit type conversion
            $('#kml_file_name').html("Error: file could not be parsed!");
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