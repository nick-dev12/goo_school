/**
 * Liste matières / modules — onglets filières / niveaux + overflow
 */
(function () {
    'use strict';

    function layoutOverflow() {
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    }

    function resetNiveauTabsInFiliere(filierePanel) {
        if (!filierePanel) return;
        var zone = filierePanel.querySelector('[data-gml-niveau-zone]');
        if (!zone) return;

        var btns = zone.querySelectorAll('.gml-niveau-tab');
        var panels = zone.querySelectorAll('.gml-niveau-panel');
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

    function activateGmlFiliereTab(root, btn) {
        if (!root || !btn) return;

        var idx = btn.getAttribute('data-filiere-idx');
        var buttons = root.querySelectorAll('.gml-filiere-tab');
        var panels = root.querySelectorAll('.gml-filiere-panel');

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

    function initGmlFiliereTabs() {
        document.querySelectorAll('[data-gml-filiere-zone]').forEach(function (root) {
            if (root.dataset.gmlFiliereInit === '1') return;
            root.dataset.gmlFiliereInit = '1';

            root.addEventListener('click', function (event) {
                var btn = event.target.closest('.gml-filiere-tab[data-filiere-idx]');
                if (!btn || !root.contains(btn)) return;
                activateGmlFiliereTab(root, btn);
            });
        });
    }

    function activateGmlNiveauTab(zone, btn) {
        if (!zone || !btn) return;

        var nidx = btn.getAttribute('data-niveau-idx');
        var buttons = zone.querySelectorAll('.gml-niveau-tab');
        var panels = zone.querySelectorAll('.gml-niveau-panel');

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

    function initGmlNiveauTabs() {
        document.querySelectorAll('[data-gml-niveau-zone]').forEach(function (zone) {
            if (zone.dataset.gmlNiveauInit === '1') return;
            zone.dataset.gmlNiveauInit = '1';

            zone.addEventListener('click', function (event) {
                var btn = event.target.closest('.gml-niveau-tab');
                if (!btn || !zone.contains(btn)) return;
                activateGmlNiveauTab(zone, btn);
            });
        });
    }

    function activateGmlTypeTab(root, btn) {
        if (!root || !btn) return;
        var type = btn.getAttribute('data-type-tab');
        root.querySelectorAll('.gml-type-tab').forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        root.querySelectorAll('.gml-type-panel').forEach(function (panel) {
            var show = panel.getAttribute('data-type-pane') === type;
            panel.classList.toggle('active', show);
            panel.hidden = !show;
        });
        layoutOverflow();
    }

    function initGmlTypeTabs() {
        var root = document.querySelector('[data-gml-type-zone]');
        if (!root) return;

        root.addEventListener('click', function (event) {
            var btn = event.target.closest('.gml-type-tab[data-type-tab]');
            if (!btn || !root.contains(btn)) return;
            activateGmlTypeTab(root, btn);
        });
    }

    function bootGmlTabs() {
        initGmlFiliereTabs();
        initGmlNiveauTabs();
        initGmlTypeTabs();
        layoutOverflow();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootGmlTabs);
    } else {
        bootGmlTabs();
    }
})();
