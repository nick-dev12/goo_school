/**
 * Annonces directeur — recherche locale (UI v2)
 */
(function () {
  'use strict';

  var searchInput = document.getElementById('ann-search-input');
  var clearBtn = document.getElementById('ann-clear-search');
  var resultsBox = document.getElementById('ann-filter-results');
  var resultsCount = document.getElementById('ann-results-count');

  if (!searchInput) {
    return;
  }

  function filterAnnonces() {
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

  searchInput.addEventListener('input', filterAnnonces);

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      searchInput.value = '';
      filterAnnonces();
      searchInput.focus();
    });
  }
})();
