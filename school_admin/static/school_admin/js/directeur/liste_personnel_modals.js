/**
 * Modals plein écran — ajout professeur / personnel sur /personnel/
 */
(function () {
  'use strict';

  var personnelPhoneInit = false;
  var profPhoneInit = false;

  function lockBody(open) {
    document.body.classList.toggle('modal-personnel-open', open);
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modal.classList.add('active');
    lockBody(true);
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) {
      return;
    }
    modal.classList.remove('active');
    if (!document.querySelector('.modal-creneau-fullscreen.active')) {
      lockBody(false);
    }
  }

  window.openModalProfesseur = function () {
    openModal('modalAjouterProfesseur');
    initProfPhoneOnce();
  };

  window.closeModalProfesseur = function () {
    closeModal('modalAjouterProfesseur');
  };

  window.openModalPersonnel = function () {
    openModal('modalAjouterPersonnel');
    initPersonnelPhoneOnce();
  };

  window.closeModalPersonnel = function () {
    closeModal('modalAjouterPersonnel');
  };

  function initPersonnelPhoneOnce() {
    if (personnelPhoneInit) {
      return;
    }
    var phoneInput = document.querySelector('#personnel_telephone');
    var phoneFullInput = document.querySelector('#personnel_telephone_full');
    var phoneError = document.querySelector('#personnel_phone-error');
    var form = document.getElementById('formAjouterPersonnel');
    if (!phoneInput || !form || !window.intlTelInput) {
      return;
    }
    personnelPhoneInit = true;
    var iti = window.intlTelInput(phoneInput, {
      utilsScript: 'https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/18.1.1/js/utils.js',
      separateDialCode: true,
      initialCountry: 'auto',
      preferredCountries: ['sn', 'ci', 'cm', 'fr'],
      geoIpLookup: function (callback) {
        fetch('https://ipapi.co/json')
          .then(function (res) {
            return res.json();
          })
          .then(function (data) {
            callback(data.country_code);
          })
          .catch(function () {
            callback('sn');
          });
      },
      nationalMode: false,
      autoFormat: true,
      autoPlaceholder: 'aggressive',
    });

    phoneInput.addEventListener('blur', function () {
      if (!phoneInput.value.trim()) {
        return;
      }
      if (iti.isValidNumber()) {
        phoneError.style.display = 'none';
        phoneInput.classList.remove('is-invalid');
        phoneFullInput.value = iti.getNumber();
      } else {
        phoneError.textContent = 'Numéro de téléphone invalide.';
        phoneError.style.display = 'block';
        phoneInput.classList.add('is-invalid');
        phoneFullInput.value = '';
      }
    });

    form.addEventListener('submit', function (e) {
      if (!phoneInput.value.trim()) {
        return;
      }
      if (iti.isValidNumber()) {
        phoneFullInput.value = iti.getNumber();
        phoneInput.value = iti.getNumber();
      } else if (!form.getAttribute('data-live-bound')) {
        e.preventDefault();
        phoneError.textContent = 'Veuillez entrer un numéro de téléphone valide.';
        phoneError.style.display = 'block';
        phoneInput.focus();
      }
    });
  }

  function initProfPhoneOnce() {
    if (profPhoneInit) {
      return;
    }
    var phoneInput = document.querySelector('#modalAjouterProfesseur #telephone');
    var phoneFullInput = document.querySelector('#modalAjouterProfesseur #telephone_full');
    var phoneError = document.querySelector('#modalAjouterProfesseur #phone-error');
    var form = document.querySelector('#modalAjouterProfesseur #ajouterProfesseurForm');
    if (!phoneInput || !form || !window.intlTelInput) {
      return;
    }
    profPhoneInit = true;
    var iti = window.intlTelInput(phoneInput, {
      utilsScript: 'https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/18.1.1/js/utils.js',
      separateDialCode: true,
      initialCountry: 'auto',
      preferredCountries: ['sn', 'ci', 'cm', 'fr'],
      geoIpLookup: function (callback) {
        fetch('https://ipapi.co/json')
          .then(function (res) {
            return res.json();
          })
          .then(function (data) {
            callback(data.country_code);
          })
          .catch(function () {
            callback('sn');
          });
      },
      nationalMode: false,
      autoFormat: true,
      autoPlaceholder: 'aggressive',
    });

    form.addEventListener('submit', function () {
      if (phoneInput.value.trim() && iti.isValidNumber()) {
        phoneFullInput.value = iti.getNumber();
        phoneInput.value = iti.getNumber();
      }
    });

    phoneInput.addEventListener('blur', function () {
      if (phoneInput.value.trim() && !iti.isValidNumber()) {
        phoneError.textContent = 'Numéro de téléphone invalide.';
        phoneError.style.display = 'block';
      } else {
        phoneError.style.display = 'none';
      }
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeModal('modalAjouterProfesseur');
      closeModal('modalAjouterPersonnel');
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (document.body.getAttribute('data-open-modal-personnel') === '1') {
      openModalPersonnel();
    }
    if (document.body.getAttribute('data-open-modal-professeur') === '1') {
      openModalProfesseur();
    }
  });
})();
