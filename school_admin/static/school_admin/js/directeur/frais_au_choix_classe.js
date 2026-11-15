/**
 * Charge les frais annexes « au choix » selon la classe sélectionnée.
 * Affichage / masquage uniquement — la soumission reste côté Django.
 */
(function () {
  'use strict';

  function esc(text) {
    var d = document.createElement('div');
    d.textContent = text == null ? '' : String(text);
    return d.innerHTML;
  }

  function resolveUrl(template, classeId) {
    if (!template) return '';
    return String(template).replace(/\/0\/?$/, '/' + classeId + '/').replace(/\/0\//, '/' + classeId + '/');
  }

  function selectedCodes(grid) {
    var raw = (grid && grid.getAttribute('data-selected-codes')) || '';
    return raw.split(',').map(function (c) { return c.trim(); }).filter(Boolean);
  }

  function renderFrais(root, data) {
    var section = root.querySelector('#fraisAuChoixSection') || root;
    var grid = root.querySelector('#fraisAuChoixGrid');
    var empty = root.querySelector('#fraisAuChoixEmpty');
    if (!grid) return;

    var frais = (data && data.frais) || [];
    var devise = (data && data.devise) || 'FCFA';
    var checked = selectedCodes(grid);
    grid.innerHTML = '';

    if (!frais.length) {
      section.hidden = false;
      if (empty) empty.hidden = false;
      return;
    }

    if (empty) empty.hidden = true;
    section.hidden = false;

    frais.forEach(function (item) {
      var label = document.createElement('label');
      label.className = 'checkbox-card-modern';
      var isChecked = checked.indexOf(item.code) !== -1;
      label.innerHTML =
        '<input type="checkbox" name="frais_annexe_choix" value="' + esc(item.code) + '"' + (isChecked ? ' checked' : '') + '>' +
        '<div class="checkbox-content-modern">' +
          '<i class="fas ' + esc(item.icon || 'fa-tag') + '" aria-hidden="true"></i>' +
          '<span>' + esc(item.libelle) + ' — ' + esc(item.montant_display || item.montant) + ' ' + esc(devise) + '</span>' +
        '</div>' +
        '<div class="checkbox-check-modern"><i class="fas fa-check" aria-hidden="true"></i></div>';
      grid.appendChild(label);
    });
  }

  function clearFrais(root) {
    var section = root.querySelector('#fraisAuChoixSection') || root;
    var grid = root.querySelector('#fraisAuChoixGrid');
    var empty = root.querySelector('#fraisAuChoixEmpty');
    if (grid) grid.innerHTML = '';
    if (empty) empty.hidden = true;
    if (section && section.id === 'fraisAuChoixSection') section.hidden = true;
  }

  function readFraisMap(root) {
    var section = root.querySelector('#fraisAuChoixSection') || root;
    var elId =
      (section && section.getAttribute('data-frais-map-el')) ||
      (root.getAttribute && root.getAttribute('data-frais-map-el')) ||
      '';
    if (elId) {
      var el = document.getElementById(elId);
      if (el) {
        try {
          return JSON.parse(el.textContent || '{}');
        } catch (e) {
          return null;
        }
      }
    }
    var raw =
      (section && section.getAttribute('data-frais-map')) ||
      (root.getAttribute && root.getAttribute('data-frais-map')) ||
      '';
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function loadForClasse(root, classeId) {
    if (!classeId) {
      clearFrais(root);
      return;
    }
    var section = root.querySelector('#fraisAuChoixSection') || root;
    var map = readFraisMap(root);
    if (map && Object.prototype.hasOwnProperty.call(map, String(classeId))) {
      var entry = map[String(classeId)] || {};
      renderFrais(root, {
        ok: true,
        frais: entry.frais || entry || [],
        devise: entry.devise || (section && section.getAttribute('data-devise')) || 'FCFA',
      });
      return;
    }
    var urlTemplate =
      (section && section.getAttribute('data-frais-au-choix-url')) ||
      (root.getAttribute && root.getAttribute('data-frais-au-choix-url')) ||
      (document.getElementById('modalInscriptionEleve') &&
        document.getElementById('modalInscriptionEleve').getAttribute('data-frais-au-choix-url')) ||
      '';
    var url = resolveUrl(urlTemplate, classeId);
    if (!url) return;

    fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          clearFrais(root);
          return;
        }
        renderFrais(root, data);
      })
      .catch(function () {
        clearFrais(root);
      });
  }

  function bindRoot(root) {
    if (!root || root.getAttribute('data-frais-au-choix-bound') === '1') return;
    var select = root.querySelector('select.js-inscription-classe, select#classe');
    if (!select) return;
    root.setAttribute('data-frais-au-choix-bound', '1');
    select.addEventListener('change', function () {
      loadForClasse(root, select.value);
    });
    if (select.value) {
      loadForClasse(root, select.value);
    }
  }

  window.initFraisAuChoixClasse = function (scope) {
    var roots = [];
    if (scope) {
      roots.push(scope);
    } else {
      var modal = document.getElementById('modalInscriptionEleve');
      if (modal) roots.push(modal);
      document.querySelectorAll('#fraisAuChoixSection').forEach(function (el) {
        var form = el.closest('form') || el;
        if (roots.indexOf(form) === -1 && (!modal || !modal.contains(el))) {
          roots.push(form);
        }
      });
    }
    roots.forEach(bindRoot);
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.initFraisAuChoixClasse();
  });
})();
