/**
 * Gestion des périodes scolaires — onglets, modals, semestres LMD
 */

(function () {
    'use strict';

    function layoutOverflow() {
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    }

    var GPS_STORAGE_KEY = 'directeur:gestion-periodes';

    function gpsPersistTabs(root) {
        if (!window.directeurTabStorage || !root) return;
        var sectionBtn = root.querySelector('.gps-main-tab.active[data-main-tab]');
        var niveauBtn = document.querySelector('.gps-niveau-tab.active[data-tab-target]');
        window.directeurTabStorage.syncUrlAndStore(GPS_STORAGE_KEY, {
            section: sectionBtn ? sectionBtn.getAttribute('data-main-tab') : '',
            niveau_lmd: niveauBtn ? niveauBtn.getAttribute('data-tab-target') : '',
        });
    }

    function activateGpsMainTab(root, btn, opts) {
        opts = opts || {};
        if (!root || !btn) return;

        var target = btn.getAttribute('data-main-tab');
        var buttons = root.querySelectorAll('.gps-main-tab');
        var panels = root.querySelectorAll('.gps-tab-panel[data-main-panel]');

        buttons.forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var show = panel.getAttribute('data-main-panel') === target;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
        });

        if (!opts.skipPersist) {
            gpsPersistTabs(root);
        }

        layoutOverflow();
    }

    function initGpsMainTabs() {
        var root = document.querySelector('[data-gps-main-tabs]');
        if (!root) return;

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.gps-main-tab');
            if (!btn || !root.contains(btn)) return;
            activateGpsMainTab(root, btn);
        });

        if (window.directeurTabStorage) {
            var sel = window.directeurTabStorage.mergeUrlFromStore(GPS_STORAGE_KEY, ['section', 'niveau_lmd']);
            var section = sel.section || root.getAttribute('data-initial-section') || 'annees';
            var sectionBtn = root.querySelector('.gps-main-tab[data-main-tab="' + CSS.escape(section) + '"]');
            if (sectionBtn) {
                activateGpsMainTab(root, sectionBtn, { skipPersist: true });
            }
            if (sel.niveau_lmd) {
                var niveauBtn = document.querySelector(
                    '.gps-niveau-tab[data-tab-target="' + CSS.escape(sel.niveau_lmd) + '"]'
                );
                if (niveauBtn) {
                    activateGpsNiveauTab(document.querySelector('[data-gps-niveau-tabs]'), niveauBtn, { skipPersist: true });
                }
            }
            gpsPersistTabs(root);
        }
    }

    function activateGpsNiveauTab(root, btn, opts) {
        opts = opts || {};
        if (!root || !btn) return;

        var code = btn.getAttribute('data-tab-target');
        var buttons = root.querySelectorAll('.gps-niveau-tab');
        var panels = root.querySelectorAll('.gps-niveau-panel');

        buttons.forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var show = panel.getAttribute('data-tab-panel') === code;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
        });

        if (!opts.skipPersist) {
            var mainRoot = document.querySelector('[data-gps-main-tabs]');
            gpsPersistTabs(mainRoot);
        }

        layoutOverflow();
    }

    function initGpsNiveauTabs() {
        var root = document.querySelector('[data-gps-niveau-tabs]');
        if (!root) return;

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.gps-niveau-tab');
            if (!btn || !root.contains(btn)) return;
            activateGpsNiveauTab(root, btn);
        });
    }

    function remplirSelectSemestres(selectEl, niveauCode, valeurPreferee) {
        if (!selectEl || typeof window.SEMESTRES_PAR_NIVEAU === 'undefined') return;
        selectEl.innerHTML = '';
        var pairs = window.SEMESTRES_PAR_NIVEAU[niveauCode] || [];
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = pairs.length ? '— Choisir un semestre —' : '— Choisissez d\'abord le niveau —';
        selectEl.appendChild(opt0);
        for (var i = 0; i < pairs.length; i++) {
            var opt = document.createElement('option');
            opt.value = pairs[i][0];
            opt.textContent = pairs[i][1];
            if (valeurPreferee && pairs[i][0] === valeurPreferee) {
                opt.selected = true;
            }
            selectEl.appendChild(opt);
        }
    }

    function initSemestresLmd() {
        if (typeof window.SEMESTRES_PAR_NIVEAU === 'undefined') return;

        var addNiveau = document.getElementById('add_niveau_lmd');
        var addSem = document.getElementById('add_nom_periode_semestre');
        if (addNiveau && addSem) {
            addNiveau.addEventListener('change', function () {
                remplirSelectSemestres(addSem, addNiveau.value, null);
            });
        }

        var editNl = document.getElementById('edit_niveau_lmd');
        if (editNl) {
            editNl.addEventListener('change', function () {
                var es = document.getElementById('edit_nom_periode_semestre');
                if (es) remplirSelectSemestres(es, editNl.value, null);
            });
        }
    }

    function updateAnneeScolaireValues() {
        var dateDebutEl = document.getElementById('date_debut');
        var dateFinEl = document.getElementById('date_fin');
        if (!dateDebutEl || !dateFinEl) return;

        var dateDebut = dateDebutEl.value;
        var dateFin = dateFinEl.value;
        var previewLibelle = document.getElementById('preview_libelle');
        var previewPeriode = document.getElementById('preview_periode');

        if (dateDebut && dateFin) {
            var debut = new Date(dateDebut);
            var fin = new Date(dateFin);
            var anneeDebut = debut.getFullYear();
            var anneeFin = fin.getFullYear();
            var libelle = anneeDebut + '-' + anneeFin;

            var hiddenLibelle = document.getElementById('hidden_libelle');
            var hiddenAnneeDebut = document.getElementById('hidden_annee_debut');
            var hiddenAnneeFin = document.getElementById('hidden_annee_fin');
            if (hiddenLibelle) hiddenLibelle.value = libelle;
            if (hiddenAnneeDebut) hiddenAnneeDebut.value = anneeDebut;
            if (hiddenAnneeFin) hiddenAnneeFin.value = anneeFin;

            if (previewLibelle) previewLibelle.textContent = libelle;
            if (previewPeriode) {
                previewPeriode.textContent =
                    debut.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' }) +
                    ' - ' +
                    fin.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });
            }
        } else {
            if (previewLibelle) previewLibelle.textContent = '-';
            if (previewPeriode) previewPeriode.textContent = '-';
        }
    }

    function openAnneeScolaireModal() {
        var modal = document.getElementById('anneeScolaireModal');
        if (!modal) return;
        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');

        var now = new Date();
        var year = now.getFullYear();
        var month = now.getMonth() + 1;
        var anneeDebut = month >= 9 ? year + 1 : year;
        var dateDebutEl = document.getElementById('date_debut');
        var dateFinEl = document.getElementById('date_fin');
        if (dateDebutEl) dateDebutEl.value = anneeDebut + '-09-01';
        if (dateFinEl) dateFinEl.value = (anneeDebut + 1) + '-06-30';
        updateAnneeScolaireValues();
    }

    function closeAnneeScolaireModal() {
        var modal = document.getElementById('anneeScolaireModal');
        if (!modal) return;
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
        var form = modal.querySelector('form');
        if (form) form.reset();
    }

    function resetFormAjoutPeriodeApresFermeture() {
        var form = document.getElementById('formAjoutPeriode');
        if (!form) return;
        form.reset();
        var estActiveCb = document.getElementById('est_active');
        if (estActiveCb) estActiveCb.checked = true;
        if (typeof window.SEMESTRES_PAR_NIVEAU !== 'undefined') {
            var addN = document.getElementById('add_niveau_lmd');
            var addS = document.getElementById('add_nom_periode_semestre');
            if (addN) addN.value = '';
            if (addS) remplirSelectSemestres(addS, '', null);
        }
    }

    function openEditPeriodeModal(button) {
        var editModal = document.getElementById('periodeEditModal');
        if (!editModal || !button) return;

        var idEl = document.getElementById('edit_periode_id');
        if (idEl) idEl.value = button.dataset.id || '';

        var selSem = document.getElementById('edit_nom_periode_semestre');
        if (selSem && typeof window.SEMESTRES_PAR_NIVEAU !== 'undefined') {
            var nl = document.getElementById('edit_niveau_lmd');
            if (nl) {
                nl.value = button.dataset.niveauLmd || '';
                remplirSelectSemestres(selSem, nl.value, button.dataset.nom || '');
            }
        } else {
            var en = document.getElementById('edit_nom_periode');
            if (en) en.value = button.dataset.nom || '';
            var et = document.getElementById('edit_type_periode');
            if (et) et.value = button.dataset.type || 'trimestre';
        }

        var deb = document.getElementById('edit_date_debut');
        var fin = document.getElementById('edit_date_fin');
        var act = document.getElementById('edit_est_active');
        if (deb) deb.value = button.dataset.debut || '';
        if (fin) fin.value = button.dataset.fin || '';
        if (act) act.checked = button.dataset.active === 'true';

        editModal.classList.add('show');
        editModal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('periode-modal-open');
    }

    function openDeletePeriodeModal(button) {
        var deleteModal = document.getElementById('periodeDeleteModal');
        if (!deleteModal || !button) return;
        var idEl = document.getElementById('delete_periode_id');
        var nameEl = document.getElementById('delete_periode_name');
        if (idEl) idEl.value = button.dataset.id || '';
        if (nameEl) nameEl.textContent = button.dataset.nom || '';
        deleteModal.classList.add('show');
        deleteModal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('periode-modal-open');
    }

    function closePeriodeModal(modalId) {
        var modal = document.getElementById(modalId);
        if (!modal) return;
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('periode-modal-open');
        if (modalId === 'periodeAddModal') {
            resetFormAjoutPeriodeApresFermeture();
        }
    }

    function initModals() {
        var btnCreerAnnee = document.getElementById('btnCreerAnneeScolaire');
        var btnCreerAnneeEmpty = document.getElementById('btnCreerAnneeScolaireEmpty');
        if (btnCreerAnnee) btnCreerAnnee.addEventListener('click', openAnneeScolaireModal);
        if (btnCreerAnneeEmpty) btnCreerAnneeEmpty.addEventListener('click', openAnneeScolaireModal);

        var dateDebutInput = document.getElementById('date_debut');
        var dateFinInput = document.getElementById('date_fin');
        if (dateDebutInput) dateDebutInput.addEventListener('change', updateAnneeScolaireValues);
        if (dateFinInput) dateFinInput.addEventListener('change', updateAnneeScolaireValues);

        var formAnneeScolaire = document.getElementById('formAnneeScolaire');
        if (formAnneeScolaire) {
            formAnneeScolaire.addEventListener('submit', updateAnneeScolaireValues);
        }

        var anneeScolaireModal = document.getElementById('anneeScolaireModal');
        if (anneeScolaireModal) {
            anneeScolaireModal.addEventListener('click', function (event) {
                if (event.target === anneeScolaireModal) closeAnneeScolaireModal();
            });
        }

        var periodeAddModal = document.getElementById('periodeAddModal');

        function openAddPeriodeModal() {
            if (!periodeAddModal) return;
            resetFormAjoutPeriodeApresFermeture();
            periodeAddModal.classList.add('show');
            periodeAddModal.setAttribute('aria-hidden', 'false');
            document.body.classList.add('periode-modal-open');
        }

        var btnAjouterPeriode = document.getElementById('btnAjouterPeriode');
        if (btnAjouterPeriode) btnAjouterPeriode.addEventListener('click', openAddPeriodeModal);
        document.querySelectorAll('.js-open-add-periode').forEach(function (btn) {
            btn.addEventListener('click', openAddPeriodeModal);
        });

        var editModal = document.getElementById('periodeEditModal');
        var deleteModal = document.getElementById('periodeDeleteModal');

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;
            if (anneeScolaireModal && anneeScolaireModal.classList.contains('show')) {
                closeAnneeScolaireModal();
                return;
            }
            ['periodeAddModal', 'periodeEditModal', 'periodeDeleteModal'].forEach(function (id) {
                var m = document.getElementById(id);
                if (m && m.classList.contains('show')) {
                    closePeriodeModal(id);
                }
            });
        });

        [periodeAddModal, editModal, deleteModal].forEach(function (modal) {
            if (!modal) return;
            modal.addEventListener('click', function (event) {
                if (event.target === modal) closePeriodeModal(modal.id);
            });
        });
    }

    window.openEditPeriodeModal = openEditPeriodeModal;
    window.openDeletePeriodeModal = openDeletePeriodeModal;
    window.closePeriodeModal = closePeriodeModal;
    window.closeAnneeScolaireModal = closeAnneeScolaireModal;

    function bootGpsPage() {
        initGpsNiveauTabs();
        initGpsMainTabs();
        initSemestresLmd();
        initModals();
        layoutOverflow();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootGpsPage);
    } else {
        bootGpsPage();
    }
})();
