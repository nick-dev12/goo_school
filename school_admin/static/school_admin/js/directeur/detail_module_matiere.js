/**
 * Modale ajout matière hybride (multi-filières, coef par filière)
 */
(function () {
  function readNiveauxData() {
    var el = document.getElementById('matiereNiveauxParFiliereData');
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || '[]');
    } catch (e) {
      return [];
    }
  }

  function getScope(form) {
    var checked = form.querySelector('input[name="filiere_scope"]:checked');
    return checked ? checked.value : 'single';
  }

  function blocksForScope(data, scope, departmentId) {
    if (scope === 'all') return data;
    var depId = parseInt(departmentId || '0', 10);
    return data.filter(function (b) { return b.department.id === depId; });
  }

  function niveauOptionsForBlocks(blocks) {
    var map = {};
    blocks.forEach(function (block) {
      (block.niveaux_items || []).forEach(function (item) {
        if (!map[item.niveau_key]) {
          map[item.niveau_key] = item.niveau_label;
        }
      });
    });
    return Object.keys(map).map(function (key) {
      return { key: key, label: map[key] };
    });
  }

  function blocksWithNiveau(blocks, niveauKey) {
    return blocks.filter(function (block) {
      return (block.niveaux_items || []).some(function (item) {
        return item.niveau_key === niveauKey;
      });
    });
  }

  function renderNiveauSelect(selectEl, options, selectedKey) {
    if (!selectEl) return;
    var html = '<option value="">— Choisir —</option>';
    options.forEach(function (opt) {
      var sel = opt.key === selectedKey ? ' selected' : '';
      html += '<option value="' + opt.key + '"' + sel + '>' + opt.label + '</option>';
    });
    selectEl.innerHTML = html;
  }

  function renderCoefFields(container, blocks, savedCoefs) {
    if (!container) return;
    container.innerHTML = '';
    blocks.forEach(function (block) {
      var dep = block.department;
      var row = document.createElement('div');
      row.className = 'matiere-hybride-coef-row';
      var label = document.createElement('label');
      label.className = 'matiere-hybride-coef-label';
      label.setAttribute('for', 'coef_dep_' + dep.id);
      label.textContent = dep.nom + (dep.sigle ? ' (' + dep.sigle + ')' : '');
      var input = document.createElement('input');
      input.type = 'number';
      input.className = 'form-control matiere-hybride-coef-input';
      input.id = 'coef_dep_' + dep.id;
      input.name = 'coef_dep_' + dep.id;
      input.min = '0';
      input.max = '10';
      input.step = '0.1';
      input.required = true;
      var saved = savedCoefs && savedCoefs[String(dep.id)];
      input.value = saved !== undefined && saved !== null && saved !== '' ? saved : '1.0';
      row.appendChild(label);
      row.appendChild(input);
      container.appendChild(row);
    });
  }

  function syncFormUI(form, data, state) {
    var scope = getScope(form);
    var depWrap = document.getElementById('matiereHybrideDepWrap');
    var depSelect = document.getElementById('matiere_hybride_department');
    var niveauSelect = document.getElementById('matiere_hybride_niveau');
    var coefsList = document.getElementById('matiereHybrideCoefsList');

    if (depWrap) depWrap.hidden = scope === 'all';
    if (depSelect && scope === 'single' && !depSelect.value && data.length === 1) {
      depSelect.value = String(data[0].department.id);
      state.departmentId = depSelect.value;
    }

    var activeBlocks = blocksForScope(data, scope, depSelect ? depSelect.value : '');
    var niveauOptions = niveauOptionsForBlocks(activeBlocks);
    if (state.niveauKey && !niveauOptions.some(function (o) { return o.key === state.niveauKey; })) {
      state.niveauKey = '';
    }
    renderNiveauSelect(niveauSelect, niveauOptions, state.niveauKey);

    var coefBlocks = blocksWithNiveau(activeBlocks, state.niveauKey);
    if (!state.niveauKey) coefBlocks = activeBlocks;
    renderCoefFields(coefsList, coefBlocks, state.savedCoefs);
  }

  window.initDetailModuleMatiereModal = function (options) {
    options = options || {};
    var modal = document.getElementById('modalMatiereClasse');
    var form = document.getElementById('formMatiereClasse');
    if (!modal || !form) return;

    var data = readNiveauxData();
    var state = {
      departmentId: options.defaultDepartmentId || '',
      niveauKey: options.defaultNiveauKey || '',
      savedCoefs: options.savedCoefs || {}
    };

    function openModal(preset) {
      preset = preset || {};
      if (preset.departmentId) state.departmentId = String(preset.departmentId);
      if (preset.niveauKey) state.niveauKey = preset.niveauKey;
      var depSelect = document.getElementById('matiere_hybride_department');
      if (depSelect && state.departmentId) depSelect.value = state.departmentId;
      if (preset.scope) {
        var scopeInput = form.querySelector('input[name="filiere_scope"][value="' + preset.scope + '"]');
        if (scopeInput) scopeInput.checked = true;
      }
      syncFormUI(form, data, state);
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }

    function closeModal() {
      modal.classList.remove('active');
      document.body.style.overflow = 'auto';
    }

    form.querySelectorAll('input[name="filiere_scope"]').forEach(function (radio) {
      radio.addEventListener('change', function () {
        syncFormUI(form, data, state);
      });
    });

    var depSelect = document.getElementById('matiere_hybride_department');
    if (depSelect) {
      depSelect.addEventListener('change', function () {
        state.departmentId = this.value;
        state.niveauKey = '';
        syncFormUI(form, data, state);
      });
    }

    var niveauSelect = document.getElementById('matiere_hybride_niveau');
    if (niveauSelect) {
      niveauSelect.addEventListener('change', function () {
        state.niveauKey = this.value;
        syncFormUI(form, data, state);
      });
    }

    document.querySelectorAll('.btn-open-modal-matiere').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openModal({
          departmentId: this.getAttribute('data-department-id'),
          niveauKey: this.getAttribute('data-niveau-key'),
          scope: 'single'
        });
      });
    });

    var btnHeader = document.getElementById('btnAjouterMatiereModule');
    if (btnHeader) {
      btnHeader.addEventListener('click', function () {
        openModal({ scope: data.length > 1 ? 'single' : 'single' });
      });
    }

    var closeBtn = document.getElementById('closeModalMatiereClasse');
    var cancelBtn = document.getElementById('cancelModalMatiereClasse');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('active')) closeModal();
    });

    syncFormUI(form, data, state);
    if (modal.classList.contains('active')) {
      document.body.style.overflow = 'hidden';
    }
  };
})();
