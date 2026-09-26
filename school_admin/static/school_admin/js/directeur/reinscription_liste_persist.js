/**
 * Réinscription — persistance recherche / filtre classe (URL + localStorage).
 */
(function () {
  'use strict';
  var KEY = 'directeur:reinscription-filtres';

  function readStored() {
    var params = new URLSearchParams(window.location.search);
    var search = params.get('search') || '';
    var classe = params.get('classe') || '';
    if (!search && !classe) {
      try {
        var stored = JSON.parse(localStorage.getItem(KEY) || 'null');
        if (stored) {
          search = stored.search || '';
          classe = stored.classe || '';
        }
      } catch (err) {
        /* ignore */
      }
    }
    return { search: search, classe: classe };
  }

  function writeStored(search, classe) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ search: search, classe: classe, at: Date.now() }));
    } catch (err) {
      /* ignore */
    }
    var params = new URLSearchParams(window.location.search);
    if (search) params.set('search', search);
    else params.delete('search');
    if (classe) params.set('classe', classe);
    else params.delete('classe');
    var q = params.toString();
    var next = window.location.pathname + (q ? '?' + q : '');
    if (next !== window.location.pathname + window.location.search) {
      history.replaceState(null, '', next);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('form.reinscription-search-form, form#reinscription-search-form');
    if (!form) return;
    var searchInput = form.querySelector('input[name="search"]');
    var classeSelect = form.querySelector('select[name="classe"]');
    var stored = readStored();
    if (stored.search && searchInput && !searchInput.value) {
      searchInput.value = stored.search;
    }
    if (stored.classe && classeSelect && !classeSelect.value) {
      classeSelect.value = stored.classe;
    }
    form.addEventListener('submit', function () {
      writeStored(
        searchInput ? searchInput.value.trim() : '',
        classeSelect ? classeSelect.value : ''
      );
    });
    if (searchInput && classeSelect && (stored.search || stored.classe) && !window.location.search) {
      form.submit();
    } else {
      writeStored(
        searchInput ? searchInput.value.trim() : stored.search,
        classeSelect ? classeSelect.value : stored.classe
      );
    }
  });
})();
