/**
 * Onglets principaux Spécialités / Classes / Examens & concours + modals spécialités
 */
(function () {
    'use strict';

    function layoutOverflow() {
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    }

    function initClassesMainTabs() {
        var root = document.querySelector('[data-classes-main-tabs]');
        if (!root) return;

        var addFiliereHeader = document.getElementById('addFiliereBtnHeader');
        var addClasseHeader = document.getElementById('addClasseBtn');

        function activateTab(target) {
            var buttons = root.querySelectorAll('.gcl-main-tab');
            var panels = root.querySelectorAll('[data-classes-main-panel]');

            buttons.forEach(function (btn) {
                var active = btn.getAttribute('data-main-tab') === target;
                btn.classList.toggle('active', active);
                btn.setAttribute('aria-selected', active ? 'true' : 'false');
            });

            panels.forEach(function (panel) {
                var show = panel.getAttribute('data-classes-main-panel') === target;
                panel.classList.toggle('active', show);
                panel.hidden = !show;
            });

            if (addFiliereHeader) addFiliereHeader.hidden = target !== 'specialites';
            if (addClasseHeader) addClasseHeader.hidden = target !== 'classes';

            if (target === 'classes') {
                window.requestAnimationFrame(layoutOverflow);
            }

            if (window.history && window.history.replaceState) {
                var url = new URL(window.location.href);
                if (target === 'specialites') {
                    url.searchParams.set('tab', 'specialites');
                } else if (target === 'examens-concours') {
                    url.searchParams.set('tab', 'examens-concours');
                } else {
                    url.searchParams.delete('tab');
                }
                window.history.replaceState({}, '', url.toString());
            }
        }

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.gcl-main-tab');
            if (!btn || !root.contains(btn)) return;
            activateTab(btn.getAttribute('data-main-tab'));
        });

        var initial = root.getAttribute('data-initial-tab') || 'classes';
        activateTab(initial);
    }

    function initSpecialitesModals() {
        var addFiliereBtn = document.getElementById('addFiliereBtnHeader');
        var addFiliereBtnEmpty = document.getElementById('addFiliereBtnEmpty');
        var filiereModal = document.getElementById('addFiliereModal');
        var modifierFiliereModal = document.getElementById('modifierFiliereModal');
        var formModifierFiliere = document.getElementById('formModifierFiliere');
        var modifierNomInput = document.getElementById('modifier_nom_filiere');
        var modifierSigleInput = document.getElementById('modifier_sigle_filiere');
        var closeFiliereModal = document.getElementById('closeFiliereModal');
        var closeModifierFiliereModal = document.getElementById('closeModifierFiliereModal');
        var cancelFiliere = document.getElementById('cancelFiliere');
        var cancelModifierFiliere = document.getElementById('cancelModifierFiliere');
        var modifierDomaineInput = document.getElementById('modifier_domaine');
        var modifierMentionInput = document.getElementById('modifier_mention');

        if (!filiereModal && !modifierFiliereModal) return;

        function openFiliereModal() {
            if (!filiereModal) return;
            filiereModal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeFiliereModalFunc() {
            if (!filiereModal) return;
            filiereModal.classList.remove('active');
            document.body.style.overflow = '';
        }

        function openModifierFiliereModal(filiereId, filiereNom, filiereSigle, filiereDomaine, filiereMention) {
            if (formModifierFiliere && formModifierFiliere.dataset.actionTemplate) {
                formModifierFiliere.action = formModifierFiliere.dataset.actionTemplate.replace('/0/', '/' + filiereId + '/');
            }
            if (modifierNomInput) modifierNomInput.value = filiereNom || '';
            if (modifierSigleInput) modifierSigleInput.value = filiereSigle || '';
            if (modifierDomaineInput) modifierDomaineInput.value = filiereDomaine || '';
            if (modifierMentionInput) modifierMentionInput.value = filiereMention || '';
            if (modifierFiliereModal) {
                modifierFiliereModal.classList.add('active');
                document.body.style.overflow = 'hidden';
            }
        }

        function closeModifierFiliereModalFunc() {
            if (!modifierFiliereModal) return;
            modifierFiliereModal.classList.remove('active');
            document.body.style.overflow = '';
        }

        if (addFiliereBtn) addFiliereBtn.addEventListener('click', openFiliereModal);
        if (addFiliereBtnEmpty) addFiliereBtnEmpty.addEventListener('click', openFiliereModal);
        if (closeFiliereModal) closeFiliereModal.addEventListener('click', closeFiliereModalFunc);
        if (cancelFiliere) cancelFiliere.addEventListener('click', closeFiliereModalFunc);
        if (filiereModal) {
            filiereModal.addEventListener('click', function (e) {
                if (e.target === filiereModal) closeFiliereModalFunc();
            });
        }

        document.querySelectorAll('.btn-filiere-modifier').forEach(function (btn) {
            btn.addEventListener('click', function () {
                openModifierFiliereModal(
                    this.dataset.filiereId,
                    this.dataset.filiereNom || '',
                    this.dataset.filiereSigle || '',
                    this.dataset.filiereDomaine || '',
                    this.dataset.filiereMention || ''
                );
            });
        });

        if (closeModifierFiliereModal) closeModifierFiliereModal.addEventListener('click', closeModifierFiliereModalFunc);
        if (cancelModifierFiliere) cancelModifierFiliere.addEventListener('click', closeModifierFiliereModalFunc);
        if (modifierFiliereModal) {
            modifierFiliereModal.addEventListener('click', function (e) {
                if (e.target === modifierFiliereModal) closeModifierFiliereModalFunc();
            });
        }

        document.querySelectorAll('.specialite-delete-form').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                var nom = this.dataset.filiereNom || '';
                if (!confirm('Êtes-vous sûr de vouloir supprimer la spécialité « ' + nom + ' » ?')) {
                    e.preventDefault();
                }
            });
        });

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            if (filiereModal && filiereModal.classList.contains('active')) closeFiliereModalFunc();
            if (modifierFiliereModal && modifierFiliereModal.classList.contains('active')) closeModifierFiliereModalFunc();
        });
    }

    function initExamensEmptyAddClasse() {
        var btn = document.getElementById('addClasseBtnFromExamens');
        var addClasseBtn = document.getElementById('addClasseBtn');
        if (!btn || !addClasseBtn) return;
        btn.addEventListener('click', function () {
            addClasseBtn.click();
        });
    }

    function bootClassesSpecialites() {
        initClassesMainTabs();
        initSpecialitesModals();
        initExamensEmptyAddClasse();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootClassesSpecialites);
    } else {
        bootClassesSpecialites();
    }
})();
