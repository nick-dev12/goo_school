// Liste de présence — interactions UI (page + modal). Pas de soumission AJAX.
(function () {
  'use strict';

  function initPresenceFormUi(root) {
    root = root || document;
    var statutOptions = root.querySelectorAll('.appel-statut-opt, .statut-option');
    statutOptions.forEach(function (option) {
      if (option.getAttribute('data-presence-bound') === '1') {
        return;
      }
      option.setAttribute('data-presence-bound', '1');
      option.addEventListener('click', function () {
        if (this.classList.contains('disabled') || this.hasAttribute('disabled')) {
          return;
        }
        var radio = this.querySelector('input[type="radio"]');
        if (!radio || radio.disabled) {
          return;
        }
        var radioName = radio.name;
        root.querySelectorAll('input[name="' + radioName + '"]').forEach(function (input) {
          var parent = input.closest('.appel-statut-opt, .statut-option');
          if (parent) {
            parent.classList.remove('active');
          }
        });
        this.classList.add('active');
        radio.checked = true;
        updateAppelCounts(root);
      });
    });
    bindAppelSearch(root);
    updateAppelCounts(root);
  }

    function updateAppelCounts(root) {
    root = root || document;
    var presents = root.querySelectorAll('input[type="radio"][value="present"]:checked').length;
    var absents = root.querySelectorAll('input[type="radio"][value="absent"]:checked').length;
    root.querySelectorAll('[data-appel-count="present"]').forEach(function (el) {
      el.textContent = String(presents);
    });
    root.querySelectorAll('[data-appel-count="absent"]').forEach(function (el) {
      el.textContent = String(absents);
    });
  }

  function bindAppelSearch(root) {
    root = root || document;
    var input = root.querySelector('#profPresenceSearchInput');
    if (!input || input.getAttribute('data-presence-search-bound') === '1') {
      return;
    }
    input.setAttribute('data-presence-search-bound', '1');
    var selector = input.getAttribute('data-prof-search-target') || '.notes-list--appel .notes-list-row';
    input.addEventListener('input', function () {
      var term = input.value.trim().toLowerCase();
      root.querySelectorAll(selector).forEach(function (row) {
        var hay = (row.getAttribute('data-eleve-name') || row.textContent || '').toLowerCase();
        row.hidden = term.length > 0 && hay.indexOf(term) === -1;
      });
    });
  }

  window.initPresenceFormUi = initPresenceFormUi;

  document.addEventListener('DOMContentLoaded', function () {
    initPresenceFormUi(document);
  });
})();
