/**
 * Gestion des bulletins — navigation onglets (UI v2)
 */

(function () {
  'use strict';

  var BUL_STORAGE_KEY = 'directeur:bulletins-notes';

  function bulPersistPeriode() {
    if (!window.directeurTabStorage) return;
    var params = new URLSearchParams(window.location.search);
    window.directeurTabStorage.syncUrlAndStore(BUL_STORAGE_KEY, {
      periode: params.get('periode') || '',
    });
  }

  window.switchMainTab = function (tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll('.tab-button').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }
    var targetBtn = btn || document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId, opts) {
    opts = opts || {};
    if (event) event.stopPropagation();
    var container = event && event.target
      ? event.target.closest('.tab-panel')
      : document.getElementById(classeId);
    if (container && !container.classList.contains('tab-panel')) {
      container = container.closest('.tab-panel');
    }
    if (!container) return;

    container.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    container.querySelectorAll('.classe-subtab-content').forEach(function (p) {
      p.classList.remove('active');
      p.hidden = true;
    });

    var subBtn = container.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    var target = document.getElementById(classeId);
    if (target) {
      target.classList.add('active');
      target.hidden = false;
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  function restoreLegacyClasseIdParam() {
    var params = new URLSearchParams(window.location.search);
    var legacy = params.get('classe_id');
    if (!legacy || params.get('classe')) return;
    params.set('classe', legacy);
    params.delete('classe_id');
    window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.tab-button[data-tab]');
    if (tabBtn) {
      window.switchMainTab(tabBtn.getAttribute('data-tab'), tabBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    restoreLegacyClasseIdParam();
    if (window.directeurTabStorage) {
      var stored = window.directeurTabStorage.mergeUrlFromStore(BUL_STORAGE_KEY, ['periode']);
      if (stored.periode && !new URLSearchParams(window.location.search).get('periode')) {
        /* mergeUrlFromStore already applied */
      }
    }
    if (typeof window.enhanceDirecteurNiveauClasseTabs === 'function') {
      window.enhanceDirecteurNiveauClasseTabs({ storageKey: BUL_STORAGE_KEY + ':niveau-classe' });
    }
    bulPersistPeriode();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
