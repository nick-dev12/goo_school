/**
 * Liste des élèves — navigation onglets niveau/classe, overflow, persistance URL (UI v2.2)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:liste-eleves:tabs';

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

  function readPersistedSelection() {
    var params = new URLSearchParams(window.location.search);
    var niveau = (params.get('niveau') || '').trim().toLowerCase();
    var classeRaw = params.get('classe');
    var classe = classeRaw ? String(parseInt(classeRaw, 10)) : '';

    if (!niveau && !classe) {
      try {
        var stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null');
        if (stored && typeof stored === 'object') {
          niveau = (stored.niveau || '').trim().toLowerCase();
          if (stored.classe != null && stored.classe !== '') {
            classe = String(parseInt(stored.classe, 10));
          }
        }
      } catch (err) {
        /* ignore */
      }
    }

    if (classe === 'NaN') {
      classe = '';
    }
    return { niveau: niveau, classe: classe };
  }

  function activeSelectionFromDom() {
    var niveauBtn = document.querySelector('.ele-niveau-tab.active[data-niveau-key]');
    var classeBtn = document.querySelector('.ele-classe-panel:not([hidden]) .classe-subtab-btn.active[data-classe-id]')
      || document.querySelector('.ele-niveau-panel:not([hidden]) .classe-subtab-btn.active[data-classe-id]');
    return {
      niveau: niveauBtn ? niveauBtn.getAttribute('data-niveau-key') : '',
      classe: classeBtn ? String(classeBtn.getAttribute('data-classe-id') || '') : '',
    };
  }

  function persistTabSelection() {
    var sel = activeSelectionFromDom();
    if (!sel.niveau && !sel.classe) {
      return;
    }

    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ niveau: sel.niveau, classe: sel.classe, at: Date.now() })
      );
    } catch (err) {
      /* ignore */
    }

    var params = new URLSearchParams(window.location.search);
    if (sel.niveau) {
      params.set('niveau', sel.niveau);
    } else {
      params.delete('niveau');
    }
    if (sel.classe) {
      params.set('classe', sel.classe);
    } else {
      params.delete('classe');
    }
    var query = params.toString();
    var next = window.location.pathname + (query ? '?' + query : '') + window.location.hash;
    if (next !== window.location.pathname + window.location.search + window.location.hash) {
      window.history.replaceState(null, '', next);
    }
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

  window.switchMainTab = function (tabId, btn, options) {
    options = options || {};
    document.querySelectorAll('.ele-niveau-panel.tab-panel').forEach(function (panel) {
      setPanelVisible(panel, panel.id === tabId);
    });
    document.querySelectorAll('.ele-niveau-tab.tab-button').forEach(function (b) {
      var active = b.getAttribute('data-tab') === tabId;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    var activePanel = document.getElementById(tabId);
    if (activePanel && !options.skipResetClasse) {
      resetClasseTabsInNiveau(activePanel);
    }

    if (btn) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
    }

    if (!options.skipPersist) {
      persistTabSelection();
    }
    layoutOverflow();
  };

  window.switchClasseTab = function (event, subtabId, options) {
    options = options || {};
    if (event) event.stopPropagation();

    var btn = event && event.target ? event.target.closest('.classe-subtab-btn') : null;
    if (!btn && subtabId) {
      btn = document.querySelector('.classe-subtab-btn[data-subtab="' + subtabId + '"]');
    }
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

    if (!options.skipPersist) {
      persistTabSelection();
    }
    layoutOverflow();
  };

  function applyStoredTabs(selection) {
    if (!selection || (!selection.niveau && !selection.classe)) {
      layoutOverflow();
      return;
    }

    var niveauBtn = selection.niveau
      ? document.querySelector('.ele-niveau-tab[data-niveau-key="' + CSS.escape(selection.niveau) + '"]')
      : null;
    if (niveauBtn) {
      window.switchMainTab(niveauBtn.getAttribute('data-tab'), niveauBtn, {
        skipResetClasse: true,
        skipPersist: true,
      });
    }

    if (selection.classe) {
      var subtabId = 'classe-' + selection.classe;
      window.switchClasseTab(null, subtabId, { skipPersist: true });
    }

    persistTabSelection();
    layoutOverflow();
  }

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

    var params = readPersistedSelection();
    var hasQuery = window.location.search.indexOf('niveau=') !== -1 ||
      window.location.search.indexOf('classe=') !== -1;
    if (hasQuery || params.niveau || params.classe) {
      applyStoredTabs(params);
    } else {
      persistTabSelection();
      layoutOverflow();
    }
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
