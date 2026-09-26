/**
 * Hub pages primaire — persistance query + localStorage, overflow, recherche locale.
 */
(function () {
  'use strict';

  function layoutOverflow() {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function initStorage() {
    var body = document.body;
    var key = body.getAttribute('data-prof-hub-key');
    var fieldsRaw = body.getAttribute('data-prof-hub-fields') || 'classe';
    if (!key || !window.professeurTabStorage) {
      return;
    }
    var fields = fieldsRaw.split(',').map(function (s) {
      return s.trim();
    }).filter(Boolean);

    var params = new URLSearchParams(window.location.search);
    var needsMerge = fields.some(function (name) {
      return !params.has(name) || params.get(name) === '';
    });
    if (needsMerge) {
      var stored = window.professeurTabStorage.readStore(key);
      var changed = false;
      fields.forEach(function (name) {
        if ((!params.has(name) || params.get(name) === '') && stored[name]) {
          params.set(name, String(stored[name]));
          changed = true;
        }
      });
      if (changed) {
        window.location.replace(window.location.pathname + '?' + params.toString());
        return;
      }
    }
    window.professeurTabStorage.mergeUrlFromStore(key, fields);
    var values = {};
    fields.forEach(function (name) {
      values[name] = params.get(name) || '';
    });
    window.professeurTabStorage.syncUrlAndStore(key, values);
  }

  function filterSearchRows() {
    var input = document.getElementById('profPrimaireSearchInput');
    if (!input) return;
    var selector = input.getAttribute('data-prof-search-target') || '.prof-primaire-searchable tbody tr';
    var term = input.value.trim().toLowerCase();
    document.querySelectorAll(selector).forEach(function (row) {
      if (row.querySelector('.empty-row')) return;
      var text = row.textContent.toLowerCase();
      row.hidden = term.length > 0 && text.indexOf(term) === -1;
    });
  }

  function activateClassePanels(classeId) {
    if (!classeId) return;
    document.querySelectorAll('[data-classe-panel]').forEach(function (el) {
      var match = el.getAttribute('data-classe-panel') === String(classeId);
      el.classList.toggle('prof-primaire-panel-hidden', !match);
      el.hidden = !match;
    });
    document.querySelectorAll('[data-classe-card-id]').forEach(function (card) {
      card.classList.toggle('prof-classe-active', card.getAttribute('data-classe-card-id') === String(classeId));
    });
    var eleveBtn = document.querySelector('.classe-tab-btn[data-classe-id="' + classeId + '"]');
    if (eleveBtn && typeof window.showClasse === 'function') {
      var panelId = eleveBtn.getAttribute('data-classe');
      var tabId = eleveBtn.closest('.tab-content-panel') && eleveBtn.closest('.tab-content-panel').id;
      if (panelId && tabId) {
        window.showClasse(panelId, tabId);
      }
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initStorage();
    var params = new URLSearchParams(window.location.search);
    var classeId = params.get('classe') || document.body.getAttribute('data-initial-classe') || '';
    activateClassePanels(classeId);
    layoutOverflow();

    document.querySelectorAll('.prof-primaire-tab-link').forEach(function (link) {
      link.addEventListener('click', function () {
        var key = document.body.getAttribute('data-prof-hub-key');
        if (!key || !window.professeurTabStorage) return;
        var fields = (document.body.getAttribute('data-prof-hub-fields') || 'classe').split(',');
        var values = {};
        fields.forEach(function (name) {
          name = name.trim();
          if (!name) return;
          values[name] = new URL(link.href, window.location.origin).searchParams.get(name) || '';
        });
        window.professeurTabStorage.syncUrlAndStore(key, values);
      });
    });

    var searchInput = document.getElementById('profPrimaireSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', filterSearchRows);
    }
    window.addEventListener('resize', layoutOverflow);
  });
})();
