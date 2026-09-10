/**
 * Affectation des professeurs — UI v2
 * Recherche, filtres, onglets matière, modals (POST Django côté serveur)
 */

(function () {
    'use strict';

    var state = {
        matiere: 'all',
        status: 'all',
        classe: '',
        search: ''
    };

    document.addEventListener('DOMContentLoaded', function () {
        initMatiereTabs();
        initToolbar();
        initProfessorCards();
        initAffectationFiliereSuperieur();
        initAffectationClasseFilter();
        applyAllFilters();

        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    });

    function initToolbar() {
        var searchInput = document.getElementById('affSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                state.search = this.value.trim().toLowerCase();
                applyAllFilters();
            });
        }

        document.querySelectorAll('[data-aff-filter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('[data-aff-filter]').forEach(function (b) {
                    b.classList.remove('active');
                });
                this.classList.add('active');
                state.status = this.getAttribute('data-aff-filter');
                applyAllFilters();
            });
        });

        var classeSelect = document.getElementById('affClasseFilter');
        if (classeSelect) {
            classeSelect.addEventListener('change', function () {
                state.classe = this.value;
                applyAllFilters();
            });
        }
    }

    function initMatiereTabs() {
        var tabButtons = document.querySelectorAll('.matiere-tab-btn');
        tabButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                state.matiere = this.getAttribute('data-matiere') || 'all';

                tabButtons.forEach(function (btn) {
                    btn.classList.remove('active');
                    btn.setAttribute('aria-selected', 'false');
                });
                this.classList.add('active');
                this.setAttribute('aria-selected', 'true');

                applyAllFilters();

                if (typeof window.layoutTabsOverflowNav === 'function') {
                    window.layoutTabsOverflowNav();
                }
            });
        });
    }

    function cardMatchesFilters(card) {
        var matiere = card.getAttribute('data-matiere') || '';
        var affected = card.getAttribute('data-affected') === '1';
        var classeIds = (card.getAttribute('data-classe-ids') || '').split(',').filter(Boolean);
        var searchBlob = (card.getAttribute('data-search') || '').toLowerCase();

        if (state.matiere !== 'all' && matiere !== state.matiere) {
            return false;
        }
        if (state.status === 'affected' && !affected) {
            return false;
        }
        if (state.status === 'pending' && affected) {
            return false;
        }
        if (state.classe && classeIds.indexOf(state.classe) === -1) {
            return false;
        }
        if (state.search && searchBlob.indexOf(state.search) === -1) {
            return false;
        }
        return true;
    }

    function applyAllFilters() {
        var cards = document.querySelectorAll('.aff-prof-card');
        var visiblePending = 0;
        var visibleOk = 0;

        cards.forEach(function (card) {
            var show = cardMatchesFilters(card);
            card.classList.toggle('aff-hidden', !show);
            if (show) {
                if (card.getAttribute('data-affected') === '1') {
                    visibleOk += 1;
                } else {
                    visiblePending += 1;
                }
            }
        });

        updateSection('affSectionPending', 'affEmptyPending', visiblePending);
        updateSection('affSectionOk', 'affEmptyOk', visibleOk);

        var countPending = document.getElementById('affCountPending');
        var countOk = document.getElementById('affCountOk');
        if (countPending) countPending.textContent = visiblePending;
        if (countOk) countOk.textContent = visibleOk;

        var resultsLine = document.getElementById('affResultsLine');
        if (resultsLine) {
            var total = visiblePending + visibleOk;
            if (state.search || state.status !== 'all' || state.classe || state.matiere !== 'all') {
                resultsLine.textContent = total + ' professeur' + (total > 1 ? 's' : '') + ' affiché' + (total > 1 ? 's' : '');
            } else {
                resultsLine.textContent = '';
            }
        }
    }

    function updateSection(sectionId, emptyId, visibleCount) {
        var section = document.getElementById(sectionId);
        var empty = document.getElementById(emptyId);
        if (!section) return;

        var hasCards = section.querySelectorAll('.aff-prof-card').length > 0;
        section.hidden = !hasCards;
        if (empty) {
            empty.hidden = visibleCount > 0 || !hasCards;
        }
    }

    function initProfessorCards() {
        /* Effets visuels gérés en CSS */
    }

    window.applyFilters = applyAllFilters;
    window.clearFilters = function () {
        state = { matiere: 'all', status: 'all', classe: '', search: '' };
        var searchInput = document.getElementById('affSearchInput');
        if (searchInput) searchInput.value = '';
        var classeSelect = document.getElementById('affClasseFilter');
        if (classeSelect) classeSelect.value = '';
        document.querySelectorAll('[data-aff-filter]').forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-aff-filter') === 'all');
        });
        document.querySelectorAll('.matiere-tab-btn').forEach(function (btn) {
            var isAll = btn.getAttribute('data-matiere') === 'all';
            btn.classList.toggle('active', isAll);
            btn.setAttribute('aria-selected', isAll ? 'true' : 'false');
        });
        applyAllFilters();
    };

    function initAffectationFiliereSuperieur() {
        document.querySelectorAll('.affectation-filiere-select').forEach(function (filSel) {
            var pid = filSel.getAttribute('data-professeur-id');
            var matSel = document.getElementById('matiere' + pid);
            if (!matSel) return;

            function syncFromFiliere() {
                var depId = filSel.value;
                matSel.querySelectorAll('option').forEach(function (opt) {
                    if (!opt.value) {
                        opt.hidden = !!depId;
                        opt.disabled = !!depId;
                        return;
                    }
                    var mdep = opt.getAttribute('data-department-id') || '';
                    var show = depId && mdep === depId;
                    opt.hidden = !show;
                    opt.disabled = !show;
                    if (!show && opt.selected) opt.selected = false;
                });
                if (!depId) {
                    matSel.value = '';
                    var ph = matSel.querySelector('option[value=""]');
                    if (ph) ph.selected = true;
                } else {
                    var curOpt = matSel.options[matSel.selectedIndex];
                    if (!curOpt || !curOpt.value || curOpt.disabled) {
                        var firstOk = Array.prototype.find.call(matSel.options, function (o) {
                            return o.value && !o.disabled;
                        });
                        if (firstOk) firstOk.selected = true;
                        else matSel.value = '';
                    }
                }
                filterClassesByMatiere(matSel);
            }

            filSel.addEventListener('change', syncFromFiliere);
        });
    }

    function initAffectationClasseFilter() {
        document.querySelectorAll('.affectation-matiere-select').forEach(function (matiereSelect) {
            matiereSelect.addEventListener('change', function () {
                filterClassesByMatiere(this);
            });
            filterClassesByMatiere(matiereSelect);
        });
    }

    window.filterClassesByMatiere = function (matiereSelect) {
        var professeurId = matiereSelect.getAttribute('data-professeur-id');
        var classeSelect = document.getElementById('classe' + professeurId);
        if (!classeSelect) return;

        var selectedOpt = matiereSelect.options[matiereSelect.selectedIndex];
        var classOptions = classeSelect.querySelectorAll('option');

        if (!selectedOpt || !selectedOpt.value) {
            classOptions.forEach(function (opt) {
                if (!opt.value) {
                    opt.style.display = '';
                    opt.disabled = false;
                    return;
                }
                opt.style.display = 'none';
                opt.disabled = true;
                opt.selected = false;
            });
            return;
        }

        var matiereDepId = selectedOpt.getAttribute('data-department-id') || '';
        var matiereClasseIdsStr = selectedOpt.getAttribute('data-classe-ids') || '';
        var matiereClasseIds = matiereClasseIdsStr
            ? matiereClasseIdsStr.split(',').filter(function (id) { return id.trim(); })
            : [];

        classOptions.forEach(function (opt) {
            if (!opt.value) {
                opt.style.display = '';
                opt.disabled = false;
                return;
            }
            var classeDepId = opt.getAttribute('data-department-id') || '';
            var classeId = opt.getAttribute('data-classe-id') || opt.value;
            var match = true;
            if (matiereDepId && classeDepId !== matiereDepId) match = false;
            if (matiereClasseIds.length > 0 && match) {
                match = matiereClasseIds.indexOf(classeId) >= 0;
            }
            opt.style.display = match ? '' : 'none';
            opt.disabled = !match;
            if (!match) opt.selected = false;
        });

        var currentClasseOpt = classeSelect.options[classeSelect.selectedIndex];
        if (currentClasseOpt && currentClasseOpt.disabled) {
            var firstVisible =
                classeSelect.querySelector('option[value=""]') ||
                classeSelect.querySelector('option:not([disabled])');
            if (firstVisible) classeSelect.value = firstVisible.value;
        }
    };

    window.toggleAffectations = function (professeurId) {
        var panel = document.getElementById('affectationsPanel' + professeurId);
        var overlay = document.getElementById('modalOverlay' + professeurId);

        if (!panel || !overlay) return;

        if (panel.style.display === 'none' || panel.style.display === '') {
            overlay.style.display = 'block';
            panel.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            var fil = document.getElementById('filiere' + professeurId);
            if (fil) {
                fil.value = '';
                fil.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                var mat = document.getElementById('matiere' + professeurId);
                if (mat) filterClassesByMatiere(mat);
            }

            setTimeout(function () {
                panel.classList.add('modal-active');
            }, 10);
        } else {
            panel.classList.remove('modal-active');
            setTimeout(function () {
                overlay.style.display = 'none';
                panel.style.display = 'none';
                document.body.style.overflow = '';
            }, 300);
        }
    };
})();
