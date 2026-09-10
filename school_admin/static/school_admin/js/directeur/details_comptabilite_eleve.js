/**
 * Détails comptabilité élève — onglets + modal paiement (UI v2)
 */

(function () {
  'use strict';

  var currentMontantTotal = 0;
  var currentMontantPaye = 0;
  var currentResteAPayer = 0;

  function getDevise() {
    return document.body.getAttribute('data-devise') || 'FCFA';
  }

  function formatMoney(amount) {
    return new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  }

  function switchScdTab(tabId, btn) {
    document.querySelectorAll('.scd-tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.scd-tab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.scd-tab-btn[data-scd-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
  }

  function updateResteAPayerDisplay() {
    var montantInput = document.getElementById('montant');
    if (!montantInput) return;

    var montantSaisi = parseFloat(montantInput.value) || 0;
    var nouveauResteAPayer = currentResteAPayer - montantSaisi;
    var resteAPayerDisplay = document.getElementById('resteAPayerDisplay');
    var resteAPayerApresVersement = document.getElementById('resteAPayerApresVersement');
    var devise = getDevise();

    if (montantSaisi > currentResteAPayer) {
      montantInput.setCustomValidity('Le montant saisi ne peut pas dépasser le reste à payer.');
      if (resteAPayerDisplay) resteAPayerDisplay.hidden = true;
    } else {
      montantInput.setCustomValidity('');
      if (resteAPayerDisplay && resteAPayerApresVersement) {
        if (nouveauResteAPayer > 0 && montantSaisi > 0) {
          resteAPayerDisplay.hidden = false;
          resteAPayerApresVersement.textContent = formatMoney(nouveauResteAPayer) + ' ' + devise;
        } else {
          resteAPayerDisplay.hidden = true;
        }
      }
    }
  }

  window.openPaiementModal = function (type, id, total, paye, reste) {
    var montantTotal = parseFloat(total) || 0;
    var montantPaye = parseFloat(paye) || 0;
    var resteAPayer = parseFloat(reste) || (montantTotal - montantPaye);
    var devise = getDevise();

    currentMontantTotal = montantTotal;
    currentMontantPaye = montantPaye;
    currentResteAPayer = resteAPayer;

    var elTotal = document.getElementById('montantTotal');
    var elPaye = document.getElementById('montantPaye');
    var elReste = document.getElementById('resteAPayer');
    if (elTotal) elTotal.textContent = formatMoney(montantTotal) + ' ' + devise;
    if (elPaye) elPaye.textContent = formatMoney(montantPaye) + ' ' + devise;
    if (elReste) elReste.textContent = formatMoney(resteAPayer) + ' ' + devise;

    var montantInput = document.getElementById('montant');
    if (montantInput) {
      montantInput.value = '';
      montantInput.max = resteAPayer > 0 ? resteAPayer.toFixed(2) : montantTotal.toFixed(2);
      montantInput.min = 0;
      montantInput.step = 0.01;
    }

    var resteDisplay = document.getElementById('resteAPayerDisplay');
    if (resteDisplay) resteDisplay.hidden = true;

    var eleveId = document.body.getAttribute('data-eleve-id');
    var form = document.getElementById('paiementForm');
    if (form && eleveId) {
      if (type === 'frais') {
        form.action = '/comptabilite/eleve/' + eleveId + '/frais-inscription/' + id + '/payer/';
      } else if (type === 'mensualite') {
        form.action = '/comptabilite/eleve/' + eleveId + '/mensualite/' + id + '/payer/';
      }
    }

    var modal = document.getElementById('paiementModal');
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  };

  window.closePaiementModal = function () {
    var modal = document.getElementById('paiementModal');
    if (modal) modal.classList.remove('active');
    document.body.style.overflow = '';
  };

  window.closePaiementModalOnOverlay = function (event) {
    if (event.target === event.currentTarget) {
      window.closePaiementModal();
    }
  };

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.scd-tab-btn[data-scd-tab]');
    if (tabBtn) {
      switchScdTab(tabBtn.getAttribute('data-scd-tab'), tabBtn);
      return;
    }
    var closeBtn = event.target.closest('[data-close-paiement-modal]');
    if (closeBtn) {
      window.closePaiementModal();
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.id === 'montant') {
      updateResteAPayerDisplay();
    }
  });

  document.addEventListener('change', function (event) {
    if (event.target.id === 'montant') {
      updateResteAPayerDisplay();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      window.closePaiementModal();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    switchScdTab('scd-panel-frais');
  });
})();
