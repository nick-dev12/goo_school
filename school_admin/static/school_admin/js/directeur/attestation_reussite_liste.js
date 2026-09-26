/**
 * Attestations de réussite — navigation onglets + filtres (UI v2)
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
    document.querySelectorAll('.atr-niveau-tab').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var targetBtn = btn || document.querySelector('.atr-niveau-tab[data-tab="' + tabId + '"]');
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
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  function filterStudentsAttestation(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var filterSexe = document.getElementById('filter-sexe-' + classeId);
    var clearButton = document.getElementById('clear-search-' + classeId);
    var resultsDiv = document.getElementById('filter-results-' + classeId);
    var resultsCount = document.getElementById('results-count-' + classeId);
    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    var sexeValue = filterSexe ? filterSexe.value : '';

    if (clearButton) clearButton.hidden = !searchTerm;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;

    var rows = classeContent.querySelectorAll('.list-row');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var numero = row.dataset.numero || '';
      var sexe = row.dataset.sexe || '';

      var matchesSearch = !searchTerm ||
        nom.includes(searchTerm) ||
        prenom.includes(searchTerm) ||
        numero.includes(searchTerm);

      var matchesSexe = !sexeValue || sexe === sexeValue;

      if (matchesSearch && matchesSexe) {
        row.classList.remove('hidden');
        visibleCount += 1;
      } else {
        row.classList.add('hidden');
      }
    });

    if (resultsDiv && resultsCount) {
      if (searchTerm || sexeValue) {
        resultsCount.textContent = visibleCount;
        resultsDiv.hidden = false;
      } else {
        resultsDiv.hidden = true;
      }
    }
  }

  function clearSearchCertificat(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    if (searchInput) {
      searchInput.value = '';
      filterStudentsAttestation(classeId);
    }
  }

  function resetFiltersCertificat(classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var filterSexe = document.getElementById('filter-sexe-' + classeId);
    if (searchInput) searchInput.value = '';
    if (filterSexe) filterSexe.value = '';
    filterStudentsAttestation(classeId);
  }

  document.addEventListener('click', function (event) {
    var niveauBtn = event.target.closest('.atr-niveau-tab[data-tab]');
    if (niveauBtn) {
      window.switchMainTab(niveauBtn.getAttribute('data-tab'), niveauBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
      return;
    }
    var clearBtn = event.target.closest('[data-clear-search]');
    if (clearBtn) {
      clearSearchCertificat(clearBtn.getAttribute('data-clear-search'));
      return;
    }
    var resetBtn = event.target.closest('[data-reset-filters]');
    if (resetBtn) {
      resetFiltersCertificat(resetBtn.getAttribute('data-reset-filters'));
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.matches('.atr-search-input[data-classe-id]')) {
      filterStudentsAttestation(event.target.getAttribute('data-classe-id'));
    }
  });

  document.addEventListener('change', function (event) {
    if (event.target.matches('.atr-filter-select[data-classe-id]')) {
      filterStudentsAttestation(event.target.getAttribute('data-classe-id'));
    }
  });

  if (typeof window.enhanceDirecteurNiveauClasseTabs === 'function') {
    window.enhanceDirecteurNiveauClasseTabs({ storageKey: 'directeur:attestation-reussite' });
  }
})();
