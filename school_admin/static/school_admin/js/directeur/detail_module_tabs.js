/**
 * Détail module — délègue aux onglets gml (matieres_liste_tabs.js)
 */
(function () {
    'use strict';

    function bootDetailModuleTabs() {
        if (typeof window.layoutTabsOverflowNav === 'function') {
            window.layoutTabsOverflowNav();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootDetailModuleTabs);
    } else {
        bootDetailModuleTabs();
    }
})();
