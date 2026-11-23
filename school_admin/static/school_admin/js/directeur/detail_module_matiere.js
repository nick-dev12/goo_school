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
    if (scope === 'all' || scope === 'common') return data;
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
    selectEl.replaceChildren(new Option('— Choisir —', ''));
    options.forEach(function (opt) {
      selectEl.add(new Option(opt.label, opt.key, false, opt.key === selectedKey));
    });
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
      label.textContent = blocks.length > 1 && dep.id !== 'commun'
        ? 'Coefficient · ' + (dep.sigle || dep.nom)
        : 'Coefficient';
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

    if (depWrap) depWrap.hidden = scope !== 'single' || data.length <= 1;
    if (depSelect && scope === 'single' && !depSelect.value && data.length === 1) {
      depSelect.value = String(data[0].department.id);
      state.departmentId = depSelect.value;
    }

    var activeBlocks = blocksForScope(data, scope, depSelect ? depSelect.value : '');
    var niveauOptions = niveauOptionsForBlocks(activeBlocks);
    if (state.niveauKey && !niveauOptions.some(function (o) { return o.key === state.niveauKey; })) {
      state.niveauKey = '';
    }
    // Un seul niveau possible : inutile de le faire choisir.
    if (!state.niveauKey && niveauOptions.length === 1) {
      state.niveauKey = niveauOptions[0].key;
    }
    renderNiveauSelect(niveauSelect, niveauOptions, state.niveauKey);

    var classesWrap = document.getElementById('matiereHybrideClasses');
    var resume = document.getElementById('matiereHybrideResume');
    var disponibles = blocksWithNiveau(activeBlocks, state.niveauKey);
    classesWrap.replaceChildren();
    if (!disponibles.length) {
      var attente = document.createElement('p');
      attente.className = 'mm-placeholder';
      attente.textContent = state.niveauKey
        ? 'Aucune classe de ce niveau ne suit ce module (UE).'
        : 'Choisissez d’abord le niveau : ses classes apparaîtront ici.';
      classesWrap.appendChild(attente);
    }
    disponibles.forEach(function (block) {
      var item = block.niveaux_items.find(function (niveau) { return niveau.niveau_key === state.niveauKey; });
      var group = document.createElement('div');
      group.className = 'mm-classes-group';
      if (disponibles.length > 1) {
        var title = document.createElement('strong');
        title.textContent = block.department.nom;
        group.appendChild(title);
      }
      var liste = document.createElement('div');
      liste.className = 'mm-classes';
      item.classes.forEach(function (classe) {
        var label = document.createElement('label');
        label.className = 'mm-class-pill';
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'classes_matiere';
        input.value = String(classe.id);
        input.dataset.department = String(block.department.id);
        input.checked = state.classesChoisies === null || state.classesChoisies.includes(input.value);
        var texte = document.createElement('span');
        texte.textContent = classe.nom;
        label.append(input, texte);
        liste.appendChild(label);
      });
      group.appendChild(liste);
      classesWrap.appendChild(group);
    });
    function syncChoix() {
      coefsList.querySelectorAll('input').forEach(function (input) {
        state.savedCoefs[input.name.slice('coef_dep_'.length)] = input.value;
      });
      var selection = Array.from(classesWrap.querySelectorAll('input:checked'));
      var deps = new Set(selection.map(function (input) { return input.dataset.department; }));
      var coefBlocks = disponibles.filter(function (block) { return deps.has(String(block.department.id)); });
      if (scope === 'common' && selection.length) {
        coefBlocks = [{department: {id: 'commun', nom: 'Toutes les classes choisies'}}];
      }
      renderCoefFields(coefsList, coefBlocks, state.savedCoefs);
      var parFiliere = scope === 'all' && coefBlocks.length > 1
        ? ' · une matière distincte pour chacune des ' + coefBlocks.length + ' filières'
        : '';
      resume.textContent = !disponibles.length ? ''
        : selection.length
          ? (selection.length > 1 ? selection.length + ' classes suivront cette matière' : '1 classe suivra cette matière') + parFiliere
          : 'Cochez au moins une classe.';
      resume.classList.toggle('mm-resume--warn', disponibles.length > 0 && !selection.length);
    }
    classesWrap.onchange = syncChoix;
    syncChoix();
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
      savedCoefs: options.savedCoefs || {},
      classesChoisies: JSON.parse(document.getElementById('matiereClassesChoisies').textContent)
    };

    function openModal(preset) {
      preset = preset || {};
      if (preset.niveauKey || preset.scope) state.classesChoisies = null;
      if (preset.departmentId) state.departmentId = String(preset.departmentId);
      if (preset.niveauKey) state.niveauKey = preset.niveauKey;
      var depSelect = document.getElementById('matiere_hybride_department');
      if (depSelect && state.departmentId) depSelect.value = state.departmentId;
      if (preset.scope) {
        var scopeInput = form.querySelector('input[name="filiere_scope"][value="' + preset.scope + '"]');
        if (scopeInput) scopeInput.checked = true;
      }
      syncFormUI(form, data, state);
      modal.classList.add('active', 'is-open');
      document.body.style.overflow = 'hidden';
      var nom = document.getElementById('nom_matiere_modal');
      if (nom) setTimeout(function () { nom.focus(); }, 60);
    }

    function closeModal() {
      modal.classList.remove('active', 'is-open');
      document.body.style.overflow = '';
    }

    form.querySelectorAll('input[name="filiere_scope"]').forEach(function (radio) {
      radio.addEventListener('change', function () {
        state.classesChoisies = null;
        syncFormUI(form, data, state);
      });
    });

    var depSelect = document.getElementById('matiere_hybride_department');
    if (depSelect) {
      depSelect.addEventListener('change', function () {
        state.classesChoisies = null;
        state.departmentId = this.value;
        state.niveauKey = '';
        syncFormUI(form, data, state);
      });
    }

    var niveauSelect = document.getElementById('matiere_hybride_niveau');
    if (niveauSelect) {
      niveauSelect.addEventListener('change', function () {
        state.classesChoisies = null;
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
      if (e.target === modal || e.target.hasAttribute('data-mm-close')) closeModal();
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
