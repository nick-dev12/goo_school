/**
 * Hub notes primaire — overflow, persistance URL + localStorage (Vague 1)
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'professeur:notes-primaire';
  var FIELDS = ['periode', 'classe', 'matiere', 'vue'];

  function persistFromUrl() {
    if (!window.professeurTabStorage) return;
    var params = new URLSearchParams(window.location.search);
    var values = {};
    FIELDS.forEach(function (name) {
      values[name] = params.get(name) || '';
    });
    window.professeurTabStorage.syncUrlAndStore(STORAGE_KEY, values);
  }

  function restoreFromStore() {
    if (!window.professeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    var missing = FIELDS.some(function (name) {
      return !params.has(name) || params.get(name) === '';
    });
    if (!missing) {
      window.professeurTabStorage.mergeUrlFromStore(STORAGE_KEY, FIELDS);
      persistFromUrl();
      return false;
    }
    var stored = window.professeurTabStorage.readStore(STORAGE_KEY);
    var next = new URLSearchParams(window.location.search);
    var changed = false;
    FIELDS.forEach(function (name) {
      if ((!next.has(name) || next.get(name) === '') && stored[name]) {
        next.set(name, String(stored[name]));
        changed = true;
      }
    });
    if (changed) {
      window.location.replace(window.location.pathname + '?' + next.toString());
      return true;
    }
    window.professeurTabStorage.mergeUrlFromStore(STORAGE_KEY, FIELDS);
    persistFromUrl();
    return false;
  }

  function layoutOverflow() {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function filterReleveRows() {
    var input = document.getElementById('notesHubSearchInput');
    var table = document.querySelector('#notesReleveTable tbody');
    if (!input || !table) return;
    var term = input.value.trim().toLowerCase();
    table.querySelectorAll('tr').forEach(function (row) {
      var text = row.textContent.toLowerCase();
      row.hidden = term.length > 0 && text.indexOf(term) === -1;
    });
  }

  function bindHubLinks() {
    document.querySelectorAll('.notes-hub-tab-link, .notes-hub-vue-btn').forEach(function (link) {
      link.addEventListener('click', function () {
        persistFromUrl();
      });
    });
  }

  function bindEvalModifier() {
    document.querySelectorAll('[data-eval-modifier]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var evaluationId = btn.getAttribute('data-eval-modifier');
        if (!evaluationId || typeof window.ouvrirModalModificationEvalHub !== 'function') {
          return;
        }
        window.ouvrirModalModificationEvalHub(evaluationId);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreFromStore()) {
      return;
    }
    bindHubLinks();
    bindEvalModifier();
    layoutOverflow();
    var searchInput = document.getElementById('notesHubSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', filterReleveRows);
    }
    window.addEventListener('resize', layoutOverflow);

    var alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
      setTimeout(function () {
        alerts.forEach(function (alert) {
          alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
          alert.style.opacity = '0';
          alert.style.transform = 'translateY(-20px)';
          setTimeout(function () {
            alert.remove();
          }, 500);
        });
      }, 5000);
    }
  });
})();
