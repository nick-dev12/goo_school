/**
 * Impayés scolarité — onglets classe, recherche, persistance (Vague 5)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:impayes';
  var TAB_SELECTOR = '.imp-classe-tab[data-tab]';

  function persistClasse(classeKey) {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, {
      classe: classeKey || 'tous',
    });
  }

  function switchClassePanel(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.imp-tabs-content .tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll(TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }
    var targetBtn = btn || document.querySelector(TAB_SELECTOR + '[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
      if (!opts.skipPersist) {
        persistClasse(targetBtn.getAttribute('data-classe-key') || 'tous');
      }
    }

    filterRows();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function restoreFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('classe')) {
      var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
      if (stored.classe) {
        params.set('classe', stored.classe);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['classe']);
    var key = params.get('classe') || 'tous';
    var btn = document.querySelector(TAB_SELECTOR + '[data-classe-key="' + CSS.escape(key) + '"]');
    if (btn) {
      switchClassePanel(btn.getAttribute('data-tab'), btn, { skipPersist: true });
      persistClasse(key);
    }
    return false;
  }

  function filterRows() {
    var input = document.getElementById('impSearchInput');
    var term = input ? input.value.trim().toLowerCase() : '';
    var panel = document.querySelector('.imp-tabs-content .tab-panel.active');
    if (!panel) return;

    var rows = panel.querySelectorAll('.imp-table tbody tr');
    var visible = 0;
    rows.forEach(function (row) {
      if (row.querySelector('.imp-empty-row')) return;
      var text = row.textContent.toLowerCase();
      var show = !term || text.indexOf(term) !== -1;
      row.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });

    var emptyFilter = panel.querySelector('.imp-empty-filter');
    if (emptyFilter) {
      emptyFilter.hidden = !term || visible > 0;
    }
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest(TAB_SELECTOR);
    if (tabBtn) {
      switchClassePanel(tabBtn.getAttribute('data-tab'), tabBtn);
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreFromStorage()) return;
    var searchInput = document.getElementById('impSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', filterRows);
    }
    filterRows();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
