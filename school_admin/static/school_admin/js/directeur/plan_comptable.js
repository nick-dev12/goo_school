(function () {
  'use strict';

  var numeroInput = document.getElementById('cg-plan-numero');
  var classeSelect = document.getElementById('cg-plan-classe');
  var natureSelect = document.getElementById('cg-plan-nature');
  var hintEl = document.getElementById('cg-plan-hint');

  if (!numeroInput || !classeSelect || !natureSelect) {
    return;
  }

  var CLASSE4_PASSIF = ['40', '42', '44', '45', '46', '47', '48', '49'];

  function inferFromNumero(raw) {
    var numero = String(raw || '').trim();
    if (!numero || !/^\d/.test(numero)) {
      return null;
    }
    var lead = numero.charAt(0);
    if ('12345678'.indexOf(lead) === -1) {
      return null;
    }
    var classe = lead;
    var nature;
    if (lead === '1') {
      nature = 'passif';
    } else if (lead === '2' || lead === '3' || lead === '5') {
      nature = 'actif';
    } else if (lead === '4') {
      var passif = CLASSE4_PASSIF.some(function (p) {
        return numero.indexOf(p) === 0;
      });
      nature = passif ? 'passif' : 'actif';
    } else if (lead === '6') {
      nature = 'charge';
    } else if (lead === '7') {
      nature = 'produit';
    } else {
      nature = 'hors';
    }
    return { classe: classe, nature: nature };
  }

  function applyInference() {
    var inferred = inferFromNumero(numeroInput.value);
    if (!inferred) {
      if (hintEl) {
        hintEl.hidden = true;
        hintEl.textContent = '';
      }
      return;
    }
    classeSelect.value = inferred.classe;
    natureSelect.value = inferred.nature;
    if (hintEl) {
      hintEl.hidden = false;
      hintEl.textContent =
        'Classe ' +
        inferred.classe +
        ' · ' +
        (inferred.nature === 'produit'
          ? 'Produit (recette)'
          : inferred.nature === 'charge'
            ? 'Charge'
            : inferred.nature === 'actif'
              ? 'Actif'
              : inferred.nature === 'passif'
                ? 'Passif'
                : 'Hors bilan') +
        ' — selon le numéro SYSCOHADA.';
    }
  }

  numeroInput.addEventListener('input', applyInference);
  numeroInput.addEventListener('change', applyInference);
  applyInference();
})();
