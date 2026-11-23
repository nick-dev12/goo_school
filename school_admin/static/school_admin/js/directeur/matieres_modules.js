/**
 * Onglets filières/niveaux modules + modales ajout / modification v2
 */
(function () {
  /* Onglets filière/niveau : matieres_liste_tabs.js */

  function syncNiveau(card, visible) {
    var checkbox = card.querySelector('.mam-niveau-select');
    var fields = card.querySelector('.niveau-credits-block');
    if (!checkbox || !fields) return;

    checkbox.disabled = !visible;
    var selected = visible && checkbox.checked;
    fields.hidden = !selected;
    fields.querySelectorAll('input, select').forEach(function (field) {
      field.disabled = !selected;
    });
    card.classList.toggle('niveau-selected', selected);
  }

  function updateSelectionSummary(root) {
    var summary = root.querySelector('[data-module-selection-summary]');
    if (!summary) return;
    var filieres = getSelectedDepIds(root).length;
    var classes = root.querySelectorAll('.mam-classes input:checked:not(:disabled)').length;
    if (!filieres) {
      summary.textContent = 'Choisissez une filière pour commencer.';
    } else if (!classes) {
      summary.textContent = 'Choisissez au moins une classe dans les niveaux proposés.';
    } else {
      summary.textContent = filieres + (filieres > 1 ? ' filières' : ' filière')
        + ' · ' + classes + (classes > 1 ? ' classes' : ' classe');
    }
  }

  function getSelectedDepIds(root) {
    var departmentsBox = root.querySelector('[data-module-departments]');
    if (!departmentsBox) return [];
    return Array.from(
      departmentsBox.querySelectorAll('input[name="departments_ids"]:checked')
    ).map(function (cb) { return cb.value; });
  }

  function updateSpecCount(root) {
    var countEl = root.querySelector('[data-module-spec-count]');
    if (!countEl) return;
    var checked = getSelectedDepIds(root).length;
    var oneLabel = countEl.getAttribute('data-one') || 'spécialité';
    var manyLabel = countEl.getAttribute('data-many') || 'spécialités';
    var emptyLabel = countEl.getAttribute('data-empty') || 'Aucune spécialité';
    if (checked === 0) {
      countEl.textContent = emptyLabel;
    } else if (checked === 1) {
      countEl.textContent = '1 ' + oneLabel;
    } else {
      countEl.textContent = checked + ' ' + manyLabel;
    }
  }

  function syncFiliereBlocks(root) {
    var selected = getSelectedDepIds(root);
    var multi = selected.length > 1;
    var anyVisible = false;
    var emptyPlaceholder = root.querySelector('[data-module-niveaux-empty]');

    root.querySelectorAll('[data-department-id]').forEach(function (block) {
      var depId = block.getAttribute('data-department-id');
      var show = selected.indexOf(depId) >= 0;
      block.hidden = !show;
      if (show) anyVisible = true;

      block.querySelectorAll('[data-show-if-multi]').forEach(function (el) {
        el.hidden = !multi;
      });

      block.querySelectorAll('.niveau-card').forEach(function (card) {
        syncNiveau(card, show);
      });
    });

    if (emptyPlaceholder) {
      emptyPlaceholder.hidden = selected.length > 0 && anyVisible;
    }
    updateSpecCount(root);
    updateSelectionSummary(root);
  }

  function initModuleFormRoot(root) {
    if (!root || root.getAttribute('data-module-form-init') === '1') return;
    root.setAttribute('data-module-form-init', '1');

    var departmentsBox = root.querySelector('[data-module-departments]');
    if (departmentsBox) {
      departmentsBox.querySelectorAll('input[name="departments_ids"]').forEach(function (cb) {
        cb.addEventListener('change', function () {
          syncFiliereBlocks(root);
        });
      });
    }

    syncFiliereBlocks(root);

    root.addEventListener('change', function (event) {
      if (event.target.matches('.mam-niveau-select')) {
        syncNiveau(event.target.closest('.niveau-card'), true);
      }
      if (event.target.matches('.mam-niveau-select, .mam-classes input')) {
        updateSelectionSummary(root);
      }
    });
  }

  function initModuleAddModal() {
    var modal = document.getElementById('moduleAddModal');
    if (!modal) return;

    var addModuleHeader = document.getElementById('addModuleBtnHeader');
    var addModuleEmpty = document.getElementById('addModuleBtnEmpty');
    var opener = null;

    function setBodyModalOpen(on) {
      document.body.classList.toggle('module-modal-open', !!on);
    }

    function openModuleModal(event) {
      opener = event.currentTarget;
      modal.classList.add('is-open');
      setBodyModalOpen(true);
      initModuleFormRoot(modal);
      modal.querySelector('#modal_nom_module').focus();
    }

    function closeModuleModal() {
      modal.classList.remove('is-open');
      setBodyModalOpen(false);
      if (opener) opener.focus();
    }

    if (modal.classList.contains('is-open')) {
      setBodyModalOpen(true);
      initModuleFormRoot(modal);
    }

    if (addModuleHeader) addModuleHeader.addEventListener('click', openModuleModal);
    if (addModuleEmpty) addModuleEmpty.addEventListener('click', openModuleModal);

    modal.querySelectorAll('[data-module-modal-close]').forEach(function (el) {
      el.addEventListener('click', function () {
        closeModuleModal();
        if (window.history.replaceState) {
          var u = new URL(window.location.href);
          u.searchParams.delete('ouvrir_modal');
          u.searchParams.delete('department');
          u.searchParams.delete('departments');
          u.searchParams.delete('nom');
          window.history.replaceState({}, '', u.pathname + (u.search ? u.search : ''));
        }
      });
    });

    document.addEventListener('keydown', function (event) {
      if (!modal.classList.contains('is-open')) return;
      if (event.key === 'Escape') {
        closeModuleModal();
      } else if (event.key === 'Tab') {
        var controls = Array.from(modal.querySelectorAll('button, input, select, a[href]')).filter(function (el) {
          return !el.disabled && el.type !== 'hidden' && el.getClientRects().length > 0;
        });
        var first = controls[0];
        var last = controls[controls.length - 1];
        if (!first) return;
        if (!modal.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
  }

  function initModuleEditModal() {
    var modal = document.getElementById('moduleEditModal');
    if (!modal) return;

    var btnModifier = document.getElementById('btnModifierModule');

    function setBodyModalOpen(on) {
      document.body.classList.toggle('module-modal-open', !!on);
    }

    function openEditModal() {
      modal.classList.add('is-open');
      setBodyModalOpen(true);
      initModuleFormRoot(modal);
    }

    function closeEditModal() {
      modal.classList.remove('is-open');
      setBodyModalOpen(false);
    }

    if (modal.classList.contains('is-open')) {
      setBodyModalOpen(true);
      initModuleFormRoot(modal);
    }

    if (btnModifier) btnModifier.addEventListener('click', openEditModal);

    modal.querySelectorAll('[data-module-edit-close]').forEach(function (el) {
      el.addEventListener('click', closeEditModal);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('is-open')) {
        closeEditModal();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initModuleAddModal();
    initModuleEditModal();
    document.querySelectorAll('[data-module-form-root]').forEach(initModuleFormRoot);
  });
})();
