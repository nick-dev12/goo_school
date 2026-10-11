/**
 * Tableau de bord directeur — onglets activités + persistance (UI v2, Vague 4)
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:dashboard';
  var FILTER_FIELDS = ['activite', 'vue', 'cycle', 'classe', 'periode', 'filiere'];
  var TAB_SELECTOR = '.dbd-activity-tab[data-tab]';
  var PANEL_SELECTOR = '.dbd-tabs-content .tab-panel';

  function persistDashboardState(extra) {
    if (!window.directeurTabStorage) return;
    var params = new URLSearchParams(window.location.search);
    var values = {};
    FILTER_FIELDS.forEach(function (name) {
      values[name] = params.get(name) || '';
    });
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        values[key] = extra[key] || '';
      });
    }
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, values);
  }

  function persistActivite(activite) {
    persistDashboardState({ activite: activite || '' });
  }

  function switchActivityTab(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll(PANEL_SELECTOR).forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll(TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }

    var targetBtn = btn || document.querySelector(TAB_SELECTOR + '[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
      if (!opts.skipPersist) {
        persistActivite(targetBtn.getAttribute('data-activite') || '');
      }
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }

    if (tabId === 'tab-absences' && typeof window.DBD_initAbsencesCharts === 'function') {
      window.requestAnimationFrame(function () {
        window.DBD_initAbsencesCharts({ force: true });
      });
    }
  }

  function restoreActiviteFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
    var missingCore = !params.has('activite') && stored.activite;
    if (missingCore) {
      FILTER_FIELDS.forEach(function (name) {
        if (!params.has(name) && stored[name]) {
          params.set(name, stored[name]);
        }
      });
      window.location.replace(window.location.pathname + '?' + params.toString());
      return true;
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, FILTER_FIELDS);
    var activite = params.get('activite') || 'absences';
    var tabId = 'tab-' + activite;
    var btn = document.querySelector(TAB_SELECTOR + '[data-activite="' + CSS.escape(activite) + '"]');
    switchActivityTab(tabId, btn, { skipPersist: true });
    persistActivite(activite);
    persistDashboardState();
    return false;
  }

  window.switchActivityTab = switchActivityTab;

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreActiviteFromStorage()) {
      return;
    }

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

    var absPanel = document.getElementById('tab-absences');
    if (absPanel && !absPanel.hidden && typeof window.DBD_initAbsencesCharts === 'function') {
      window.DBD_initAbsencesCharts();
    }
  });
})();
