/**
 * Profil établissement — onglets + persistance URL (UI v2, Vague 4)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:profil-etablissement';
  var TAB_SELECTOR = '.profil-tab-btn[data-tab]';

  function updateActiveTabInputs(tabValue) {
    document.querySelectorAll('input[name="active_tab"]').forEach(function (input) {
      input.value = tabValue;
    });
  }

  function persistTab(tab) {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, { tab: tab || '' });
  }

  function switchProfilTab(link, opts) {
    opts = opts || {};
    var targetSelector = link.getAttribute('data-target');
    var tabValue = link.getAttribute('data-tab');
    if (!targetSelector || !tabValue) return;

    document.querySelectorAll(TAB_SELECTOR).forEach(function (btn) {
      btn.classList.remove('active');
      btn.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tabs-content .tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });

    link.classList.add('active');
    link.setAttribute('aria-selected', 'true');
    var targetPanel = document.querySelector(targetSelector);
    if (targetPanel) {
      targetPanel.classList.add('active');
      targetPanel.hidden = false;
    }

    updateActiveTabInputs(tabValue);
    if (!opts.skipPersist) {
      persistTab(tabValue);
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function restoreTab() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('tab')) {
      var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
      if (stored.tab) {
        params.set('tab', stored.tab);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['tab']);
    var tab = params.get('tab');
    if (tab) {
      var btn = document.querySelector(TAB_SELECTOR + '[data-tab="' + CSS.escape(tab) + '"]');
      if (btn) {
        switchProfilTab(btn, { skipPersist: true });
        persistTab(tab);
      }
    }
    return false;
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreTab()) {
      return;
    }

    document.querySelectorAll(TAB_SELECTOR).forEach(function (link) {
      link.addEventListener('click', function () {
        switchProfilTab(link);
      });
    });

    var currentActiveTab = document.querySelector(TAB_SELECTOR + '.active');
    if (currentActiveTab) {
      updateActiveTabInputs(currentActiveTab.getAttribute('data-tab'));
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
