/**
 * Demandes de liaison Parent-Enfant — onglets statut + filtres (UI v2)
 */

(function () {
  'use strict';

  var TAB_SELECTOR = '.dml-status-tab[data-tab]';
  var PANEL_SELECTOR = '.dml-tabs-content .tab-panel';

  function switchStatusTab(tabId, btn) {
    document.querySelectorAll(PANEL_SELECTOR).forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll(TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');

    var targetBtn = btn || document.querySelector(TAB_SELECTOR + '[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function getPanelId(panelKey) {
    return 'tab-' + panelKey;
  }

  function filterPanelRows(panelKey) {
    var panelId = getPanelId(panelKey);
    var panel = document.getElementById(panelId);
    if (!panel) return;

    var searchInput = panel.querySelector('.dml-search-input[data-panel="' + panelKey + '"]');
    var searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';
    var activeFilterBtn = panel.querySelector('.dml-filter-btn.active[data-panel="' + panelKey + '"]');
    var statusFilter = activeFilterBtn ? (activeFilterBtn.getAttribute('data-filter-status') || 'tous') : 'tous';
    var clearBtn = panel.querySelector('.dml-clear-search[data-panel="' + panelKey + '"]');
    var resultsWrap = panel.querySelector('.dml-filter-results[data-panel="' + panelKey + '"]');
    var resultsCount = panel.querySelector('.dml-results-count[data-panel="' + panelKey + '"]');
    var tbody = panel.querySelector('.dml-table tbody');

    if (clearBtn) clearBtn.hidden = !searchTerm;
    if (!tbody) return;

    var rows = tbody.querySelectorAll('tr[data-statut]');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var rowStatus = row.getAttribute('data-statut') || '';
      var text = row.textContent.toLowerCase();
      var matchesSearch = !searchTerm || text.indexOf(searchTerm) !== -1;
      var matchesStatus = statusFilter === 'tous' || rowStatus === statusFilter;

      if (matchesSearch && matchesStatus) {
        row.classList.remove('dml-row-hidden');
        visibleCount += 1;
      } else {
        row.classList.add('dml-row-hidden');
      }
    });

    if (resultsWrap && resultsCount) {
      var filtering = searchTerm || statusFilter !== 'tous';
      if (filtering) {
        resultsCount.textContent = visibleCount;
        resultsWrap.hidden = false;
      } else {
        resultsWrap.hidden = true;
      }
    }
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest(TAB_SELECTOR);
    if (tabBtn) {
      switchStatusTab(tabBtn.getAttribute('data-tab'), tabBtn);
      return;
    }

    var filterBtn = event.target.closest('.dml-filter-btn[data-panel][data-filter-status]');
    if (filterBtn) {
      var panelKey = filterBtn.getAttribute('data-panel');
      var panel = document.getElementById(getPanelId(panelKey));
      if (panel) {
        panel.querySelectorAll('.dml-filter-btn[data-panel="' + panelKey + '"]').forEach(function (btn) {
          btn.classList.remove('active');
        });
        filterBtn.classList.add('active');
        filterPanelRows(panelKey);
      }
      return;
    }

    var clearBtn = event.target.closest('.dml-clear-search[data-panel]');
    if (clearBtn) {
      var clearPanelKey = clearBtn.getAttribute('data-panel');
      var clearPanel = document.getElementById(getPanelId(clearPanelKey));
      var clearInput = clearPanel ? clearPanel.querySelector('.dml-search-input[data-panel="' + clearPanelKey + '"]') : null;
      if (clearInput) clearInput.value = '';
      filterPanelRows(clearPanelKey);
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.matches('.dml-search-input[data-panel]')) {
      filterPanelRows(event.target.getAttribute('data-panel'));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    ['a-approuver', 'reussies', 'refusees'].forEach(function (panelKey) {
      filterPanelRows(panelKey);
    });

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
