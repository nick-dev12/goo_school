/**
 * Détail élève — onglets principaux + sous-onglets avec overflow (UI v2)
 */
(function () {
  'use strict';

  function layoutOverflow() {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function setPanelVisible(panel, show) {
    if (!panel) return;
    panel.classList.toggle('active', show);
    panel.hidden = !show;
  }

  window.showTab = function (tabName, btn) {
    document.querySelectorAll('.ded-tab-panel, .tab-panel').forEach(function (panel) {
      setPanelVisible(panel, panel.id === tabName + '-tab');
    });

    document.querySelectorAll('[data-ded-tab]').forEach(function (button) {
      var active = button.getAttribute('data-ded-tab') === tabName;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    if (btn) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
    }

    layoutOverflow();
  };

  window.showSubTab = function (subTabName, btn) {
    var parentTab = btn
      ? btn.closest('.tab-panel, .ded-tab-panel')
      : document.getElementById(subTabName)?.closest('.tab-panel, .ded-tab-panel');

    if (!parentTab) return;

    parentTab.querySelectorAll('.sub-tab-content, .ded-sub-panel').forEach(function (content) {
      setPanelVisible(content, content.id === subTabName);
    });

    parentTab.querySelectorAll('[data-ded-subtab]').forEach(function (button) {
      var active = button.getAttribute('data-ded-subtab') === subTabName;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });

    if (btn) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
    }

    layoutOverflow();
  };

  function initDedTabs() {
    var mainZone = document.querySelector('[data-ded-main-tabs]');
    if (mainZone) {
      mainZone.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-ded-tab]');
        if (!btn || !mainZone.contains(btn)) return;
        window.showTab(btn.getAttribute('data-ded-tab'), btn);
      });
    }

    document.querySelectorAll('[data-ded-subtabs-zone]').forEach(function (zone) {
      zone.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-ded-subtab]');
        if (!btn || !zone.contains(btn)) return;
        window.showSubTab(btn.getAttribute('data-ded-subtab'), btn);
      });
    });

    document.querySelectorAll('.ded-tab-panel.tab-panel').forEach(function (panel, index) {
      if (index === 0) {
        panel.classList.add('active');
        panel.hidden = false;
      } else {
        panel.classList.remove('active');
        panel.hidden = true;
      }
    });

    layoutOverflow();
    window.addEventListener('resize', layoutOverflow);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDedTabs);
  } else {
    initDedTabs();
  }
})();
