/**
 * Tableau de bord directeur — onglets activités (UI v2)
 */

(function () {
  'use strict';

  var TAB_SELECTOR = '.dbd-activity-tab[data-tab]';
  var PANEL_SELECTOR = '.dbd-tabs-content .tab-panel';

  function switchActivityTab(tabId, btn) {
    document.querySelectorAll(PANEL_SELECTOR).forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll(TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
    }

    var targetBtn = btn || document.querySelector(TAB_SELECTOR + '[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  window.switchActivityTab = switchActivityTab;

  document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('click', function (event) {
      var btn = event.target.closest(TAB_SELECTOR);
      if (!btn) {
        return;
      }
      var tabId = btn.getAttribute('data-tab');
      if (tabId) {
        switchActivityTab(tabId, btn);
      }
    });

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
