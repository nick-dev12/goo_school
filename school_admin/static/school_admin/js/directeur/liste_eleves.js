/**
 * Liste des élèves — navigation onglets niveau/classe + overflow + filtres (UI v2.1)
 */
(function () {
  'use strict';

  function layoutOverflow() {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function setPanelVisible(panel, show) {
    if (!panel) return;
    panel.classList.toggle('active', show);
    panel.hidden = !show;
  }

  function resetClasseTabsInNiveau(niveauPanel) {
    if (!niveauPanel) return;
    var zone = niveauPanel.querySelector('[data-ele-classe-zone]');
    if (!zone) return;

    var btns = zone.querySelectorAll('.classe-subtab-btn');
    var panels = zone.querySelectorAll('.ele-classe-panel');
    btns.forEach(function (b, i) {
      var active = i === 0;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach(function (p, i) {
      setPanelVisible(p, i === 0);
    });
  }

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.ele-niveau-panel.tab-panel').forEach(function (panel) {
      setPanelVisible(panel, panel.id === tabId);
    });
    document.querySelectorAll('.ele-niveau-tab.tab-button').forEach(function (b) {
      var active = b.getAttribute('data-tab') === tabId;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    var activePanel = document.getElementById(tabId);
    if (activePanel) {
      resetClasseTabsInNiveau(activePanel);
    }

    if (btn) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
    }

    layoutOverflow();
  };

  window.switchClasseTab = function (event, subtabId) {
    if (event) event.stopPropagation();

    var btn = event && event.target ? event.target.closest('.classe-subtab-btn') : null;
    var niveauPanel = btn
      ? btn.closest('.ele-niveau-panel')
      : document.querySelector('.ele-classe-panel#' + subtabId)?.closest('.ele-niveau-panel');

    if (!niveauPanel) return;

    niveauPanel.querySelectorAll('.ele-classe-panel').forEach(function (content) {
      setPanelVisible(content, content.id === subtabId);
    });
    niveauPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      var active = b.getAttribute('data-subtab') === subtabId;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    layoutOverflow();
  };

  window.filterStudents = function (classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    var filterStatut = document.getElementById('filter-statut-' + classeId);
    var filterSexe = document.getElementById('filter-sexe-' + classeId);
    var filterAbsences = document.getElementById('filter-absences-' + classeId);
    var clearButton = document.getElementById('clear-search-' + classeId);
    var resultsDiv = document.getElementById('filter-results-' + classeId);
    var resultsCount = document.getElementById('results-count-' + classeId);

    if (!searchInput) return;

    var searchTerm = searchInput.value.toLowerCase().trim();
    var statutValue = filterStatut ? filterStatut.value : '';
    var sexeValue = filterSexe ? filterSexe.value : '';
    var absencesValue = filterAbsences ? filterAbsences.value : '';

    if (clearButton) clearButton.hidden = !searchTerm;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;
    var rows = classeContent.querySelectorAll('.list-row');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var nom = row.dataset.nom || '';
      var prenom = row.dataset.prenom || '';
      var email = row.dataset.email || '';
      var matricule = row.dataset.matricule || '';
      var statut = row.dataset.statut || '';
      var sexe = row.dataset.sexe || '';
      var absences = parseInt(row.dataset.absences || '0', 10);

      var matchesSearch = !searchTerm ||
        nom.includes(searchTerm) ||
        prenom.includes(searchTerm) ||
        email.includes(searchTerm) ||
        matricule.includes(searchTerm);
      var matchesStatut = !statutValue || statut === statutValue;
      var matchesSexe = !sexeValue || sexe === sexeValue;
      var matchesAbsences = true;
      if (absencesValue === '0') matchesAbsences = absences === 0;
      else if (absencesValue === '1-2') matchesAbsences = absences >= 1 && absences <= 2;
      else if (absencesValue === '3-4') matchesAbsences = absences >= 3 && absences <= 4;
      else if (absencesValue === '5+') matchesAbsences = absences >= 5;

      if (matchesSearch && matchesStatut && matchesSexe && matchesAbsences) {
        row.classList.remove('hidden');
        visibleCount += 1;
      } else {
        row.classList.add('hidden');
      }
    });

    if (resultsDiv && resultsCount) {
      var filtering = searchTerm || statutValue || sexeValue || absencesValue;
      if (filtering) {
        resultsCount.textContent = visibleCount;
        resultsDiv.hidden = false;
      } else {
        resultsDiv.hidden = true;
      }
    }
  };

  window.clearSearch = function (classeId) {
    var searchInput = document.getElementById('search-input-' + classeId);
    if (searchInput) searchInput.value = '';
    window.filterStudents(classeId);
  };

  window.resetFilters = function (classeId) {
    ['search-input', 'filter-statut', 'filter-sexe', 'filter-absences'].forEach(function (prefix) {
      var el = document.getElementById(prefix + '-' + classeId);
      if (el) el.value = '';
    });
    window.filterStudents(classeId);
  };

  window.ouvrirModalSanction = function (eleveId, eleveNom, classeId) {
    var modal = document.getElementById('modalSanction');
    var eleveIdInput = document.getElementById('sanction_eleve_id');
    var classeIdInput = document.getElementById('sanction_classe_id');
    var eleveNomDiv = document.getElementById('eleve_sanction_nom');
    var dateSanctionInput = document.getElementById('date_sanction');
    if (!modal) return;
    if (eleveIdInput) eleveIdInput.value = eleveId;
    if (classeIdInput) classeIdInput.value = classeId;
    if (eleveNomDiv) eleveNomDiv.textContent = 'Élève : ' + eleveNom;
    if (dateSanctionInput) dateSanctionInput.value = new Date().toISOString().split('T')[0];
    modal.style.display = 'flex';
  };

  window.fermerModalSanction = function () {
    var modal = document.getElementById('modalSanction');
    if (!modal) return;
    var form = modal.querySelector('form');
    if (form) form.reset();
    modal.style.display = 'none';
  };

  function initEleListeTabs() {
    var niveauZone = document.querySelector('[data-ele-niveau-zone]');
    if (niveauZone) {
      niveauZone.addEventListener('click', function (event) {
        var btn = event.target.closest('.ele-niveau-tab[data-tab]');
        if (!btn || !niveauZone.contains(btn)) return;
        window.switchMainTab(btn.getAttribute('data-tab'), btn);
      });

      niveauZone.querySelectorAll('[data-ele-classe-zone]').forEach(function (zone) {
        if (zone.dataset.eleClasseInit === '1') return;
        zone.dataset.eleClasseInit = '1';
        zone.addEventListener('click', function (event) {
          var btn = event.target.closest('.classe-subtab-btn');
          if (!btn || !zone.contains(btn)) return;
          window.switchClasseTab(event, btn.getAttribute('data-subtab'));
        });
      });
    }

    layoutOverflow();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEleListeTabs);
  } else {
    initEleListeTabs();
  }

  window.addEventListener('click', function (event) {
    var modal = document.getElementById('modalSanction');
    if (modal && event.target === modal) {
      window.fermerModalSanction();
    }
  });
})();
