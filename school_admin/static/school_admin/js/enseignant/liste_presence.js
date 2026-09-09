// Liste de présence — interactions UI (page + modal)
(function () {
  'use strict';

  function initPresenceFormUi(root) {
    root = root || document;
    var statutOptions = root.querySelectorAll('.statut-option');
    statutOptions.forEach(function (option) {
      if (option.getAttribute('data-presence-bound') === '1') {
        return;
      }
      option.setAttribute('data-presence-bound', '1');
      option.addEventListener('click', function () {
        if (this.classList.contains('disabled')) {
          return;
        }
        var radio = this.querySelector('input[type="radio"]');
        if (!radio) {
          return;
        }
        var radioName = radio.name;
        root.querySelectorAll('input[name="' + radioName + '"]').forEach(function (input) {
          var parent = input.closest('.statut-option');
          if (parent) {
            parent.classList.remove('active');
          }
        });
        this.classList.add('active');
        radio.checked = true;
      });
    });
  }

  window.initPresenceFormUi = initPresenceFormUi;

  document.addEventListener('DOMContentLoaded', function () {
    initPresenceFormUi(document);
  });
})();
