/**
 * Liste classes — onglets catégories / filières / niveaux LMD + overflow
 */

(function () {
    'use strict';

    function layoutOverflow() {
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    }

    function slugifyClsCategory(text) {
        return text
            .toString()
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    function activateGclCategory(root, btn) {
        if (!root || !btn) return;

        var category = btn.getAttribute('data-category');
        var buttons = root.querySelectorAll('.cls-cat-btn');
        var panels = root.querySelectorAll('.gcl-cat-panel');

        buttons.forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var show = panel.getAttribute('data-category') === category;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
        });

        layoutOverflow();
    }

    function initGclCategoryTabs() {
        var root = document.querySelector('[data-gcl-cat-zone]');
        if (!root) return;

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.cls-cat-btn[data-category]');
            if (!btn || !root.contains(btn)) return;
            activateGclCategory(root, btn);
        });
    }

    function resetNiveauTabsInFiliere(filierePanel) {
        if (!filierePanel) return;
        var zone = filierePanel.querySelector('[data-gcl-niveau-zone]');
        if (!zone) return;

        var btns = zone.querySelectorAll('.gcl-niveau-tab');
        var panels = zone.querySelectorAll('.gcl-niveau-panel');
        btns.forEach(function (b, i) {
            var active = i === 0;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        panels.forEach(function (p, i) {
            var show = i === 0;
            p.classList.toggle('active', show);
            p.hidden = !show;
        });
    }

    function activateGclFiliereTab(root, btn) {
        if (!root || !btn) return;

        var idx = btn.getAttribute('data-filiere-idx');
        var buttons = root.querySelectorAll('.gcl-filiere-tab');
        var panels = root.querySelectorAll('.gcl-filiere-panel');

        buttons.forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var show = panel.getAttribute('data-filiere-idx') === idx;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
            if (show) {
                resetNiveauTabsInFiliere(panel);
            }
        });

        layoutOverflow();
    }

    function initGclFiliereTabs() {
        var root = document.querySelector('[data-gcl-filiere-zone]');
        if (!root) return;

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.gcl-filiere-tab[data-filiere-idx]');
            if (!btn || !root.contains(btn)) return;
            activateGclFiliereTab(root, btn);
        });
    }

    function activateGclNiveauTab(zone, btn) {
        if (!zone || !btn) return;

        var nidx = btn.getAttribute('data-niveau-idx');
        var buttons = zone.querySelectorAll('.gcl-niveau-tab');
        var panels = zone.querySelectorAll('.gcl-niveau-panel');

        buttons.forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var show = panel.getAttribute('data-niveau-idx') === nidx;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
        });

        layoutOverflow();
    }

    function initGclNiveauTabs() {
        document.querySelectorAll('[data-gcl-niveau-zone]').forEach(function (zone) {
            if (zone.dataset.gclNiveauInit === '1') return;
            zone.dataset.gclNiveauInit = '1';

            zone.addEventListener('click', function (event) {
                var btn = event.target.closest('.gcl-niveau-tab');
                if (!btn || !zone.contains(btn)) return;
                activateGclNiveauTab(zone, btn);
            });
        });
    }

    function bootGclTabs() {
        initGclCategoryTabs();
        initGclFiliereTabs();
        initGclNiveauTabs();
        layoutOverflow();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootGclTabs);
    } else {
        bootGclTabs();
    }

    window.gclSlugifyCategory = slugifyClsCategory;
})();
