/**
 * Scolarité des élèves — navigation, filtres, persistance (UI v2, Vague 5)
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:compta-eleves';

  function persistStatut(classeId, statut) {
    if (!window.directeurTabStorage) return;
    var store = window.directeurTabStorage.readStore(STORAGE_KEY);
    var byClasse = store.statutParClasse && typeof store.statutParClasse === 'object'
      ? store.statutParClasse
      : {};
    if (classeId) {
      byClasse[String(classeId)] = statut || '';
    }
    window.directeurTabStorage.writeStore(STORAGE_KEY, {
      statutParClasse: byClasse,
    });
  }

  window.switchMainTab = function (tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll('.tab-button').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }
    var targetBtn = btn || document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId, opts) {
    opts = opts || {};
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
      el.classList.remove('active');
      el.hidden = true;
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var target = document.getElementById(classeId);
    if (target) {
      target.classList.add('active');
      target.hidden = false;
    }

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  function filterStudentsComptabilite(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var filterStatut = document.getElementById('filter-statut-' + classeId);
    var clearButton = document.getElementById('clear-search-' + classeId);
    var resultsDiv = document.getElementById('filter-results-' + classeId);
    var resultsCount = document.getElementById('results-count-' + classeId);
    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    var statutValue = filterStatut ? filterStatut.value : '';

    if (clearButton) clearButton.hidden = !searchTerm;
    if (filterStatut && statutValue) {
      persistStatut(classeId, statutValue);
    }

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;

    var rows = classeContent.querySelectorAll('.list-row');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var email = row.dataset.email || '';
      var estNonEnRegle = row.getAttribute('data-est-non-en-regle') === 'true';

      var matchesSearch = !searchTerm ||
        nom.includes(searchTerm) ||
        prenom.includes(searchTerm) ||
        email.includes(searchTerm);

      var matchesStatut = true;
      if (statutValue === 'a_jour') matchesStatut = !estNonEnRegle;
      else if (statutValue === 'non_en_regle') matchesStatut = estNonEnRegle;

      if (matchesSearch && matchesStatut) {
        row.classList.remove('hidden');
        visibleCount += 1;
      } else {
        row.classList.add('hidden');
      }
    });

    if (resultsDiv && resultsCount) {
      if (searchTerm || statutValue) {
        resultsCount.textContent = visibleCount;
        resultsDiv.hidden = false;
      } else {
        resultsDiv.hidden = true;
      }
    }
  }

  function clearSearchComptabilite(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    if (searchInput) {
      searchInput.value = '';
      filterStudentsComptabilite(classeId);
    }
  }

  function resetFiltersComptabilite(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var filterStatut = document.getElementById('filter-statut-' + classeId);
    if (searchInput) searchInput.value = '';
    if (filterStatut) filterStatut.value = '';
    persistStatut(classeId, '');
    filterStudentsComptabilite(classeId);
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.tab-button[data-tab]');
    if (tabBtn) {
      window.switchMainTab(tabBtn.getAttribute('data-tab'), tabBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
      return;
    }
    var clearBtn = event.target.closest('[data-clear-search]');
    if (clearBtn) {
      clearSearchComptabilite(clearBtn.getAttribute('data-clear-search'));
      return;
    }
    var resetBtn = event.target.closest('[data-reset-filters]');
    if (resetBtn) {
      resetFiltersComptabilite(resetBtn.getAttribute('data-reset-filters'));
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.matches('.sco-search-input[data-classe-id]')) {
      filterStudentsComptabilite(event.target.getAttribute('data-classe-id'));
    }
  });

  document.addEventListener('change', function (event) {
    if (event.target.matches('.sco-filter-select[data-classe-id]')) {
      filterStudentsComptabilite(event.target.getAttribute('data-classe-id'));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.enhanceDirecteurNiveauClasseTabs === 'function') {
      window.enhanceDirecteurNiveauClasseTabs({ storageKey: STORAGE_KEY + ':niveau-classe' });
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
