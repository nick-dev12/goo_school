/**
 * Liste des élèves — navigation onglets + filtres (UI v2)
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
    var parentPanel = (event && event.target)
      ? event.target.closest('.tab-panel')
      : document.querySelector('.classe-subtab-content#classe-' + classeId);
    if (!parentPanel) return;
    if (!parentPanel.classList.contains('tab-panel')) {
      parentPanel = parentPanel.closest('.tab-panel');
    }
    if (!parentPanel) return;

    parentPanel.querySelectorAll('.classe-subtab-content').forEach(function (content) {
      content.classList.remove('active');
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var content = document.getElementById(classeId);
    if (content) content.classList.add('active');

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
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

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.tab-button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        window.switchMainTab(this.getAttribute('data-tab'), this);
      });
    });
    document.querySelectorAll('.classe-subtab-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        window.switchClasseTab(e, btn.getAttribute('data-subtab'));
      });
    });
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });

  window.addEventListener('click', function (event) {
    var modal = document.getElementById('modalSanction');
    if (modal && event.target === modal) {
      window.fermerModalSanction();
    }
  });
})();
