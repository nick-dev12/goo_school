/**
 * Cartes d'identité — onglets niveau/classe + overflow + persistance (UI v2.1)
 */
(function () {
  'use strict';

  function setPanelVisible(panel, show) {
    if (!panel) return;
    panel.classList.toggle('active', show);
    panel.hidden = !show;
  }

  window.switchMainTab = function (tabId, btn, opts) {
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
      setPanelVisible(panel, panel.id === tabId);
    });
    document.querySelectorAll('.sci-niveau-tab, .tab-button[data-tab]').forEach(function (b) {
      var active = b.getAttribute('data-tab') === tabId;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    var targetBtn = btn || document.querySelector('[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId, opts) {
    if (event) event.stopPropagation();
    var parentPanel = event && event.target
      ? event.target.closest('.tab-panel')
      : null;
    if (!parentPanel) {
      var content = document.getElementById(classeId);
      parentPanel = content ? content.closest('.tab-panel') : null;
    }
    if (!parentPanel) return;

    parentPanel.querySelectorAll('.classe-subtab-content').forEach(function (el) {
      setPanelVisible(el, el.id === classeId);
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      var active = b.getAttribute('data-subtab') === classeId;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  function filterStudentsCartes(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var clearButton = document.getElementById('clear-search-' + classeId);
    var resultsDiv = document.getElementById('filter-results-' + classeId);
    var resultsCount = document.getElementById('results-count-' + classeId);
    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    if (clearButton) clearButton.hidden = !searchTerm;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;

    var rows = classeContent.querySelectorAll('.list-row');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var matricule = row.dataset.matricule || '';
      var numero = row.dataset.numero || '';
      var matches = !searchTerm ||
        nom.includes(searchTerm) ||
        prenom.includes(searchTerm) ||
        matricule.includes(searchTerm) ||
        numero.includes(searchTerm);
      row.classList.toggle('hidden', !matches);
      if (matches) visibleCount += 1;
    });

    if (resultsDiv && resultsCount) {
      if (searchTerm) {
        resultsCount.textContent = visibleCount;
        resultsDiv.hidden = false;
      } else {
        resultsDiv.hidden = true;
      }
    }
  }

  document.addEventListener('click', function (event) {
    var niveauBtn = event.target.closest('.sci-niveau-tab[data-tab]');
    if (niveauBtn) {
      window.switchMainTab(niveauBtn.getAttribute('data-tab'), niveauBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.matches('.sci-search-input[data-classe-id]')) {
      filterStudentsCartes(event.target.getAttribute('data-classe-id'));
    }
  });

  if (typeof window.enhanceDirecteurNiveauClasseTabs === 'function') {
    window.enhanceDirecteurNiveauClasseTabs({ storageKey: 'directeur:cartes-identite' });
  }
})();
