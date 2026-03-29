/**
 * Filtre le select « classe » selon la filière (établissements supérieurs).
 * Interaction uniquement (pas de validation métier).
 */
(function () {
  'use strict';

  function filterOptions(filiereSelect, classeSelect) {
    var fid = filiereSelect.value;
    var opts = classeSelect.querySelectorAll('option[value]');
    opts.forEach(function (o) {
      var dep = o.getAttribute('data-department-id') || '';
      var show = !fid || String(dep) === String(fid);
      o.hidden = !show;
    });
    var cur = classeSelect.options[classeSelect.selectedIndex];
    if (cur && cur.hidden && cur.value) {
      classeSelect.value = '';
    }
  }

  function preselectFiliereFromClasse(filiereSelect, classeSelect) {
    if (!classeSelect.value) return;
    var cur = classeSelect.options[classeSelect.selectedIndex];
    if (!cur) return;
    var dep = cur.getAttribute('data-department-id');
    if (dep) filiereSelect.value = dep;
  }

  /**
   * @param {string} filiereId - id du select filière
   * @param {string} classeId - id du select classe
   */
  window.initInscriptionClasseSuperieur = function (filiereId, classeId) {
    var filiereSelect = document.getElementById(filiereId);
    var classeSelect = document.getElementById(classeId);
    if (!filiereSelect || !classeSelect) return;

    function syncFromFiliere() {
      filterOptions(filiereSelect, classeSelect);
    }

    filiereSelect.addEventListener('change', syncFromFiliere);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        preselectFiliereFromClasse(filiereSelect, classeSelect);
        syncFromFiliere();
      });
    } else {
      preselectFiliereFromClasse(filiereSelect, classeSelect);
      syncFromFiliere();
    }
  };
})();
