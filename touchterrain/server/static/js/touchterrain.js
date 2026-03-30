// TouchTerrain ESRI/Leaflet version
// Migrated from Google Maps to Leaflet + ESRI basemaps

//
// GLOBALS - Template variables are defined in index.html script block
// These are the runtime variables used by the application
//
let map = null; // Leaflet map object
let rectangle = null;  // red box
let polygon = null;    // yellow polygon from kml
let div_lines_x = [];
let div_lines_y = [];
let marker = null;     // search result marker
let overlay = null;    // DEM overlay layer
let basemap_layer = null; // current basemap layer
let current_basemap = 'NationalGeographic';
let corner_handles = []; // custom corner drag handles (NE/NW/SE/SW)
let edge_handles = [];   // custom edge-midpoint drag handles (N/S/E/W)
let _drag_anchor_ll = null; // anchor latlng (opposite corner) during corner drag
let _drag_anchor_px = null; // anchor pixel position during corner drag
let _drag_ratio_px  = null; // pixel width/height ratio for Shift+constrained drag
let _shift_held = false;    // true while Shift key is physically held down
window.addEventListener('keydown', function(e) { if (e.key === 'Shift') _shift_held = true;  });
window.addEventListener('keyup',   function(e) { if (e.key === 'Shift') _shift_held = false; });

function getById(id) {
    return document.getElementById(id);
}

//
// MAP INITIALIZATION AND SETUP
//
window.onload = function () {
    
    // Initialize Leaflet map with ESRI basemap
    map = L.map('map', {
        center: [map_lat, map_lon],
        zoom: map_zoom,
        boxZoom: false,         // disable Shift+drag box-zoom so Shift+corner-drag works
        doubleClickZoom: false
    });

    // Build an ESRI tile URL for the given service name.
    // Use L.esri.basemapLayer so esri-leaflet handles raster vs vector tiles and
    // token passing automatically for both the public CDN and the authenticated
    // Location Platform CDN.
    var _esriBasemapOpts = window.ESRI_API_KEY ? { token: window.ESRI_API_KEY } : {};

    // Add ESRI National Geographic layer as default
    basemap_layer = L.esri.basemapLayer('NationalGeographic', _esriBasemapOpts).addTo(map);

    // Add basemap selector dropdown control
    L.Control.BasemapSwitcher = L.Control.extend({
        onAdd: function(map) {
            let div = L.DomUtil.create('div', 'basemap-switcher');
            div.innerHTML =
                '<select id="basemap-select" class="basemap-select">'
              + '<option value="NationalGeographic" selected>National Geographic</option>'
              + '<option value="ImageryClarity">Satellite</option>'
              + '<option value="Streets">Streets</option>'
              + '<option value="Topographic">Topographic</option>'
              + '</select>';
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            return div;
        }
    });

    L.control.basemapSwitcher = function(opts) {
        return new L.Control.BasemapSwitcher(opts);
    }

    L.control.basemapSwitcher({ position: 'topleft' }).addTo(map);

    // Scale bar (metric + imperial)
    L.control.scale({ position: 'bottomleft', imperial: true, metric: true }).addTo(map);

    // Mouse position (lat/lon display)
    L.control.mousePosition({ position: 'bottomright', numDigits: 4, prefix: 'Lat/Lon:&nbsp;' }).addTo(map);

    // Basemap select event handler
    setTimeout(function() {
        let sel = document.getElementById('basemap-select');
        if (sel) {
            sel.addEventListener('change', function() {
                switchBasemap(this.value);
            });
        }
    }, 500);

    // Initialize search with ESRI geocoder
    const searchControl = L.esri.Geocoding.geosearch({
        position: 'topleft',
        placeholder: 'Search for a place',
        useMapBounds: false,
        providers: [L.esri.Geocoding.arcgisOnlineProvider({
            apikey: window.ESRI_API_KEY || ''
        })],
        collapseAfterResult: false,
        expanded: true,
        allowMultipleResults: false
    }).addTo(map);

    // Create marker for search results; hide pin when its popup is closed
    marker = L.marker([0, 0], { opacity: 0 }).addTo(map);
    marker.on('popupclose', function() {
        marker.setOpacity(0);
    });

    // Handle search results
    searchControl.on('results', function(data) {
        if (data.results && data.results.length > 0) {
            const result = data.results[0];
            const latlng = result.latlng;
            
            // Move map to location
            map.setView(latlng, 13);
            
            // Show marker
            marker.setLatLng(latlng);
            marker.setOpacity(1);
            marker.bindPopup(result.text).openPopup();
            
            // Track with Google Analytics if available
            if (typeof gtag === "function") {
                gtag('event', 'Placename', {
                    'event_category': 'SearchBoxText',
                    'event_label': result.text,
                    'value': '1',
                    'nonInteraction': true
                });
            }
            
            // Update hidden field
            document.getElementById('place').value = result.text;
            
            // Center print area box on result
            center_rectangle();
        }
    });

    // Initialize Earth Engine if MAPID is available
    if (MAPID && MAPID !== "None") {
        overlay = create_overlay(MAPID, map);
        overlay.setOpacity(1.0 - transp / 100.0);
    }

    // Create the red bounding box rectangle
    let bounds = L.latLngBounds(
        L.latLng(bllat, bllon),
        L.latLng(trlat, trlon)
    );
    
    rectangle = L.rectangle(bounds, {
        color: '#FF0000',
        weight: 2,
        fill: true,
        fillOpacity: 0.001   // near-zero but non-false so SVG interior is hit-testable
    }).addTo(map);
    // No enableEdit() — all handles are custom markers via create_corner_handles / create_edge_handles

    // Allow dragging inside the rectangle to move (translate) the whole box
    (function() {
        let el = rectangle.getElement();
        if (!el) return;
        el.style.cursor = 'move';

        el.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();

            let rect    = map.getContainer().getBoundingClientRect();
            let startPx = L.point(e.clientX - rect.left, e.clientY - rect.top);
            let startLL = map.containerPointToLatLng(startPx);
            let startBounds = rectangle.getBounds();
            let startNE = startBounds.getNorthEast();
            let startSW = startBounds.getSouthWest();

            map.dragging.disable();
            map.getContainer().classList.add('editing-active');

            function onMouseMove(ev) {
                let rect2   = map.getContainer().getBoundingClientRect();
                let curPx   = L.point(ev.clientX - rect2.left, ev.clientY - rect2.top);
                let curLL   = map.containerPointToLatLng(curPx);
                let dlat    = curLL.lat - startLL.lat;
                let dlng    = curLL.lng - startLL.lng;
                rectangle.setBounds(L.latLngBounds(
                    L.latLng(startSW.lat + dlat, startSW.lng + dlng),
                    L.latLng(startNE.lat + dlat, startNE.lng + dlng)
                ));
                update_fields_live();
            }
            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup',   onMouseUp);
                map.dragging.enable();
                map.getContainer().classList.remove('editing-active');
                create_corner_handles();
                create_edge_handles();
                update_corners_form();
            }
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup',   onMouseUp);
        });
    })();

    // Create polygon for KML display (initially empty)
    polygon = L.polygon([], {
        color: '#FFFF00',
        weight: 2,
        fillOpacity: 0.1
    });

    // Center the selection box on first load — also creates corner + edge handles
    center_rectangle();

    // Map events
    map.on('moveend', saveMapSettings);
    map.on('zoomend', saveMapSettings);

    // Initialize form values
    update_corners_form();
    SetDEM_name();
    init_print_options();
    create_divison_lines();

    // Button event handlers
    const recenterBtn = getById("recenter-box-button");
    if (recenterBtn) {
        recenterBtn.onclick = center_rectangle;
    }
    
    // Handle update box button
    const updateBoxBtn = getById("options_update_box_button");
    if (updateBoxBtn) {
        updateBoxBtn.onclick = update_box;
    }
    
    // Tile configuration changes
    const numTilesX = getById("options_numTiles_x");
    if (numTilesX) {
        numTilesX.onchange = function() {
        calcTileHeight();
        create_divison_lines();
        setApproxDEMResolution_meters();
        };
    }
    
    const numTilesY = getById("options_numTiles_y");
    if (numTilesY) {
        numTilesY.onchange = function() {
        calcTileHeight();
        create_divison_lines();
        };
    }
    
    // Print resolution changes
    const printResolution = getById("options_print_resolution");
    if (printResolution) {
        printResolution.onchange = function() {
        setApproxDEMResolution_meters();
        };
    }
    
    const tileWidth = getById("options_tile_width");
    if (tileWidth) {
        tileWidth.onchange = function() {
        calcTileHeight();
        setApproxDEMResolution_meters();
        };
    }

    // Handle scale slider
    const scaleSlider = getById("scale");
    if (scaleSlider) {
        scaleSlider.onchange = function() {
        scale_box(this.value);
        };
    }

    // Handle KML file upload
    const fileInput = getById("kml_file");
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
      if (fileInput.files.length > 0) {
        let file = fileInput.files[0];
        
        // process kml file
        if(file.name.endsWith(".kml")){
            const reader = new FileReader();
            reader.onload = function(e) {
                const [bbox, latloncoords] = processKMLFile(e.target.result);
                if(!!bbox){ // not null => valid bounding box
                    rectangle.setBounds(bbox);
                    create_corner_handles();
                    create_edge_handles();
                    update_corners_form();
                    map.fitBounds(bbox);
                    polygon.setLatLngs(latloncoords);
                    polygon.addTo(map);
                    fileInput.name = "kml_file";
                    $('#kml_file_name').html(file.name);
                }else{
                    $('#kml_file_name').html("Error: " + file.name + " not a valid kml file!");
                    fileInput.name.value = null;
                    polygon.remove();
                }
            }
            reader.readAsText(file);
        }
      
        // unzip kmz file into kml first
        else if(file.name.endsWith(".kmz")){
            const reader = new zip.ZipReader(new zip.BlobReader(file));
            const entries = reader.getEntries();
            reader.getEntries().then(function(entries){
                if (entries.length) {
                    const text = entries[0].getData(
                        new zip.TextWriter()
                    ).then(function(text) {
                        const [bbox, latloncoords] = processKMLFile(text);
                        if(!!bbox){
                            rectangle.setBounds(bbox);
                            create_corner_handles();
                            create_edge_handles();
                            update_corners_form();
                            map.fitBounds(bbox);
                            polygon.setLatLngs(latloncoords);
                            polygon.addTo(map);
                            fileInput.name = "kml_file";
                            $('#kml_file_name').html(file.name);
                        }else{
                            $('#kml_file_name').html("Error: " + file.name + " not a valid kmz file!")
                            fileInput.name.value = null
                            polygon.remove();
                        }
                    });
                }
            })
        }
        else{
            $('#kml_file_name').html("Error: " + file.name + " not a valid kml/kmz file!")
            fileInput.name.value = null
            polygon.remove();
        }
      }
        });
    }

    // Help popovers (keeping all existing popover code)
    $('#Whats_new__popover').popover({
        content: 'Mouse over the question marks to see the help text or click on it to toggle the text on/off<br><br>\
                  New in 3.6: Added Colab notebook support, the easiest way to <a href="http://colab.research.google.com/github/ChHarding/TouchTerrain_for_CAGEO/blob/master/TouchTerrain_jupyter_starters_colab.ipynb"  target="_blank"> run TouchTerrain standalone!</a><br>\
                  New in 3.5: large processing jobs should no longer time out. Simplified bottom.<br>\
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
        content: 'Click on the Terrain settings label to expand or compact this section. <br> \
                  Terrain settings define the type and appearance of the gray hillshade overlay.\
                  You can change the type of the basemap (Street Map, Satellite) via the toggle button.<br>',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'auto'
    });

    $('#elevation_data_source_popover').popover({
        content: ' Elevation data source defines which DEM (Digital Elevation Model) will be used and at what resolution.\
                   The highest resolution DEM, the 10m USGS/3DEP/10m DEM, is only available for the lower 48 US states. Outside the US,\
                   use AW3D30 (30m resolution). For more info on the current DEM source, click on the (DEM info) link.\
                   The current DEM will appear as a gray hillshade (relief) layer overlaying the basemap.',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'left'
    });
    
    $('#transparency_popover').popover({
        content: 'This slider sets the transparency of the gray hillshade overlay. Full transparency (full right) completely hides the hillshade,\
                  completely to the left, completely hides the basemap.',
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
                  This section deals with selecting the area to be printed, shown by the red box inside the map.\
                  <br>If you don\'t see a red box, click on the blue button to the right (Re-center box on map).<br> Drag the box around and\
                  adjust the sides and corners to your liking.<a href="https://iastate.box.com/s/r7jzwoqfv75f1kok4t81cxrjx64p52bg" target="_blank">(video)</a><br>\
                  You can also type in the lat./long. coordinates of the top-right and\
                  bottom-left corners of the box.<a href="https://iastate.box.com/s/pg6xwp92jynvhb439vevi4he0cminom6" target="_blank">(video)</a><br>\
                  Or, you can upload Google Earth kml/kmz files with a single polygon to define the boundary of your print area. \
                  The polygon will be shown in yellow with the red box wrapped around it.<a href="https://iastate.box.com/s/qbs56sh0grboq7nxyg19ixj20m4p4i6o" target="_blank">(video)</a>',  
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
                  <a href="https://iastate.box.com/s/ccem0equbdmzvz1v9oimujqa7c7cfv1e" target="_blank">(video)</a>. Set the number of subdivions\
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
                  <li>"zscale":4.5 - overwrites the z-scale with a non-GUI value of 4.5</li>\
                  <li>"smooth_borders":false - prevents the smoothing of polygon borders (default: true)</li>\
                  <li>"lower_leq":[0,2] - lowers elevations <= 0 by 2m, useful to emphasize shorelines\
                  </ul>\
                  Separate multiple settings with a comma:<br>"zscale":4.5, "smooth_borders":false, "lower_leq":[0,2]',
        html: true,
        trigger: 'click hover',
        delay: { "show": 500, "hide": 0 },
        placement: 'top'
    });

    $('#recenter-box-button').popover({
        content: 'Will place the red print area box at the center of the map',
        html: true,
        trigger: 'hover',
        placement: 'auto',
        delay: { "show": 2000, "hide": 0 },
    });
    
}; // end of window.onload()


//
// HELPER FUNCTIONS
//

// Switch to a named ESRI basemap
function switchBasemap(esriName) {
    if (esriName === current_basemap) return;
    map.removeLayer(basemap_layer);
    var _esriBasemapOpts = window.ESRI_API_KEY ? { token: window.ESRI_API_KEY } : {};
    basemap_layer = L.esri.basemapLayer(esriName, _esriBasemapOpts).addTo(map);
    current_basemap = esriName;
    if (overlay) overlay.bringToFront();
}

// Helper: update all 8 form fields from current rectangle bounds (no division lines)
function update_fields_live() {
    let nb = rectangle.getBounds();
    document.getElementById('trlat2').value = nb.getNorthEast().lat;
    document.getElementById('trlon2').value = nb.getNorthEast().lng;
    document.getElementById('bllat2').value = nb.getSouthWest().lat;
    document.getElementById('bllon2').value = nb.getSouthWest().lng;
    document.getElementById('trlat').value  = nb.getNorthEast().lat;
    document.getElementById('trlon').value  = nb.getNorthEast().lng;
    document.getElementById('bllat').value  = nb.getSouthWest().lat;
    document.getElementById('bllon').value  = nb.getSouthWest().lng;
}

// Helper: attach raw mousedown→mousemove/mouseup drag to a marker element.
// onMove(mapPoint) is called each mousemove; onDone() is called on mouseup.
function attach_raw_drag(markerEl, onMove, onDone) {
    markerEl.style.cursor = 'crosshair';
    markerEl.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        map.dragging.disable();
        map.getContainer().classList.add('editing-active');

        function onMouseMove(ev) {
            let rect = map.getContainer().getBoundingClientRect();
            let px = L.point(ev.clientX - rect.left, ev.clientY - rect.top);
            onMove(px);
        }
        function onMouseUp() {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup',   onMouseUp);
            map.dragging.enable();
            map.getContainer().classList.remove('editing-active');
            onDone();
        }
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup',   onMouseUp);
    });
}

// Remove and recreate corner handles (NE/NW/SE/SW)
function remove_corner_handles() {
    corner_handles.forEach(function(h) { h.remove(); });
    corner_handles = [];
}

function create_corner_handles() {
    remove_corner_handles();
    let b = rectangle.getBounds();
    let ne = b.getNorthEast();
    let sw = b.getSouthWest();

    const cornerIcon = L.divIcon({
        className: 'leaflet-vertex-icon',
        iconSize:   [12, 12],
        iconAnchor: [6,  6]
    });

    const cornerDefs = [
        { id: 'NE', latlng: L.latLng(ne.lat, ne.lng) },
        { id: 'NW', latlng: L.latLng(ne.lat, sw.lng) },
        { id: 'SE', latlng: L.latLng(sw.lat, ne.lng) },
        { id: 'SW', latlng: L.latLng(sw.lat, sw.lng) }
    ];

    cornerDefs.forEach(function(def) {
        // draggable:false — we handle all dragging via raw DOM events
        let h = L.marker(def.latlng, { icon: cornerIcon, draggable: false }).addTo(map);
        h._cornerId = def.id;

        // getElement() is valid immediately after addTo(map) — no need for 'add' event
        let el = h.getElement();
        if (!el) return;

        // Record anchor + ratio on mousedown (capture phase — runs before attach_raw_drag)
        el.addEventListener('mousedown', function() {
            let b = rectangle.getBounds();
            let ne = b.getNorthEast(), sw = b.getSouthWest();
            switch (h._cornerId) {
                case 'NE': _drag_anchor_ll = L.latLng(sw.lat, sw.lng); break;
                case 'SW': _drag_anchor_ll = L.latLng(ne.lat, ne.lng); break;
                case 'NW': _drag_anchor_ll = L.latLng(sw.lat, ne.lng); break;
                case 'SE': _drag_anchor_ll = L.latLng(ne.lat, sw.lng); break;
            }
            _drag_anchor_px = map.latLngToContainerPoint(_drag_anchor_ll);
            let selfPx = map.latLngToContainerPoint(h.getLatLng());
            let dx = Math.abs(selfPx.x - _drag_anchor_px.x);
            let dy = Math.abs(selfPx.y - _drag_anchor_px.y);
            _drag_ratio_px = dy < 1 ? 1 : dx / dy;
        }, true);

        attach_raw_drag(el,
            function onMove(px) {
                let ll = map.containerPointToLatLng(px);

                // Shift: constrain to original pixel aspect ratio
                if (_shift_held && _drag_anchor_px && _drag_ratio_px) {
                    let dx = px.x - _drag_anchor_px.x;
                    let dy = px.y - _drag_anchor_px.y;
                    if (Math.abs(dx) > 0.5 && Math.abs(dy) > 0.5) {
                        if (Math.abs(dx / dy) > _drag_ratio_px) {
                            dy = (dy < 0 ? -1 : 1) * Math.abs(dx) / _drag_ratio_px;
                        } else {
                            dx = (dx < 0 ? -1 : 1) * Math.abs(dy) * _drag_ratio_px;
                        }
                        ll = map.containerPointToLatLng(
                            L.point(_drag_anchor_px.x + dx, _drag_anchor_px.y + dy));
                    }
                }
                rectangle.setBounds(L.latLngBounds(_drag_anchor_ll, ll));
                update_fields_live();
            },
            function onDone() {
                create_corner_handles();
                create_edge_handles();
                update_corners_form();
            }
        );

        corner_handles.push(h);
    });
}

// Remove all custom edge handles
function remove_edge_handles() {
    edge_handles.forEach(function(h) { h.remove(); });
    edge_handles = [];
}

// Create custom N/S/E/W edge-midpoint drag handles.
function create_edge_handles() {
    remove_edge_handles();
    let b = rectangle.getBounds();
    let ne = b.getNorthEast();
    let sw = b.getSouthWest();
    let midLat = (ne.lat + sw.lat) / 2;
    let midLng = (ne.lng + sw.lng) / 2;

    const edgeIcon = L.divIcon({
        className: 'leaflet-middle-icon',
        iconSize:   [12, 12],
        iconAnchor: [6,  6]
    });

    const edgeDefs = [
        { id: 'N', latlng: L.latLng(ne.lat,  midLng) },
        { id: 'S', latlng: L.latLng(sw.lat,  midLng) },
        { id: 'E', latlng: L.latLng(midLat,  ne.lng) },
        { id: 'W', latlng: L.latLng(midLat,  sw.lng) }
    ];

    edgeDefs.forEach(function(def) {
        let h = L.marker(def.latlng, { icon: edgeIcon, draggable: false }).addTo(map);
        h._edgeId = def.id;

        // getElement() is valid immediately after addTo(map) — no need for 'add' event
        let el = h.getElement();
        if (!el) return;
        let edgeId = h._edgeId;

        attach_raw_drag(el,
            function onMove(px) {
                let ll = map.containerPointToLatLng(px);
                let cb = rectangle.getBounds();
                let cne = cb.getNorthEast(), csw = cb.getSouthWest();
                let newBounds;
                switch (edgeId) {
                    case 'N': newBounds = L.latLngBounds(csw, L.latLng(ll.lat, cne.lng)); break;
                    case 'S': newBounds = L.latLngBounds(L.latLng(ll.lat, csw.lng), cne); break;
                    case 'E': newBounds = L.latLngBounds(csw, L.latLng(cne.lat, ll.lng)); break;
                    case 'W': newBounds = L.latLngBounds(L.latLng(csw.lat, ll.lng), cne); break;
                }
                rectangle.setBounds(newBounds);
                update_fields_live();
            },
            function onDone() {
                create_corner_handles();
                create_edge_handles();
                update_corners_form();
            }
        );

        edge_handles.push(h);
    });
}

// Create an Earth Engine tile layer using the MapID
function create_overlay(MAPID, map) {
    const EE_MAP_PATH = 'https://earthengine.googleapis.com/v1';
    
    const overlay = L.tileLayer(`${EE_MAP_PATH}/${MAPID}/tiles/{z}/{x}/{y}`, {
        attribution: 'Google Earth Engine',
        opacity: 0.8
    });
    
    overlay.addTo(map);
    return overlay;
}

// Function to return an arc-degree distance in meters at a given latitude
function arcDegr_in_meter(latitude_in_degr) {
    let lat = (2.0 * Math.PI)/360.0 * latitude_in_degr;
    let m1 = 111132.954;
    let m2 = -559.822;
    let m3 = 1.175;
    let m4 = -0.0023;
    let p1 = 111412.84;
    let p2 = -93.5;
    let p3 = 0.118;

    let latlen = m1 + (m2 * Math.cos(2 * lat)) + (m3 * Math.cos(4 * lat)) + (m4 * Math.cos(6 * lat));
    let longlen = (p1 * Math.cos(lat)) + (p2 * Math.cos(3 * lat)) + (p3 * Math.cos(5 * lat));
    return [latlen, longlen];
}

// Create a centered LatLngBounds box
function make_center_box() {
    let bounds = map.getBounds();
    let topRight = bounds.getNorthEast();  
    let bottomLeft = bounds.getSouthWest();
    let c = bounds.getCenter();
    let cx = c.lng;
    let cy = c.lat;
    let nex = topRight.lng;
    let ney = topRight.lat;
    let swx = bottomLeft.lng;
    let swy = bottomLeft.lat;

    let box_size_x = (nex - swx) / 3.0;
    let box_size_y = (ney - swy) / 3.0;

    let box = L.latLngBounds(
        L.latLng(cy - box_size_y, cx - box_size_x),
        L.latLng(cy + box_size_y, cx + box_size_x)
    );
    return box;
}

// Set bounding box of rectangle so it's centered
function center_rectangle() {
    polygon.remove();
    let box = make_center_box();
    rectangle.setBounds(box);
    create_corner_handles();
    create_edge_handles();
    update_corners_form();
}

// Callback to update corner lat/lon in form to current rectangle
function update_corners_form(event) {
    let b = rectangle.getBounds();
    let trlat = b.getNorthEast().lat;
    let trlon = b.getNorthEast().lng;
    let bllat = b.getSouthWest().lat;
    let bllon = b.getSouthWest().lng;

    // Update GUI values
    document.getElementById('trlat2').value = trlat;
    document.getElementById('trlon2').value = trlon;
    document.getElementById('bllat2').value = bllat;
    document.getElementById('bllon2').value = bllon;

    // Also update hidden id values
    document.getElementById('trlat').value = trlat;
    document.getElementById('trlon').value = trlon;
    document.getElementById('bllat').value = bllat;
    document.getElementById('bllon').value = bllon;

    setApproxDEMResolution_meters();
    calcTileHeight();
    create_divison_lines();
    polygon.remove();
    $('#kml_file_name').html('Optional Polygon KML file: ');
}

// Triggered after manual change of box coords
function update_box(event) {
    // Read values from GUI
    let trlat = document.getElementById('trlat2').value;
    let trlon = document.getElementById('trlon2').value;
    let bllat = document.getElementById('bllat2').value;
    let bllon = document.getElementById('bllon2').value;

    // Update hidden id values
    document.getElementById('trlat').value = trlat;
    document.getElementById('trlon').value = trlon;
    document.getElementById('bllat').value = bllat;
    document.getElementById('bllon').value = bllon;

    // Make new bounds
    let newbounds = L.latLngBounds(
        L.latLng(bllat, bllon),
        L.latLng(trlat, trlon)
    );
    rectangle.setBounds(newbounds);
    create_corner_handles();
    create_edge_handles();
    polygon.remove();
    $('#kml_file_name').html('Optional Polygon KML file: ');
}

// Read corners, scale them by sc and update corners
function scale_box(scale_factor) {
    let sc = Number(scale_factor);

    let b = rectangle.getBounds();
    let n = b.getNorthEast().lat;
    let e = b.getNorthEast().lng;
    let s = b.getSouthWest().lat;
    let w = b.getSouthWest().lng;

    let c = b.getCenter();
    let cx = c.lng;
    let cy = c.lat;
    
    let hwidth = (w - e) / 2.0;
    let hheight = (n - s) / 2.0;

    // Scaled coords
    let esc = cx + (hwidth * sc); 
    let wsc = cx - (hwidth * sc);
    let nsc = cy + (hheight * sc);
    let ssc = cy - (hheight * sc);

    // Update rectangle bounds with new coords
    let bounds_scaled = L.latLngBounds(
        L.latLng(ssc, wsc),
        L.latLng(nsc, esc)
    );

    rectangle.setBounds(bounds_scaled);
    create_corner_handles();
    create_edge_handles();
    update_corners_form();

    document.getElementById('scale').value = "1.0";
}

// Calculate the approximate meter resolution of each pixel
function setApproxDEMResolution_meters() {
    let b = rectangle.getBounds();
    let trlat = b.getNorthEast().lat;
    let trlon = b.getNorthEast().lng;
    let bllat = b.getSouthWest().lat;
    let bllon = b.getSouthWest().lng;
    let print_res_mm = document.getElementById('options_print_resolution').value;

    if(print_res_mm <= 0){
        document.getElementById('DEMresolution').value = 'the same';
    }
    else{
        let tw_mm = document.getElementById('options_tile_width').value;
        let num_tiles_x = document.getElementById('options_numTiles_x').value;
        let num_cells_per_tile = tw_mm / print_res_mm;
        let total_cells = num_cells_per_tile * num_tiles_x;

        let lat_of_center = (trlat + bllat) / 2.0;
        let box_width_in_degr = Math.abs(trlon - bllon);
        let one_degr_in_m = arcDegr_in_meter(lat_of_center)[1];
        let box_width_in_m = box_width_in_degr * one_degr_in_m;

        let cell_resolution_meter = box_width_in_m / total_cells;
        cell_resolution_meter = Math.round(cell_resolution_meter * 100) / 100;
        document.getElementById('DEMresolution').value = cell_resolution_meter;

        if(cell_resolution_meter < document.getElementById('source_resolution').value){
            document.getElementById('DEMresolution').style.background = "yellow";
        }
        else{
            document.getElementById('DEMresolution').style.background = "";
        }
    }
}

function remove_divison_lines() {
    for (let i = 0; i < div_lines_x.length; i++) {
        div_lines_x[i].remove();
    }
    div_lines_x = [];

    for (let i = 0; i < div_lines_y.length; i++) {
        div_lines_y[i].remove();
    }
    div_lines_y = [];
}

function create_divison_lines(event) {
    remove_divison_lines();

    let bounds = rectangle.getBounds();
    let ne = bounds.getNorthEast();
    let sw = bounds.getSouthWest();
    
    // Calculate span manually (Leaflet doesn't have toSpan())
    let span = {
        lat: ne.lat - sw.lat,
        lng: ne.lng - sw.lng
    };

    let num_lines = document.getElementById('options_numTiles_x').value - 1;
    if(num_lines > 0){
        let width = span.lng / (num_lines + 1);
        for (let i = 0; i < num_lines; i++) {
            let x = sw.lng + (i+1) * width;
            let line_coords = [
                [ne.lat, x],
                [sw.lat, x]
            ];
            div_lines_x[i] = L.polyline(line_coords, {
                color: '#FF0000',
                opacity: 1.0,
                weight: 1
            });
            div_lines_x[i].addTo(map);
        }
    }

    num_lines = document.getElementById('options_numTiles_y').value - 1;
    if(num_lines > 0){
        let height = span.lat / (num_lines + 1);
        for (let i = 0; i < num_lines; i++) {
            let y = sw.lat + (i+1) * height;
            let line_coords = [
                [y, sw.lng],
                [y, ne.lng]
            ];
            div_lines_y[i] = L.polyline(line_coords, {
                color: '#FF0000',
                opacity: 1.0,
                weight: 1
            });
            div_lines_y[i].addTo(map);
        }
    }
}

// Update functions, called from HTML
function SetDEM_name() {
    document.getElementById('DEM_name').value = DEM_name;
    document.getElementById('DEM_name2').value = DEM_name;

    let res = "unknown resolution";
    switch(DEM_name){
        case "USGS/3DEP/10m_collection": res = "10"; break;
        case "NRCan/CDEM": res = "20"; break;
        case "AU/GA/AUSTRALIA_5M_DEM": res = "5"; break;
        case "MERIT/DEM/v1_0_3": res = "90"; break;
        case "JAXA/ALOS/AW3D30/V3_2": res = "30"; break;
        case "USGS/GMTED2010": res = "230"; break;
        case "USGS/GTOPO30": res = "1000"; break;
        case "CPOM/CryoSat2/ANTARCTICA_DEM": res = "1000"; break;
        case "NOAA/NGDC/ETOPO1": res = "2000"; break;
        case "IGN/RGE_ALTI/1M/2_0/FXX": res = "1"; break;
        case "UK/EA/ENGLAND_1M_TERRAIN/2022": res = "1"; break;
        case "USGS/3DEP/1m": res = "1"; break;
    }
    
    document.getElementById('source_resolution').value = parseInt(res);
    document.getElementById('source_resolution').innerHTML = res + " m";
}

// Set opacity of hillshade as inverse of transparency given
function updateTransparency(transparency_pct) {
    let op = 1.0 - transparency_pct / 100.0;
    if (overlay) {
        overlay.setOpacity(op);
    }
    document.getElementById('hillshade_transparency_slider').value = transparency_pct;
    document.getElementById('transp').value = transparency_pct;
    document.getElementById('transp3').value = transparency_pct;
}

// Update gamma in both places
function updateGamma(val) {
    document.getElementById('gamma').value = val;
    document.getElementById('gamma2').value = val;
    document.getElementById('gamma3').value = val;
}

// Update hillshade elevation(angle above horizon) and adjust gamma
function updateHillshadeElevation(elev) {
    document.getElementById('hselev').value = elev;
    document.getElementById('hselev2').value = elev;
    switch(Number(elev)) {
        case 55: updateGamma(0.3); break;
        case 45: updateGamma(1.0); break;
        case 35: updateGamma(1.2); break;
        case 25: updateGamma(1.5); break;
        case 10: updateGamma(2.5); break;
        case 5: updateGamma(4.5); break;
        default: alert(elev + " is bad!");
    }
}

// Update the hidden ids in reload form
function update_options_hidden() {
    document.getElementById('tilewidth').value = document.getElementById('options_tile_width').value;
    document.getElementById('ntilesx').value = document.getElementById('options_numTiles_x').value;
    document.getElementById('ntilesy').value = document.getElementById('options_numTiles_y').value;
    document.getElementById('printres').value = document.getElementById('options_print_resolution').value;
    document.getElementById('basethick').value = document.getElementById('options_base_thickness').value;
    document.getElementById('zscale').value = document.getElementById('options_z_scale').value;
    document.getElementById('fileformat').value = document.getElementById('options_fileformat').value;
    document.getElementById('manual').value = document.getElementById('options_manual').value;
    document.getElementById('polyURL').value = document.getElementById('options_polyURL').value;

    document.getElementById('maptype').value = current_basemap;
    document.getElementById('maptype3').value = current_basemap;
    document.getElementById('gamma').value = document.getElementById('gamma2').value;
    document.getElementById('transp').value = document.getElementById('hillshade_transparency_slider').value;
    document.getElementById('hsazi3').value = document.getElementById('hsazi2').value;
    document.getElementById('hselev3').value = document.getElementById('hselev2').value;

    document.getElementById('hsazi').value = document.getElementById('hsazi2').value;
    document.getElementById('hselev').value = document.getElementById('hselev2').value;
}

// Update the print option values in the GUI from the global vars
function init_print_options() {
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

// Called on idle (after map pan/zoom), sets current lat, lon and zoom
function saveMapSettings() {
    let c = map.getCenter();
    
    document.getElementById('map_lat').value = c.lat;
    document.getElementById('map_lon').value = c.lng;
    document.getElementById('map_zoom').value = map.getZoom(); 

    document.getElementById('map_lat3').value = c.lat;
    document.getElementById('map_lon3').value = c.lng;
    document.getElementById('map_zoom3').value = map.getZoom(); 
}

// Updates hidden fields and submits a form
function submit_for_reload(trans_method) {
    const viewport = map.getBounds();
    const vpne = viewport.getNorthEast();
    const vpsw = viewport.getSouthWest();
    const bounds = rectangle.getBounds();
    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();

    if(ne.lat < vpne.lat && ne.lng < vpne.lng &&
       sw.lat > vpsw.lat && sw.lng > vpsw.lng){
        // Fully inside
    }
    else{
        document.getElementById('warning').value = 
            "Warning: your red area selection box was at least partially outside the \
            map viewport when you clicked on Export. This could be OK but maybe \
            you forgot to click on the Re-center box button?";
    }

    saveMapSettings();
    update_options_hidden();

    let f = document.forms["reloadform"];
    f.method = trans_method;
    f.submit();
}

// Calculate tile height from given mm width and red box ratio
function calcTileHeight() {
    let tw = document.getElementById('options_tile_width').value;
    document.getElementById('tilewidth').value = tw;
    let bounds = rectangle.getBounds();
    let n = bounds.getNorthEast().lat;
    let s = bounds.getSouthWest().lat;
    let center_lat = (n + s) / 2.0;
    let degr_in_m = arcDegr_in_meter(center_lat);
    
    // Calculate span manually
    let span_lat = n - s;
    let span_lng = bounds.getNorthEast().lng - bounds.getSouthWest().lng;
    
    let hm = span_lat * degr_in_m[0];
    let wm = span_lng * degr_in_m[1];

    let hw_in_meter_ratio = hm / wm;
    let th = tw * hw_in_meter_ratio;

    let tile_height_rounded = parseInt(th * 10) / 10;
    document.getElementById('options_tile_height').value = th;
    document.getElementById('options_tile_height').innerHTML = tile_height_rounded + "&nbsp mm";
}

// Return bounds of polygon in kml file or null on parse error
function processKMLFile(xmlfile) {
    if (!xmlfile || !xmlfile.length) {
        $('#kml_file_name').html("Error: file is empty or unreadable!");
        return [null, null];
    }
    {
        let xmlDoc = null;
        try {
            xmlDoc = $.parseXML(xmlfile);
        }
        catch(e) {
            $('#kml_file_name').html("Error: file could not be parsed!");
            return [null, null];
        }

        let $xml = $(xmlDoc);
        if (typeof xmlDoc === 'undefined') {
            $('#kml_file_name').html("Error: file could not be parsed!");
            return [null, null];
        } else {
            let coords = $xml.find("coordinates").text();

            coords = coords.replace(/\t/g, '');
            coords = coords.replace(/\n/g, '');
            coords = coords.trim();

            coords = coords.split(" ");

            if (coords.length < 3) {
                alert("Error: KML file does not contain polygon (need >2 coordinates)!");
                return [null, null];
            }

            let xcoords = [];
            let ycoords = [];
            let llcoords = [];
            for (let i=0; i < coords.length; i++) {
                let c = coords[i].split(",");
                xcoords.push(c[0]);
                ycoords.push(c[1]);
                llcoords.push([c[1], c[0]]); // Leaflet uses [lat, lng]
            }

            xcoords = xcoords.map(Number);
            ycoords = ycoords.map(Number);

            let xmax = Math.max(...xcoords);
            let ymax = Math.max(...ycoords);
            let xmin = Math.min(...xcoords);
            let ymin = Math.min(...ycoords);

            let bounds = L.latLngBounds(
                L.latLng(ymin, xmin),
                L.latLng(ymax, xmax)
            );
            
            return [bounds, llcoords];
        }
    }
}
