/**
 * Gestion du personnel — UI v2
 * Onglets catégories, filtre matière (professeurs), recherche et statut
 */

(function () {
    'use strict';

    var state = {
        tab: 'professeurs',
        matiere: 'all',
        status: 'all',
        search: ''
    };

    document.addEventListener('DOMContentLoaded', function () {
        initCategoryTabs();
        initMatiereTabs();
        initToolbar();
        applyFilters();

        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    });

    function initCategoryTabs() {
        var tabButtons = document.querySelectorAll('.pers-tabs-wrap .tab-btn');
        var tabPanes = document.querySelectorAll('.pers-tabs-content .tab-pane');

        tabButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                state.tab = this.getAttribute('data-tab') || 'professeurs';
                state.matiere = 'all';

                tabButtons.forEach(function (btn) {
                    btn.classList.remove('active');
                    btn.setAttribute('aria-selected', 'false');
                });
                tabPanes.forEach(function (pane) {
                    pane.classList.remove('active');
                });

                this.classList.add('active');
                this.setAttribute('aria-selected', 'true');

                var pane = document.getElementById(state.tab + '-pane');
                if (pane) pane.classList.add('active');

                document.querySelectorAll('.matiere-tab-btn').forEach(function (btn) {
                    var isAll = btn.getAttribute('data-matiere') === 'all';
                    btn.classList.toggle('active', isAll);
                    btn.setAttribute('aria-selected', isAll ? 'true' : 'false');
                });

                applyFilters();

                if (typeof window.layoutTabsOverflowNav === 'function') {
                    window.layoutTabsOverflowNav();
                }
            });
        });
    }

    function initMatiereTabs() {
        document.querySelectorAll('.matiere-tab-btn').forEach(function (button) {
            button.addEventListener('click', function () {
                if (state.tab !== 'professeurs') return;

                state.matiere = this.getAttribute('data-matiere') || 'all';

                document.querySelectorAll('.matiere-tab-btn').forEach(function (btn) {
                    btn.classList.remove('active');
                    btn.setAttribute('aria-selected', 'false');
                });
                this.classList.add('active');
                this.setAttribute('aria-selected', 'true');

                applyFilters();

                if (typeof window.layoutTabsOverflowNav === 'function') {
                    window.layoutTabsOverflowNav();
                }
            });
        });
    }

    function initToolbar() {
        var searchInput = document.getElementById('persSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                state.search = this.value.trim().toLowerCase();
                applyFilters();
            });
        }

        document.querySelectorAll('[data-pers-filter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('[data-pers-filter]').forEach(function (b) {
                    b.classList.remove('active');
                });
                this.classList.add('active');
                state.status = this.getAttribute('data-pers-filter');
                applyFilters();
            });
        });
    }

    function getActivePane() {
        return document.querySelector('.pers-tabs-content .tab-pane.active');
    }

    function cardMatches(card) {
        var actif = card.getAttribute('data-actif') === '1';
        var searchBlob = (card.getAttribute('data-search') || '').toLowerCase();
        var matiere = card.getAttribute('data-matiere') || '';

        if (state.status === 'active' && !actif) return false;
        if (state.status === 'inactive' && actif) return false;
        if (state.search && searchBlob.indexOf(state.search) === -1) return false;
        if (state.tab === 'professeurs' && state.matiere !== 'all' && matiere !== state.matiere) {
            return false;
        }
        return true;
    }

    function applyFilters() {
        var pane = getActivePane();
        if (!pane) return;

        var cards = pane.querySelectorAll('.pers-member-card');
        var visible = 0;

        cards.forEach(function (card) {
            var show = cardMatches(card);
            card.classList.toggle('pers-hidden', !show);
            if (show) visible += 1;
        });

        var emptyEl = document.getElementById(state.tab + '-empty-filter');
        if (emptyEl) {
            emptyEl.hidden = visible > 0 || cards.length === 0;
        }

        var resultsLine = document.getElementById('persResultsLine');
        if (resultsLine) {
            var filtering = state.search || state.status !== 'all' || (state.tab === 'professeurs' && state.matiere !== 'all');
            if (filtering && cards.length > 0) {
                resultsLine.textContent = visible + ' résultat' + (visible > 1 ? 's' : '') + ' dans cet onglet';
            } else {
                resultsLine.textContent = '';
            }
        }
    }

    window.searchPersonnel = function (query) {
        var input = document.getElementById('persSearchInput');
        if (input) input.value = query;
        state.search = (query || '').trim().toLowerCase();
        applyFilters();
    };

    window.filterPersonnelByType = function () {
        applyFilters();
    };
})();
