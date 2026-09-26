/**
 * Paramètres de scolarité — modal ajout (UI v2)
 */

(function () {
  'use strict';

  function openAjouterModal() {
    var modal = document.getElementById('ajouterParametreModal');
    if (!modal) return;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeAjouterModal() {
    var modal = document.getElementById('ajouterParametreModal');
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('#btnOpenAjouterModal, .btn-open-ajouter-modal')) {
      openAjouterModal();
      return;
    }
    if (event.target.closest('[data-close-modal="ajouterParametreModal"]')) {
      closeAjouterModal();
      return;
    }
    var modal = document.getElementById('ajouterParametreModal');
    if (modal && event.target === modal) {
      closeAjouterModal();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      var modal = document.getElementById('ajouterParametreModal');
      if (modal && modal.classList.contains('show')) {
        closeAjouterModal();
      }
    }
  });

  function filterParamCards() {
    var input = document.getElementById('scpSearchInput');
    if (!input) return;
    var term = input.value.trim().toLowerCase();
    var cards = document.querySelectorAll('.scp-param-card[data-scp-search]');
    var visible = 0;
    cards.forEach(function (card) {
      var blob = (card.getAttribute('data-scp-search') || '') + ' ' + card.textContent;
      blob = blob.toLowerCase();
      var show = !term || blob.indexOf(term) !== -1;
      card.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });
    var emptyEl = document.getElementById('scpSearchEmpty');
    if (emptyEl) {
      emptyEl.hidden = !term || visible > 0;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (document.body.getAttribute('data-open-ajouter-modal') === '1') {
      openAjouterModal();
    }
    var searchInput = document.getElementById('scpSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', filterParamCards);
    }
  });
})();
