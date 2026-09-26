/**
 * Hub gestion établissement — sections, recherche, persistance (UI v2, Vague 4)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:gestion-etablissement';
  var TAB_SELECTOR = '.etab-section-tab[data-tab]';

  function persistSection(section) {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, {
      section: section || '',
    });
  }

  function restoreSection() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('section')) {
      var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
      if (stored.section) {
        params.set('section', stored.section);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['section']);
    var section = params.get('section') || 'structure';
    var btn = document.querySelector(TAB_SELECTOR + '[data-section="' + CSS.escape(section) + '"]');
    switchSectionTab(btn ? btn.getAttribute('data-tab') : 'tab-etab-structure', btn, { skipPersist: true });
    persistSection(section);
    return false;
  }

  function switchSectionTab(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.etab-tabs-content .tab-panel').forEach(function (panel) {
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
        persistSection(targetBtn.getAttribute('data-section') || '');
      }
    }

    filterCards();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function filterCards() {
    var input = document.getElementById('etabSearchInput');
    var term = input ? input.value.trim().toLowerCase() : '';
    var panel = document.querySelector('.etab-tabs-content .tab-panel.active');
    if (!panel) return;

    var cards = panel.querySelectorAll('.nav-link-card');
    var visible = 0;
    cards.forEach(function (card) {
      var blob = (card.getAttribute('data-etab-search') || '') + ' ' + card.textContent;
      blob = blob.toLowerCase();
      var show = !term || blob.indexOf(term) !== -1;
      card.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });

    var emptyId = panel.id === 'tab-etab-finances' ? 'etab-empty-finances' : 'etab-empty-structure';
    var emptyEl = document.getElementById(emptyId);
    if (emptyEl) {
      emptyEl.hidden = !term || visible > 0 || cards.length === 0;
    }
  }

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest(TAB_SELECTOR);
    if (tabBtn) {
      switchSectionTab(tabBtn.getAttribute('data-tab'), tabBtn);
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreSection()) {
      return;
    }
    var searchInput = document.getElementById('etabSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', filterCards);
    }
    filterCards();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
