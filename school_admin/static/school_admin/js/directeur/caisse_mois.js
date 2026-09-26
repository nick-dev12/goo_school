/**
 * Caisse du mois — onglets entrées/sorties + persistance mois/vue (Vague 5)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:caisse-mois';
  var TAB_SELECTOR = '.caisse-vue-tab[data-tab]';

  function persistState(vue, mois) {
    if (!window.directeurTabStorage) return;
    var values = { vue: vue || 'entrees' };
    if (mois) values.mois = mois;
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, values);
  }

  function switchVuePanel(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.caisse-tabs-content .tab-panel').forEach(function (panel) {
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
        var moisInput = document.getElementById('caisse-mois');
        persistState(targetBtn.getAttribute('data-vue') || 'entrees', moisInput ? moisInput.value : '');
        syncMonthFormVue(targetBtn.getAttribute('data-vue'));
      }
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function syncMonthFormVue(vue) {
    var form = document.getElementById('caisseMonthForm');
    if (!form) return;
    var hidden = form.querySelector('input[name="vue"]');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'vue';
      form.appendChild(hidden);
    }
    hidden.value = vue || 'entrees';
  }

  function restoreFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
    var needsReload = false;

    if (!params.has('vue') && stored.vue) {
      params.set('vue', stored.vue);
      needsReload = true;
    }
    if (!params.has('mois') && stored.mois) {
      params.set('mois', stored.mois);
      needsReload = true;
    }
    if (needsReload) {
      window.location.replace(window.location.pathname + '?' + params.toString());
      return true;
    }

    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['vue', 'mois']);
    var vue = params.get('vue') || 'entrees';
    var btn = document.querySelector(TAB_SELECTOR + '[data-vue="' + CSS.escape(vue) + '"]');
    if (btn) {
      switchVuePanel(btn.getAttribute('data-tab'), btn, { skipPersist: true });
      persistState(vue, params.get('mois') || '');
      syncMonthFormVue(vue);
    }
    return false;
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest(TAB_SELECTOR);
    if (tabBtn) {
      switchVuePanel(tabBtn.getAttribute('data-tab'), tabBtn);
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreFromStorage()) return;

    var moisInput = document.getElementById('caisse-mois');
    if (moisInput) {
      moisInput.addEventListener('change', function () {
        var params = new URLSearchParams(window.location.search);
        persistState(params.get('vue') || 'entrees', moisInput.value);
      });
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
