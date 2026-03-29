/**
 * Filière → filtrage des options « classe » (établissements supérieurs).
 * Utilisation : dans un <form>, un select .js-inscription-filiere et un select .js-inscription-classe
 * dont les <option data-classe-option> portent data-department-id.
 */
(function () {
  function syncFiliereFromClasse(filiereSel, classeSel) {
    if (!classeSel || !classeSel.value || !filiereSel) return;
    var val = classeSel.value;
    var opt = null;
    for (var i = 0; i < classeSel.options.length; i++) {
      if (classeSel.options[i].value === val) {
        opt = classeSel.options[i];
        break;
      }
    }
    if (!opt) return;
    var dep = opt.getAttribute('data-department-id');
    if (dep) filiereSel.value = dep;
  }

  function applyFilter(filiereSel, classeSel) {
    if (!filiereSel || !classeSel) return;
    var form = filiereSel.closest('form');
    var listMode = form && form.getAttribute('data-filiere-classe-mode') === 'filter';
    var fid = filiereSel.value;
    var placeholder = classeSel.querySelector('option:not([data-classe-option])');

    if (!fid && listMode) {
      classeSel.querySelectorAll('option[data-classe-option]').forEach(function (opt) {
        opt.hidden = false;
      });
      if (placeholder) placeholder.hidden = false;
      return;
    }

    classeSel.querySelectorAll('option[data-classe-option]').forEach(function (opt) {
      var dep = opt.getAttribute('data-department-id') || '';
      if (!fid) {
        opt.hidden = true;
      } else if (!dep) {
        opt.hidden = false;
      } else {
        opt.hidden = dep !== fid;
      }
    });
    if (placeholder) placeholder.hidden = false;
    if (!fid) {
      classeSel.value = '';
    } else {
      var sel = classeSel.options[classeSel.selectedIndex];
      if (sel && sel.hidden) classeSel.value = '';
    }
  }

  function setupPair(filiereSel, classeSel) {
    if (!filiereSel || !classeSel) return;
    function run() {
      syncFiliereFromClasse(filiereSel, classeSel);
      applyFilter(filiereSel, classeSel);
    }
    filiereSel.addEventListener('change', function () {
      applyFilter(filiereSel, classeSel);
    });
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run);
    } else {
      run();
    }
  }

  function init() {
    document.querySelectorAll('.js-inscription-filiere').forEach(function (filiereSel) {
      var form = filiereSel.closest('form');
      if (!form) return;
      var classeSel = form.querySelector('.js-inscription-classe');
      setupPair(filiereSel, classeSel);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
