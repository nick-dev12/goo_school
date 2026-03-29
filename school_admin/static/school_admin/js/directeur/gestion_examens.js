/**
 * Gestion des Examens — modals, onglets, filière → classes (supérieur)
 * Supérieur : matières filtrées par classes cochées + libellés de niveau (données JSON).
 */

function getMatieresSuperieurMeta() {
    const el = document.getElementById('exam-matieres-superieur-data');
    if (!el || !el.textContent) return [];
    try {
        return JSON.parse(el.textContent);
    } catch (e) {
        return [];
    }
}

function getSelectedClasseIds(modal) {
    if (!modal) return [];
    const ids = [];
    modal.querySelectorAll('input[name="classes_concernees"]:checked').forEach(function (cb) {
        const v = parseInt(cb.value, 10);
        if (!isNaN(v)) ids.push(v);
    });
    return ids;
}

/**
 * Libellé affiché : nom + niveaux (LMD, etc.) pour les classes sélectionnées concernées.
 */
function buildMatiereLabelSuperieur(entry, selectedClasseIds) {
    const sel = new Set(selectedClasseIds);
    const niveaux = [];
    const seen = {};
    (entry.par_classe || []).forEach(function (row) {
        if (!sel.has(row.classe_id)) return;
        const lbl = row.niveau_label || '';
        if (lbl && !seen[lbl]) {
            seen[lbl] = true;
            niveaux.push(lbl);
        }
    });
    const nom = entry.nom || '';
    if (niveaux.length === 0) return nom;
    return nom + ' — ' + niveaux.join(', ');
}

function renderMatieresSuperieurMount(modal, preselectedMatiereIds) {
    const root = document.getElementById('gestion-examens-root');
    if (!root || root.dataset.estSuperieur !== 'true') return;

    const mount = modal.querySelector('.js-exam-matieres-superieur-mount');
    const emptyHint = modal.querySelector('.js-exam-matieres-superieur-empty');
    if (!mount) return;

    const inputName = mount.getAttribute('data-input-name') || 'matieres';
    const meta = getMatieresSuperieurMeta();
    const selectedIds = getSelectedClasseIds(modal);
    const pre = new Set(
        (preselectedMatiereIds || []).map(function (x) {
            return parseInt(x, 10);
        })
    );

    mount.innerHTML = '';

    if (selectedIds.length === 0) {
        const p = document.createElement('p');
        p.className = 'exam-filiere-placeholder';
        p.style.margin = '0';
        p.innerHTML =
            '<i class="fas fa-layer-group"></i> ' +
            'Sélectionnez au moins une promotion à l’étape 3 pour afficher les matières.';
        mount.appendChild(p);
        if (emptyHint) emptyHint.style.display = 'none';
        return;
    }

    const selectedSet = new Set(selectedIds);
    let shown = 0;

    meta.forEach(function (entry) {
        const ids = entry.classe_ids || [];
        let match = false;
        for (let i = 0; i < ids.length; i++) {
            if (selectedSet.has(ids[i])) {
                match = true;
                break;
            }
        }
        if (!match) return;

        const id = entry.id;
        const label = buildMatiereLabelSuperieur(entry, selectedIds);
        const lab = document.createElement('label');
        lab.className = 'exam-checkbox-card';
        lab.setAttribute('for', 'msup_' + inputName + '_' + id);

        const inp = document.createElement('input');
        inp.type = 'checkbox';
        inp.name = inputName;
        inp.value = String(id);
        inp.id = 'msup_' + inputName + '_' + id;
        inp.className = 'js-exam-matiere-superieur-cb';
        if (pre.has(id)) inp.checked = true;

        const span = document.createElement('span');
        span.className = 'exam-checkbox-card__text';
        const strong = document.createElement('strong');
        strong.textContent = label;
        span.appendChild(strong);

        lab.appendChild(inp);
        lab.appendChild(span);
        mount.appendChild(lab);
        shown++;
    });

    syncExamCheckboxCards(modal);

    if (emptyHint) {
        emptyHint.style.display = shown === 0 ? '' : 'none';
    }
}

function refreshMatieresSuperieurInModal(modal, preselectedMatiereIds) {
    renderMatieresSuperieurMount(modal, preselectedMatiereIds);
}

function initSuperieurMatieresListeners(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    const root = document.getElementById('gestion-examens-root');
    if (!root || root.dataset.estSuperieur !== 'true') return;

    modal.addEventListener(
        'change',
        function (ev) {
            const t = ev.target;
            if (t && t.name === 'classes_concernees') {
                const preserved = [];
                modal.querySelectorAll('.js-exam-matieres-superieur-mount input[type="checkbox"]:checked').forEach(function (cb) {
                    const v = parseInt(cb.value, 10);
                    if (!isNaN(v)) preserved.push(v);
                });
                refreshMatieresSuperieurInModal(modal, preserved);
            }
            if (t && t.classList && t.classList.contains('js-exam-matiere-superieur-cb')) {
                syncExamCheckboxCards(modal);
            }
        },
        true
    );
}

function syncExamCheckboxCards(scope) {
    const root = scope || document;
    root.querySelectorAll('.exam-checkbox-card input[type="checkbox"]').forEach(function (cb) {
        const card = cb.closest('.exam-checkbox-card');
        if (card) card.classList.toggle('is-checked', cb.checked);
    });
}

function updateFilierePanels(modal) {
    if (!modal) return;
    const select = modal.querySelector('.js-filiere-select-examen');
    const placeholder = modal.querySelector('.js-filiere-placeholder');
    const panels = modal.querySelectorAll('.js-filiere-panel-examen');
    if (!select || !panels.length) return;

    const v = select.value;
    panels.forEach(function (p) {
        const match = p.getAttribute('data-groupe-key') === v;
        if (match) p.classList.add('is-visible');
        else p.classList.remove('is-visible');
    });

    if (placeholder) {
        placeholder.style.display = v ? 'none' : '';
    }
    syncExamCheckboxCards(modal);
}

function updateSelectionCountExam(modal) {
    if (!modal) return;
    const n = modal.querySelectorAll('input[name="classes_concernees"]:checked').length;
    const el = modal.querySelector('.js-selection-count');
    if (el) el.textContent = String(n);
}

function initFiliereExamModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    const select = modal.querySelector('.js-filiere-select-examen');
    if (!select) return;

    select.addEventListener('change', function () {
        updateFilierePanels(modal);
        updateSelectionCountExam(modal);
    });

    modal.querySelectorAll('input[name="classes_concernees"]').forEach(function (cb) {
        cb.addEventListener('change', function () {
            syncExamCheckboxCards(modal);
            updateSelectionCountExam(modal);
        });
    });

    updateFilierePanels(modal);
    updateSelectionCountExam(modal);
}

// Modal création
function openModal() {
    const m = document.getElementById('sessionModal');
    m.classList.add('show');
    const sel = m.querySelector('.js-filiere-select-examen');
    if (sel) {
        sel.value = '';
        updateFilierePanels(m);
        updateSelectionCountExam(m);
    }
    syncExamCheckboxCards(m);
    refreshMatieresSuperieurInModal(m, null);
}

function closeModal() {
    const m = document.getElementById('sessionModal');
    m.classList.remove('show');
    const form = m.querySelector('form');
    if (form) form.reset();
    const sel = m.querySelector('.js-filiere-select-examen');
    if (sel) {
        sel.value = '';
        updateFilierePanels(m);
        updateSelectionCountExam(m);
    }
    syncExamCheckboxCards(m);
    refreshMatieresSuperieurInModal(m, null);
}

function openEditModal(sessionId, nomExamen, periodeId, dateDebut, dateFin, description, selectedClasseIds, selectedMatiereIds) {
    const modal = document.getElementById('editSessionModal');
    const form = document.getElementById('editSessionForm');

    form.action = '/modifier-session-examen/' + sessionId + '/';

    document.getElementById('edit_session_id').value = sessionId;
    document.getElementById('edit_nom_examen').value = nomExamen;
    document.getElementById('edit_periode_id').value = periodeId;
    document.getElementById('edit_date_debut').value = dateDebut;
    document.getElementById('edit_date_fin').value = dateFin;
    document.getElementById('edit_description').value = description || '';

    modal.classList.add('show');

    const root = document.getElementById('gestion-examens-root');
    const estSuperieur = root && root.dataset.estSuperieur === 'true';

    if (estSuperieur && Array.isArray(selectedClasseIds)) {
        modal.querySelectorAll('input[name="classes_concernees"]').forEach(function (cb) {
            const vid = parseInt(cb.value, 10);
            cb.checked = selectedClasseIds.indexOf(vid) !== -1;
        });
    }

    const sel = modal.querySelector('.js-filiere-select-examen');
    if (sel) {
        sel.value = '';
        updateFilierePanels(modal);
        updateSelectionCountExam(modal);
    }
    syncExamCheckboxCards(modal);

    if (estSuperieur) {
        refreshMatieresSuperieurInModal(modal, Array.isArray(selectedMatiereIds) ? selectedMatiereIds : []);
    }
}

function closeEditModal() {
    const modal = document.getElementById('editSessionModal');
    modal.classList.remove('show');
    document.getElementById('editSessionForm').reset();
    document.querySelectorAll('#editSessionModal input[type="checkbox"]').forEach(function (cb) {
        cb.checked = false;
    });
    const sel = modal.querySelector('.js-filiere-select-examen');
    if (sel) {
        sel.value = '';
        updateFilierePanels(modal);
        updateSelectionCountExam(modal);
    }
    syncExamCheckboxCards(modal);
    const rootEd = document.getElementById('gestion-examens-root');
    if (rootEd && rootEd.dataset.estSuperieur === 'true') {
        refreshMatieresSuperieurInModal(modal, null);
    }
}

// Onglets
function showTab(tabId) {
    const panels = document.querySelectorAll('.tab-panel');
    panels.forEach(function (panel) {
        panel.classList.remove('active');
    });
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(function (button) {
        button.classList.remove('active');
    });
    document.getElementById(tabId).classList.add('active');
    event.target.classList.add('active');
    const subPanels = document.querySelectorAll('.sub-tab-panel');
    subPanels.forEach(function (panel) {
        panel.classList.remove('active');
    });
    const subButtons = document.querySelectorAll('.sub-tab-button');
    subButtons.forEach(function (button) {
        button.classList.remove('active');
    });
    const firstSubPanel = document.querySelector('#' + tabId + ' .sub-tab-panel:first-child');
    const firstSubButton = document.querySelector('#' + tabId + ' .sub-tab-button:first-child');
    if (firstSubPanel) firstSubPanel.classList.add('active');
    if (firstSubButton) firstSubButton.classList.add('active');
}

function showSubTab(subTabId) {
    const parentPanel = event.target.closest('.tab-panel');
    const subPanels = parentPanel.querySelectorAll('.sub-tab-panel');
    subPanels.forEach(function (panel) {
        panel.classList.remove('active');
    });
    const subButtons = parentPanel.querySelectorAll('.sub-tab-button');
    subButtons.forEach(function (button) {
        button.classList.remove('active');
    });
    document.getElementById(subTabId).classList.add('active');
    event.target.classList.add('active');
}

function validateForm() {
    const root = document.getElementById('gestion-examens-root');
    const estSuperieur = root && root.dataset.estSuperieur === 'true';
    const modal = document.getElementById('sessionModal');
    const nomExamen = document.getElementById('nom_examen').value.trim();
    const periode = document.getElementById('periode_id').value;
    const dateDebut = document.getElementById('date_debut').value;
    const dateFin = document.getElementById('date_fin').value;
    const groupesClasses = modal.querySelectorAll('input[name="groupes_classes"]:checked');
    const classesSuperieur = modal.querySelectorAll('input[name="classes_concernees"]:checked');
    const matieres = modal.querySelectorAll('input[name="matieres"]:checked');

    if (!nomExamen) {
        alert('Veuillez saisir le nom de la session d\'examen.');
        return false;
    }
    if (!periode) {
        alert('Veuillez sélectionner une période scolaire.');
        return false;
    }
    if (!dateDebut || !dateFin) {
        alert('Veuillez sélectionner les dates de début et de fin.');
        return false;
    }
    if (estSuperieur) {
        if (classesSuperieur.length === 0) {
            alert('Veuillez sélectionner au moins une classe (cochez les promotions après avoir choisi chaque filière).');
            return false;
        }
    } else if (groupesClasses.length === 0) {
        alert('Veuillez sélectionner au moins un groupe de classes.');
        return false;
    }
    if (matieres.length === 0) {
        alert('Veuillez sélectionner au moins une matière.');
        return false;
    }
    return true;
}

function toggleCheckboxGroup(groupName, maxSelections) {
    const checkboxes = document.querySelectorAll('#sessionModal input[name="' + groupName + '"]');
    const checkedBoxes = document.querySelectorAll('#sessionModal input[name="' + groupName + '"]:checked');
    if (maxSelections && checkedBoxes.length >= maxSelections) {
        checkboxes.forEach(function (checkbox) {
            if (!checkbox.checked && checkedBoxes.length >= maxSelections) {
                checkbox.disabled = true;
            }
        });
    } else {
        checkboxes.forEach(function (checkbox) {
            checkbox.disabled = false;
        });
    }
}

function deleteSession(sessionId, nomSession) {
    if (
        confirm(
            'Êtes-vous sûr de vouloir supprimer la session "' +
                nomSession +
                '" ?\n\nTous les créneaux d\'examen associés seront également supprimés.\n\nCette action est irréversible.'
        )
    ) {
        window.location.href = '/supprimer-session-examen/' + sessionId + '/';
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}

function formatTime(timeString) {
    const parts = timeString.split(':');
    return parts[0] + 'h' + parts[1];
}

function animateCards() {
    const cards = document.querySelectorAll('.session-card');
    cards.forEach(function (card, index) {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(function () {
            card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

document.addEventListener('DOMContentLoaded', function () {
    initFiliereExamModal('sessionModal');
    initFiliereExamModal('editSessionModal');
    initSuperieurMatieresListeners('sessionModal');
    initSuperieurMatieresListeners('editSessionModal');

    document.querySelectorAll('#sessionModal .exam-checkbox-card input, #editSessionModal .exam-checkbox-card input').forEach(function (cb) {
        cb.addEventListener('change', function () {
            syncExamCheckboxCards(cb.closest('.exam-modal'));
        });
    });

    const groupesCheckboxes = document.querySelectorAll('#sessionModal input[name="groupes_classes"]');
    const matieresCheckboxes = document.querySelectorAll('#sessionModal input[name="matieres"]');
    groupesCheckboxes.forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            toggleCheckboxGroup('groupes_classes');
        });
    });
    matieresCheckboxes.forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            toggleCheckboxGroup('matieres');
        });
    });

    const form = document.querySelector('#sessionModal form');
    if (form) {
        form.addEventListener('submit', function (e) {
            if (!validateForm()) e.preventDefault();
        });
    }

    window.addEventListener('click', function (event) {
        const sessionModal = document.getElementById('sessionModal');
        const editModal = document.getElementById('editSessionModal');
        if (event.target === sessionModal) closeModal();
        if (event.target === editModal) closeEditModal();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeModal();
            closeEditModal();
        }
    });

    setTimeout(animateCards, 300);
});
