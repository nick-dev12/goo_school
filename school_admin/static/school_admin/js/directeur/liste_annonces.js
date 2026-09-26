/**
 * Annonces directeur — filtre statut (URL + storage), recherche locale (UI v2)
 */
(function () {
  'use strict';

  var ANN_STORAGE_KEY = 'directeur:annonces';

  var searchInput = document.getElementById('ann-search-input');
  var clearBtn = document.getElementById('ann-clear-search');
  var resultsBox = document.getElementById('ann-filter-results');
  var resultsCount = document.getElementById('ann-results-count');

  function annPersistStatut(statut) {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.syncUrlAndStore(ANN_STORAGE_KEY, {
      statut: statut || '',
    });
  }

  function annRestoreStatutFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('statut')) {
      var stored = window.directeurTabStorage.readStore(ANN_STORAGE_KEY);
      if (stored.statut) {
        params.set('statut', stored.statut);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(ANN_STORAGE_KEY, ['statut']);
    annPersistStatut(params.get('statut') || '');
    return false;
  }

  function filterAnnonces() {
    if (!searchInput) return;
    var term = searchInput.value.toLowerCase().trim();
    var rows = document.querySelectorAll('.ann-list-row');
    var visible = 0;

    if (clearBtn) {
      clearBtn.hidden = !term;
    }

    rows.forEach(function (row) {
      var titre = row.getAttribute('data-titre') || '';
      var contenu = row.getAttribute('data-contenu') || '';
      var match = !term || titre.indexOf(term) !== -1 || contenu.indexOf(term) !== -1;

      if (match) {
        row.classList.remove('hidden');
        visible += 1;
      } else {
        row.classList.add('hidden');
      }
    });

    if (resultsBox && resultsCount) {
      if (term) {
        resultsCount.textContent = String(visible);
        resultsBox.hidden = false;
      } else {
        resultsBox.hidden = true;
      }
    }
  }

  document.addEventListener('click', function (event) {
    var statutTab = event.target.closest('.ann-statut-tab[href]');
    if (statutTab) {
      try {
        var url = new URL(statutTab.getAttribute('href'), window.location.origin);
        annPersistStatut(url.searchParams.get('statut') || '');
      } catch (err) {
        annPersistStatut('');
      }
    }
  });

  if (searchInput) {
    searchInput.addEventListener('input', filterAnnonces);
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      searchInput.value = '';
      filterAnnonces();
      searchInput.focus();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (annRestoreStatutFromStorage()) {
      return;
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
