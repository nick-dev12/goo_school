/**
 * Gestion des matières — UI v2
 */

window.toggleCoefficientField = function (checkbox) {
    if (!checkbox) return;
    var groupeWrapper = checkbox.closest('.groupe-with-coefficient');
    if (!groupeWrapper) return;
    var coefficientField = groupeWrapper.querySelector('.coefficient-field-wrapper');
    var coefficientInput = coefficientField && coefficientField.querySelector('.coefficient-input');
    if (!coefficientField || !coefficientInput) return;
    if (checkbox.checked) {
        coefficientField.classList.add('show');
        coefficientInput.required = true;
    } else {
        coefficientField.classList.remove('show');
        coefficientInput.required = false;
    }
};

window.initCoefficientFields = function () {
    document.querySelectorAll('.groupe-checkbox-input').forEach(function (checkbox) {
        window.toggleCoefficientField(checkbox);
    });
};

window.toggleAddForm = function () {
    var formContainer = document.getElementById('addFormContainer');
    if (!formContainer) return;
    var isVisible = formContainer.style.display === 'flex';
    formContainer.style.display = isVisible ? 'none' : 'flex';
    document.body.style.overflow = isVisible ? '' : 'hidden';
    if (!isVisible) {
        var firstInput = formContainer.querySelector('input[type="text"]');
        if (firstInput) setTimeout(function () { firstInput.focus(); }, 100);
        setTimeout(function () {
            if (typeof window.initCoefficientFields === 'function') {
                window.initCoefficientFields();
            }
        }, 200);
    }
};

window.confirmDelete = function (matiereId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer cette matière ? Cette action est irréversible.')) {
        window.location.href = '/matieres/' + matiereId + '/supprimer/';
    }
};

(function () {
    'use strict';

    var state = { search: '', type: 'all' };

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            var formContainer = document.getElementById('addFormContainer');
            if (formContainer && formContainer.style.display === 'flex') {
                window.toggleAddForm();
            }
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        initToolbar();
        initTypeTabs();
        initSuperieurNav();
        applyFilters();
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    });

    function activateTypeTab(typeId) {
        var tabs = document.querySelectorAll('.mat-type-tab-btn');
        var panes = document.querySelectorAll('.mat-type-pane');
        var matched = false;
        tabs.forEach(function (btn) {
            var isTarget = btn.getAttribute('data-type-tab') === typeId;
            btn.classList.toggle('active', isTarget);
            btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
            if (isTarget) matched = true;
        });
        panes.forEach(function (pane) {
            pane.classList.toggle('active', pane.getAttribute('data-type-pane') === typeId);
        });
        if (!matched && tabs[0]) {
            tabs[0].click();
        }
    }

    function initTypeTabs() {
        document.querySelectorAll('.mat-type-tab-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                activateTypeTab(this.getAttribute('data-type-tab'));
                if (typeof window.layoutTabsOverflowNav === 'function') {
                    window.layoutTabsOverflowNav();
                }
                applyFilters();
            });
        });
    }

    function initToolbar() {
        var searchInput = document.getElementById('matSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                state.search = this.value.trim().toLowerCase();
                applyFilters();
            });
        }
        document.querySelectorAll('[data-mat-filter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('[data-mat-filter]').forEach(function (b) {
                    b.classList.remove('active');
                });
                this.classList.add('active');
                state.type = this.getAttribute('data-mat-filter');
                if (state.type === 'obligatoire' || state.type === 'optionnelle') {
                    activateTypeTab(state.type);
                }
                applyFilters();
            });
        });
    }

    function getVisibleCardsContainer() {
        var activeModule = document.querySelector('.module-panel.active');
        if (activeModule) {
            return activeModule.querySelector('.mat-cards-grid');
        }
        return document.querySelector('.mat-list-wrap');
    }

    function cardMatches(card) {
        var searchBlob = (card.getAttribute('data-search') || card.getAttribute('data-matiere') || '').toLowerCase();
        var cardType = card.getAttribute('data-type') || '';
        if (state.search && searchBlob.indexOf(state.search) === -1) return false;
        if (state.type !== 'all' && cardType !== state.type) return false;
        return true;
    }

    function applyFilters() {
        var scope = document.querySelector('.mat-list-wrap');
        if (!scope) return;

        var cards = scope.querySelectorAll('.mat-matiere-card');
        var visible = 0;

        cards.forEach(function (card) {
            var panel = card.closest('.module-panel');
            if (panel && !panel.classList.contains('active')) {
                card.classList.remove('mat-hidden');
                return;
            }
            var typePane = card.closest('.mat-type-pane');
            if (typePane && !typePane.classList.contains('active')) {
                card.classList.remove('mat-hidden');
                return;
            }
            var show = cardMatches(card);
            card.classList.toggle('mat-hidden', !show);
            if (show && (!panel || panel.classList.contains('active')) && (!typePane || typePane.classList.contains('active'))) {
                visible += 1;
            }
        });

        document.querySelectorAll('.mat-type-pane.active').forEach(function (pane) {
            var paneCards = pane.querySelectorAll('.mat-matiere-card');
            var paneVisible = 0;
            paneCards.forEach(function (card) {
                if (!card.classList.contains('mat-hidden')) paneVisible += 1;
            });
            var emptyMsg = pane.querySelector('.mat-type-empty');
            if (emptyMsg) {
                emptyMsg.hidden = paneVisible > 0 || paneCards.length === 0;
            }
        });

        var activeModule = document.querySelector('.module-panel.active');
        if (activeModule) {
            var modEmpty = activeModule.querySelector('.mat-module-empty');
            var modCards = activeModule.querySelectorAll('.mat-matiere-card');
            var modVisible = 0;
            modCards.forEach(function (c) {
                if (!c.classList.contains('mat-hidden')) modVisible += 1;
            });
            if (modEmpty) modEmpty.hidden = modVisible > 0 || modCards.length === 0;
        }

        var resultsLine = document.getElementById('matResultsLine');
        if (resultsLine) {
            var filtering = state.search || state.type !== 'all';
            var count = 0;
            cards.forEach(function (c) {
                var panel = c.closest('.module-panel');
                if (panel && !panel.classList.contains('active')) return;
                var typePane = c.closest('.mat-type-pane');
                if (typePane && !typePane.classList.contains('active')) return;
                if (!c.classList.contains('mat-hidden')) count += 1;
            });
            if (filtering && cards.length > 0) {
                resultsLine.textContent = count + ' matière' + (count > 1 ? 's' : '') + ' affichée' + (count > 1 ? 's' : '');
            } else {
                resultsLine.textContent = '';
            }
        }
    }

    function initSuperieurNav() {
        if (!document.querySelector('.mat-superieur-nav')) return;

        function activateFirstModuleInNiveau(niveauPanel) {
            if (!niveauPanel) return;
            var subs = niveauPanel.querySelectorAll('.sub-tab-btn');
            var mods = niveauPanel.querySelectorAll('.module-panel');
            subs.forEach(function (b) { b.classList.remove('active'); });
            mods.forEach(function (p) { p.classList.remove('active'); });
            if (subs[0]) subs[0].classList.add('active');
            if (mods[0]) mods[0].classList.add('active');
        }

        function resetNiveauTabs(panel) {
            if (!panel) return;
            var nivBtns = panel.querySelectorAll('.niveau-tab-btn');
            var nivPanels = panel.querySelectorAll('.niveau-panel');
            nivBtns.forEach(function (b) { b.classList.remove('active'); });
            nivPanels.forEach(function (p) { p.classList.remove('active'); });
            if (nivBtns[0]) nivBtns[0].classList.add('active');
            if (nivPanels[0]) {
                nivPanels[0].classList.add('active');
                activateFirstModuleInNiveau(nivPanels[0]);
            }
        }

        function relayout() {
            if (typeof window.layoutTabsOverflowNav === 'function') {
                window.layoutTabsOverflowNav();
            }
            applyFilters();
        }

        document.querySelectorAll('.main-tab-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var depId = btn.getAttribute('data-dep-id');
                document.querySelectorAll('.main-tab-btn').forEach(function (b) {
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                });
                btn.classList.add('active');
                btn.setAttribute('aria-selected', 'true');
                document.querySelectorAll('.department-panel').forEach(function (panel) {
                    panel.classList.toggle('active', panel.getAttribute('data-dep-id') === depId);
                });
                resetNiveauTabs(document.querySelector('.department-panel[data-dep-id="' + depId + '"]'));
                relayout();
            });
        });

        document.querySelectorAll('.department-panel').forEach(function (panel) {
            panel.querySelectorAll('.niveau-tab-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var idx = btn.getAttribute('data-niveau-idx');
                    panel.querySelectorAll('.niveau-tab-btn').forEach(function (b) { b.classList.remove('active'); });
                    btn.classList.add('active');
                    panel.querySelectorAll('.niveau-panel').forEach(function (p) {
                        p.classList.toggle('active', p.getAttribute('data-niveau-idx') === idx);
                    });
                    activateFirstModuleInNiveau(panel.querySelector('.niveau-panel[data-niveau-idx="' + idx + '"]'));
                    relayout();
                });
            });
            panel.querySelectorAll('.niveau-panel').forEach(function (niveauPanel) {
                niveauPanel.querySelectorAll('.sub-tab-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var modId = btn.getAttribute('data-module-id');
                        niveauPanel.querySelectorAll('.sub-tab-btn').forEach(function (b) { b.classList.remove('active'); });
                        btn.classList.add('active');
                        niveauPanel.querySelectorAll('.module-panel').forEach(function (p) {
                            p.classList.toggle('active', p.getAttribute('data-module-id') === modId);
                        });
                        relayout();
                    });
                });
            });
        });
    }
})();
