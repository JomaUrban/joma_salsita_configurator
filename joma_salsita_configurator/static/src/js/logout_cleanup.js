// Al cerrar sesión en la web, borra la sesión de cliente del configurador
// Salsita para que el siguiente usuario no herede la identidad anterior.
(function () {
    'use strict';
    var PREFIX = 'joma-customer:configurator-';
    var OWNER_KEY = 'joma-salsita:owner';

    function clear() {
        [window.sessionStorage, window.localStorage].forEach(function (storage) {
            try {
                var keys = [];
                for (var i = 0; i < storage.length; i++) {
                    var key = storage.key(i);
                    if (key && key.indexOf(PREFIX) === 0) {
                        keys.push(key);
                    }
                }
                keys.forEach(function (key) { storage.removeItem(key); });
            } catch (e) { /* almacenamiento no disponible */ }
        });
        try { window.localStorage.removeItem(OWNER_KEY); } catch (e) { /* */ }
    }

    document.addEventListener('click', function (ev) {
        var link = ev.target && ev.target.closest
            ? ev.target.closest('a[href*="/web/session/logout"]') : null;
        if (link) {
            clear();
        }
    }, true);
})();
