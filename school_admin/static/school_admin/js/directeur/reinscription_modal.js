/**
 * Réinscription — modals sur la liste des élèves (recherche + formulaire).
 */
(function () {
  'use strict';

  var listeModal = document.getElementById('modalReinscriptionListe');
  var formModal = document.getElementById('modalReinscriptionForme');
  if (!listeModal || !formModal) {
    return;
  }

  var listeCorps = document.getElementById('riListeCorps');
  var formCorps = document.getElementById('riFormeCorps');
  var listeUrl = listeModal.getAttribute('data-ri-liste-url') || '';
  var didReinscrire = false;

  function lockBody(open) {
    document.body.classList.toggle('modal-personnel-open', open);
  }

  function anyModalOpen() {
    var inscription = document.getElementById('modalInscriptionEleve');
    return (
      (inscription &&
        (inscription.classList.contains('active') || inscription.classList.contains('is-open'))) ||
      (document.getElementById('modalInscriptionMasse') &&
        document.getElementById('modalInscriptionMasse').classList.contains('active')) ||
      (document.getElementById('modalRecuEleve') &&
        document.getElementById('modalRecuEleve').classList.contains('active')) ||
      listeModal.classList.contains('active') ||
      formModal.classList.contains('active')
    );
  }

  function loadingHtml(msg) {
    return (
      '<p class="ri-chargement"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> ' +
      (msg || 'Chargement…') +
      '</p>'
    );
  }

  function errorHtml() {
    return (
      '<p class="ri-erreur" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ' +
      'La connexion a échoué. Réessayez.</p>'
    );
  }

  function fetchHtml(url) {
    return fetch(url, {
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'text/html' },
      credentials: 'same-origin',
      cache: 'no-store',
    }).then(function (r) {
      if (!r.ok) {
        throw new Error(String(r.status));
      }
      return r.text();
    });
  }

  function afterListeHtml() {
    if (window.initInscriptionFiliereClasse) {
      window.initInscriptionFiliereClasse(listeCorps);
    } else if (window.AriaInscriptionFiliereClasse && window.AriaInscriptionFiliereClasse.init) {
      window.AriaInscriptionFiliereClasse.init(listeCorps);
    }
    if (window.sxInitFiltres) {
      window.sxInitFiltres();
    }
  }

  function afterFormHtml() {
    initReinscriptionFormExtras(formCorps);
    if (window.initInscriptionFiliereClasse) {
      window.initInscriptionFiliereClasse(formCorps);
    }
    if (window.initFraisAuChoixClasse) {
      formCorps.removeAttribute('data-frais-au-choix-bound');
      var section = formCorps.querySelector('#fraisAuChoixSection');
      if (section) section.removeAttribute('data-frais-au-choix-bound');
      window.initFraisAuChoixClasse(formCorps);
    }
  }

  function chargerListe(query) {
    var url = listeUrl;
    if (query) {
      url += (url.indexOf('?') >= 0 ? '&' : '?') + query.replace(/^\?/, '');
    }
    listeCorps.innerHTML = loadingHtml();
    return fetchHtml(url)
      .then(function (html) {
        listeCorps.innerHTML = html;
        afterListeHtml();
      })
      .catch(function () {
        listeCorps.innerHTML = errorHtml();
      });
  }

  function chargerForme(url) {
    formCorps.innerHTML = loadingHtml();
    return fetchHtml(url)
      .then(function (html) {
        formCorps.innerHTML = html;
        afterFormHtml();
      })
      .catch(function () {
        formCorps.innerHTML = errorHtml();
      });
  }

  window.openModalReinscriptionListe = function () {
    formModal.classList.remove('active');
    listeModal.classList.add('active');
    lockBody(true);
    chargerListe('');
  };

  window.closeModalReinscriptionListe = function () {
    listeModal.classList.remove('active');
    if (!anyModalOpen()) {
      lockBody(false);
    }
    if (didReinscrire) {
      var adresse = new URL(window.location.href);
      adresse.searchParams.delete('reinscrire');
      adresse.searchParams.delete('reinscrire_eleve');
      window.location.replace(adresse.toString());
    }
  };

  window.openModalReinscriptionForme = function (url) {
    if (!url) {
      return;
    }
    listeModal.classList.remove('active');
    formModal.classList.add('active');
    lockBody(true);
    chargerForme(url);
  };

  window.closeModalReinscriptionForme = function (backToListe) {
    formModal.classList.remove('active');
    if (backToListe) {
      listeModal.classList.add('active');
      lockBody(true);
      if (!listeCorps.querySelector('[data-ri-liste]')) {
        chargerListe('');
      }
      return;
    }
    if (!anyModalOpen()) {
      lockBody(false);
    }
  };

  function normalizeString(str) {
    if (!str) {
      return '';
    }
    return str
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim();
  }

  function initReinscriptionFormExtras(root) {
    var form = root.querySelector('#reinscriptionForm');
    if (!form) {
      return;
    }

    var countrySearchInput = root.querySelector('#nationalite_search');
    var countrySelect = root.querySelector('#nationalite');
    var countryDropdown = root.querySelector('#country_dropdown');
    var highlightedIndex = -1;
    var filteredCountries = [];

    if (countrySearchInput && countrySelect && countryDropdown) {
      var allCountries = Array.from(countrySelect.options)
        .slice(1)
        .map(function (option) {
          var text = option.textContent.trim();
          return {
            value: option.value,
            text: text,
            searchText: normalizeString(text),
          };
        });

      if (countrySelect.value) {
        var selectedOption = Array.from(countrySelect.options).find(function (opt) {
          return opt.value === countrySelect.value;
        });
        if (selectedOption) {
          countrySearchInput.value = selectedOption.textContent.trim();
          countrySearchInput.classList.add('has-value');
        }
      }

      function renderDropdown() {
        countryDropdown.innerHTML = '';
        if (!filteredCountries.length) {
          countryDropdown.innerHTML =
            '<div class="country-dropdown-item no-results">Aucun pays trouvé</div>';
          countryDropdown.style.display = 'block';
          return;
        }
        filteredCountries.forEach(function (country, index) {
          var item = document.createElement('div');
          item.className = 'country-dropdown-item';
          item.textContent = country.text;
          item.addEventListener('click', function () {
            selectCountry(country.value, country.text);
          });
          item.addEventListener('mouseenter', function () {
            highlightItem(index);
          });
          countryDropdown.appendChild(item);
        });
        countryDropdown.style.display = 'block';
        highlightedIndex = -1;
      }

      function filterCountries(searchTerm) {
        var normalizedTerm = normalizeString(searchTerm);
        if (!normalizedTerm) {
          filteredCountries = [];
          countryDropdown.style.display = 'none';
          return;
        }
        filteredCountries = allCountries
          .filter(function (country) {
            return country.searchText.indexOf(normalizedTerm) !== -1;
          })
          .slice(0, 20);
        renderDropdown();
      }

      function selectCountry(value, text) {
        countrySearchInput.value = text;
        countrySelect.value = value;
        countryDropdown.style.display = 'none';
        countrySearchInput.classList.add('has-value');
        highlightedIndex = -1;
        countrySelect.dispatchEvent(new Event('change', { bubbles: true }));
      }

      function highlightItem(index) {
        var items = countryDropdown.querySelectorAll('.country-dropdown-item:not(.no-results)');
        items.forEach(function (item, i) {
          item.classList.toggle('highlighted', i === index);
        });
        highlightedIndex = index;
      }

      countrySearchInput.addEventListener('input', function (e) {
        filterCountries(e.target.value);
        if (!e.target.value) {
          countrySelect.value = '';
          countrySearchInput.classList.remove('has-value');
        }
      });

      countrySearchInput.addEventListener('focus', function () {
        if (filteredCountries.length || countrySearchInput.value.trim()) {
          filterCountries(countrySearchInput.value);
        }
      });

      document.addEventListener('click', function (e) {
        if (!countrySearchInput.contains(e.target) && !countryDropdown.contains(e.target)) {
          countryDropdown.style.display = 'none';
        }
      });

      countrySearchInput.addEventListener('keydown', function (e) {
        var items = countryDropdown.querySelectorAll('.country-dropdown-item:not(.no-results)');
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (items.length) {
            highlightedIndex = (highlightedIndex + 1) % items.length;
            highlightItem(highlightedIndex);
          }
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (items.length) {
            highlightedIndex = highlightedIndex <= 0 ? items.length - 1 : highlightedIndex - 1;
            highlightItem(highlightedIndex);
          }
        } else if (e.key === 'Enter' && highlightedIndex >= 0 && filteredCountries[highlightedIndex]) {
          e.preventDefault();
          var country = filteredCountries[highlightedIndex];
          selectCountry(country.value, country.text);
        } else if (e.key === 'Escape') {
          countryDropdown.style.display = 'none';
        }
      });
    }

    var parentPhoneInput = root.querySelector('#parent_telephone');
    var parentPhoneFullInput = root.querySelector('#parent_telephone_full');
    if (parentPhoneInput && window.intlTelInput) {
      var itiParent = window.intlTelInput(parentPhoneInput, {
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
        autoPlaceholder: 'aggressive',
      });
      form.addEventListener('submit', function () {
        if (parentPhoneInput.value.trim() && itiParent.isValidNumber && itiParent.isValidNumber()) {
          if (parentPhoneFullInput) {
            parentPhoneFullInput.value = itiParent.getNumber();
          }
        } else if (parentPhoneFullInput && parentPhoneInput.value.trim()) {
          parentPhoneFullInput.value = parentPhoneInput.value.trim();
        }
      });
      if (parentPhoneInput.value) {
        try {
          itiParent.setNumber(parentPhoneInput.value);
          if (parentPhoneFullInput) {
            parentPhoneFullInput.value = itiParent.getNumber();
          }
        } catch (err) {
          /* ignore */
        }
      }
    }
  }

  listeCorps.addEventListener('submit', function (e) {
    var form = e.target.closest('[data-ri-search]');
    if (!form) {
      return;
    }
    e.preventDefault();
    var params = new URLSearchParams(new FormData(form));
    chargerListe(params.toString());
  });

  listeCorps.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-ri-eleve-url]');
    if (!btn) {
      return;
    }
    openModalReinscriptionForme(btn.getAttribute('data-ri-eleve-url'));
  });

  formCorps.addEventListener('click', function (e) {
    if (e.target.closest('[data-ri-back]')) {
      closeModalReinscriptionForme(true);
    }
  });

  formCorps.addEventListener('submit', function (e) {
    var form = e.target.closest('#reinscriptionForm');
    if (!form) {
      return;
    }
    e.preventDefault();
    var action = form.getAttribute('action');
    var bouton = form.querySelector('[type="submit"]');
    if (bouton) {
      bouton.disabled = true;
    }
    fetch(action, {
      method: 'POST',
      body: new FormData(form),
      headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'text/html' },
      credentials: 'same-origin',
    })
      .then(function (r) {
        var ct = r.headers.get('Content-Type') || '';
        if (ct.indexOf('application/json') !== -1) {
          return r.json().then(function (data) {
            if (data && data.ok) {
              didReinscrire = true;
              closeModalReinscriptionForme(false);
              closeModalReinscriptionListe();
              return null;
            }
            throw new Error((data && data.message) || 'Erreur');
          });
        }
        return r.text().then(function (html) {
          if (r.redirected || (html && html.indexOf('id="reinscriptionForm"') === -1 && r.ok && r.status === 200)) {
            /* success redirect followed as HTML of liste — reload */
            didReinscrire = true;
            window.location.reload();
            return null;
          }
          formCorps.innerHTML = html;
          afterFormHtml();
          return null;
        });
      })
      .catch(function () {
        formCorps.innerHTML = errorHtml();
      })
      .finally(function () {
        if (bouton) {
          bouton.disabled = false;
        }
      });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') {
      return;
    }
    if (formModal.classList.contains('active')) {
      closeModalReinscriptionForme(true);
    } else if (listeModal.classList.contains('active')) {
      closeModalReinscriptionListe();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    var openListe = document.body.getAttribute('data-open-reinscription-modal') === '1';
    var openEleve = document.body.getAttribute('data-open-reinscription-eleve') || '';
    if (openEleve) {
      openModalReinscriptionForme(openEleve);
    } else if (openListe) {
      openModalReinscriptionListe();
    }
  });
})();
