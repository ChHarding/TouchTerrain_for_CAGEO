/* Leaflet.MousePosition - show cursor lat/lon on the map
 * Original: https://github.com/ardhi/Leaflet.MousePosition  (MIT licence)
 */
L.Control.MousePosition = L.Control.extend({
    options: {
        position: 'bottomleft',
        separator: ' : ',
        emptyString: 'Move mouse over map',
        lngFirst: false,
        numDigits: 5,
        lngFormatter: undefined,
        latFormatter: undefined,
        formatter: undefined,
        prefix: '',
        suffix: ''
    },

    onAdd: function (map) {
        this._container = L.DomUtil.create('div', 'leaflet-control-mouseposition');
        L.DomEvent.disableClickPropagation(this._container);
        map.on('mousemove', this._onMouseMove, this);
        this._container.innerHTML = this.options.emptyString;
        return this._container;
    },

    onRemove: function (map) {
        map.off('mousemove', this._onMouseMove, this);
    },

    _onMouseMove: function (e) {
        var lng = this.options.lngFormatter
            ? this.options.lngFormatter(e.latlng.lng)
            : L.Util.formatNum(e.latlng.lng, this.options.numDigits);
        var lat = this.options.latFormatter
            ? this.options.latFormatter(e.latlng.lat)
            : L.Util.formatNum(e.latlng.lat, this.options.numDigits);
        var value = this.options.lngFirst
            ? lng + this.options.separator + lat
            : lat + this.options.separator + lng;
        this._container.innerHTML = this.options.prefix + value + this.options.suffix;
    }
});

L.Map.mergeOptions({ positionControl: false });

L.Map.addInitHook(function () {
    if (this.options.positionControl) {
        this.positionControl = new L.Control.MousePosition();
        this.addControl(this.positionControl);
    }
});

L.control.mousePosition = function (options) {
    return new L.Control.MousePosition(options);
};
