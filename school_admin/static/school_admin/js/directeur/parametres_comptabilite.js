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

  document.addEventListener('DOMContentLoaded', function () {
    if (document.body.getAttribute('data-open-ajouter-modal') === '1') {
      openAjouterModal();
    }
  });
})();
