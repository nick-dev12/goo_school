/**
 * Cartes d'identité scolaires — navigation onglets + recherche (UI v2)
 */

(function () {
  'use strict';

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.tab-button').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId) {
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
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var target = document.getElementById(classeId);
    if (target) target.classList.add('active');

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
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

      var matchesSearch = !searchTerm ||
        nom.includes(searchTerm) ||
        prenom.includes(searchTerm) ||
        matricule.includes(searchTerm) ||
        numero.includes(searchTerm);

      if (matchesSearch) {
        row.classList.remove('hidden');
        visibleCount += 1;
      } else {
        row.classList.add('hidden');
      }
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

  function clearSearchCartes(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    if (searchInput) {
      searchInput.value = '';
      filterStudentsCartes(classeId);
    }
  }

  function activateClasseFromHash() {
    var hash = window.location.hash;
    if (!hash || !hash.startsWith('#classe-')) return;
    var classeId = hash.slice(1);
    var panel = document.getElementById(classeId);
    if (!panel) return;

    var mainPanel = panel.closest('.tab-panel');
    if (mainPanel && mainPanel.id) {
      window.switchMainTab(mainPanel.id);
    }
    window.switchClasseTab(null, classeId);
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
      clearSearchCartes(clearBtn.getAttribute('data-clear-search'));
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.matches('.sci-search-input[data-classe-id]')) {
      filterStudentsCartes(event.target.getAttribute('data-classe-id'));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
    activateClasseFromHash();
  });
})();
