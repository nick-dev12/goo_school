/**
 * Gestion du personnel — onglets, filtres, persistance (UI v2, Vague 4)
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:personnel';
  var CAT_TAB_SELECTOR = '.pers-cat-tab[data-tab]';

  var state = {
    tab: 'professeurs',
    matiere: 'all',
    status: 'all',
    search: '',
  };

  function readInitialStateFromDom() {
    var activeCat = document.querySelector(CAT_TAB_SELECTOR + '.active');
    if (activeCat) {
      state.tab = activeCat.getAttribute('data-tab') || 'professeurs';
    }
    var activeMatiere = document.querySelector('.pers-matiere-nav .matiere-tab-btn.active[data-matiere]');
    if (activeMatiere) {
      state.matiere = activeMatiere.getAttribute('data-matiere') || 'all';
    }
    var activeStatut = document.querySelector('.pers-filter-btn.active[data-pers-filter]');
    if (activeStatut) {
      state.status = activeStatut.getAttribute('data-pers-filter') || 'all';
    }
  }

  function persistState() {
    if (!window.directeurTabStorage) return;
    var ongletBtn = document.querySelector(CAT_TAB_SELECTOR + '.active[data-onglet]');
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, {
      onglet: ongletBtn ? ongletBtn.getAttribute('data-onglet') : state.tab,
      matiere: state.matiere,
      statut: state.status,
    });
  }

  function restoreFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('onglet')) {
      var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
      if (stored.onglet) {
        params.set('onglet', stored.onglet);
        if (stored.matiere) params.set('matiere', stored.matiere);
        if (stored.statut) params.set('statut', stored.statut);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['onglet', 'matiere', 'statut']);
    persistState();
    return false;
  }

  function switchCategoryTab(tabKey, btn) {
    state.tab = tabKey;
    if (tabKey !== 'professeurs') {
      state.matiere = 'all';
    }

    document.querySelectorAll(CAT_TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.pers-tabs-content .tab-pane').forEach(function (pane) {
      pane.classList.remove('active');
      pane.hidden = true;
    });

    if (btn) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
    }

    var pane = document.getElementById(tabKey + '-pane');
    if (pane) {
      pane.classList.add('active');
      pane.hidden = false;
    }

    if (tabKey === 'professeurs') {
      document.querySelectorAll('.pers-matiere-nav .matiere-tab-btn').forEach(function (b) {
        var isAll = b.getAttribute('data-matiere') === state.matiere;
        b.classList.toggle('active', isAll);
        b.setAttribute('aria-selected', isAll ? 'true' : 'false');
      });
    }

    persistState();
    applyFilters();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function initCategoryTabs() {
    document.querySelectorAll(CAT_TAB_SELECTOR).forEach(function (button) {
      button.addEventListener('click', function () {
        switchCategoryTab(this.getAttribute('data-tab') || 'professeurs', this);
      });
    });
  }

  function initMatiereTabs() {
    document.querySelectorAll('.pers-matiere-nav .matiere-tab-btn').forEach(function (button) {
      button.addEventListener('click', function () {
        if (state.tab !== 'professeurs') return;
        state.matiere = this.getAttribute('data-matiere') || 'all';
        document.querySelectorAll('.pers-matiere-nav .matiere-tab-btn').forEach(function (btn) {
          btn.classList.remove('active');
          btn.setAttribute('aria-selected', 'false');
        });
        this.classList.add('active');
        this.setAttribute('aria-selected', 'true');
        persistState();
        applyFilters();
        if (typeof window.layoutTabsOverflowNav === 'function') {
          window.layoutTabsOverflowNav();
        }
      });
    });
  }

  function initToolbar() {
    var searchInput = document.getElementById('persSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        state.search = this.value.trim().toLowerCase();
        applyFilters();
      });
    }

    document.querySelectorAll('[data-pers-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('[data-pers-filter]').forEach(function (b) {
          b.classList.remove('active');
        });
        this.classList.add('active');
        state.status = this.getAttribute('data-pers-filter');
        persistState();
        applyFilters();
      });
    });
  }

  function getActivePane() {
    return document.querySelector('.pers-tabs-content .tab-pane.active');
  }

  function cardMatches(card) {
    var actif = card.getAttribute('data-actif') === '1';
    var searchBlob = (card.getAttribute('data-search') || '').toLowerCase();
    var matiere = card.getAttribute('data-matiere') || '';

    if (state.status === 'active' && !actif) return false;
    if (state.status === 'inactive' && actif) return false;
    if (state.search && searchBlob.indexOf(state.search) === -1) return false;
    if (state.tab === 'professeurs' && state.matiere !== 'all' && matiere !== state.matiere) {
      return false;
    }
    return true;
  }

  function applyFilters() {
    var pane = getActivePane();
    if (!pane) return;

    var cards = pane.querySelectorAll('.pers-member-card');
    var visible = 0;

    cards.forEach(function (card) {
      var show = cardMatches(card);
      card.classList.toggle('pers-hidden', !show);
      if (show) visible += 1;
    });

    var emptyEl = document.getElementById(state.tab + '-empty-filter');
    if (emptyEl) {
      emptyEl.hidden = visible > 0 || cards.length === 0;
    }

    var resultsLine = document.getElementById('persResultsLine');
    if (resultsLine) {
      var filtering = state.search || state.status !== 'all' || (state.tab === 'professeurs' && state.matiere !== 'all');
      if (filtering && cards.length > 0) {
        resultsLine.textContent = visible + ' résultat' + (visible > 1 ? 's' : '') + ' dans cet onglet';
      } else {
        resultsLine.textContent = '';
      }
    }
  }

  window.searchPersonnel = function (query) {
    var input = document.getElementById('persSearchInput');
    if (input) input.value = query;
    state.search = (query || '').trim().toLowerCase();
    applyFilters();
  };

  window.filterPersonnelByType = function () {
    applyFilters();
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreFromStorage()) {
      return;
    }
    readInitialStateFromDom();
    initCategoryTabs();
    initMatiereTabs();
    initToolbar();
    applyFilters();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
