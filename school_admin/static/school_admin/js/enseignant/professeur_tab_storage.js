/**
 * Persistance onglets / filtres espace professeur — query string + localStorage.
 */
(function (global) {
  'use strict';

  function readStore(storageKey) {
    try {
      var raw = global.localStorage.getItem(storageKey);
      return raw ? JSON.parse(raw) : {};
    } catch (err) {
      return {};
    }
  }

  function writeStore(storageKey, values) {
    try {
      global.localStorage.setItem(
        storageKey,
        JSON.stringify(Object.assign({}, values, { at: Date.now() }))
      );
    } catch (err) {
      /* ignore */
    }
  }

  function mergeUrlFromStore(storageKey, fieldNames) {
    var params = new global.URLSearchParams(global.location.search);
    var stored = readStore(storageKey);
    var changed = false;

    fieldNames.forEach(function (name) {
      if (!params.has(name) && stored[name] != null && stored[name] !== '') {
        params.set(name, String(stored[name]));
        changed = true;
      }
    });

    if (changed) {
      var query = params.toString();
      global.history.replaceState(
        null,
        '',
        global.location.pathname + (query ? '?' + query : '') + global.location.hash
      );
    }

    var out = {};
    fieldNames.forEach(function (name) {
      out[name] = params.get(name) || '';
    });
    return out;
  }

  function syncUrlAndStore(storageKey, values) {
    var params = new global.URLSearchParams(global.location.search);
    Object.keys(values).forEach(function (name) {
      var v = values[name];
      if (v != null && v !== '') {
        params.set(name, String(v));
      } else {
        params.delete(name);
      }
    });
    var query = params.toString();
    var next = global.location.pathname + (query ? '?' + query : '') + global.location.hash;
    var current = global.location.pathname + global.location.search + global.location.hash;
    if (next !== current) {
      global.history.replaceState(null, '', next);
    }
    writeStore(storageKey, values);
  }

  global.professeurTabStorage = {
    readStore: readStore,
    writeStore: writeStore,
    mergeUrlFromStore: mergeUrlFromStore,
    syncUrlAndStore: syncUrlAndStore,
  };
})(window);
