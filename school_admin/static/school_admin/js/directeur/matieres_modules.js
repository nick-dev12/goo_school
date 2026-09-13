/**
 * Onglets filières/niveaux modules + modales ajout / modification v2
 */
(function () {
  /* Onglets filière/niveau : matieres_liste_tabs.js */

  function shouldAutoSelectNiveauCard(card) {
    if (card.getAttribute('data-niveau-selected') === '1') return true;
    var initialCredits = (card.getAttribute('data-initial-credits') || '').trim();
    if (initialCredits !== '' && parseFloat(initialCredits) > 0) return true;
    if ((card.getAttribute('data-initial-periode') || '').trim()) return true;
    return (card.getAttribute('data-initial-numero') || '').trim() !== '';
  }

  function setNiveauOpen(card, open) {
    var toggle = card.querySelector('.niveau-card-header');
    var block = card.querySelector('.niveau-credits-block');
    var hiddenInput = card.querySelector('.niveau-hidden-input');
    var creditsInput = card.querySelector('.credits-niveau-input');
    var periodeInput = card.querySelector('.periode-niveau-input');
    var numeroInput = card.querySelector('.numero-ue-input');
    var filiereBlock = card.closest('[data-department-id]');
    var filiereVisible = !filiereBlock || !filiereBlock.hidden;

    if (!block) return;

    if (open && filiereVisible) {
      block.hidden = false;
      if (hiddenInput) hiddenInput.disabled = false;
      if (creditsInput) creditsInput.disabled = false;
      if (periodeInput) periodeInput.disabled = false;
      if (numeroInput) numeroInput.disabled = false;
      card.classList.add('niveau-selected');
      if (toggle) toggle.setAttribute('aria-expanded', 'true');
    } else {
      block.hidden = true;
      if (hiddenInput) hiddenInput.disabled = true;
      if (creditsInput) {
        if (!open) creditsInput.value = '0';
        creditsInput.disabled = true;
      }
      if (periodeInput) {
        if (!open) periodeInput.value = '';
        periodeInput.disabled = true;
      }
      if (numeroInput) {
        if (!open) numeroInput.value = '';
        numeroInput.disabled = true;
      }
      card.classList.remove('niveau-selected');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
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

      if (!show) {
        block.querySelectorAll('.niveau-card').forEach(function (card) {
          setNiveauOpen(card, false);
        });
      } else {
        block.querySelectorAll('.niveau-card').forEach(function (card) {
          var isOpen = card.classList.contains('niveau-selected');
          setNiveauOpen(card, isOpen);
        });
      }
    });

    if (emptyPlaceholder) {
      emptyPlaceholder.hidden = selected.length > 0 && anyVisible;
    }
    updateSpecCount(root);
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

    root.querySelectorAll('.niveau-card').forEach(function (card) {
      var toggle = card.querySelector('.niveau-card-header');
      if (shouldAutoSelectNiveauCard(card)) {
        setNiveauOpen(card, true);
      }
      if (toggle) {
        toggle.addEventListener('click', function () {
          var isOpen = card.classList.contains('niveau-selected');
          setNiveauOpen(card, !isOpen);
          if (!isOpen) {
            var creditsInput = card.querySelector('.credits-niveau-input');
            if (creditsInput) creditsInput.focus();
          }
        });
      }
    });
  }

  function initModuleAddModal() {
    var modal = document.getElementById('moduleAddModal');
    if (!modal) return;

    var addModuleHeader = document.getElementById('addModuleBtnHeader');
    var addModuleEmpty = document.getElementById('addModuleBtnEmpty');

    function setBodyModalOpen(on) {
      document.body.classList.toggle('module-modal-open', !!on);
    }

    function openModuleModal() {
      modal.classList.add('is-open');
      setBodyModalOpen(true);
      initModuleFormRoot(modal);
    }

    function closeModuleModal() {
      modal.classList.remove('is-open');
      setBodyModalOpen(false);
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

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('is-open')) {
        closeModuleModal();
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
