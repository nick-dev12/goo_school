/**
 * Gestion des bulletins — navigation onglets (UI v2)
 */

(function () {
  'use strict';

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.tab-button').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId) {
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
    });

    var subBtn = container.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }
    var target = document.getElementById(classeId);
    if (target) target.classList.add('active');

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  function restoreClasseFromUrl() {
    var classeId = new URLSearchParams(window.location.search).get('classe_id');
    if (!classeId) return;

    var classeContent = document.getElementById('classe-' + classeId);
    if (!classeContent) return;

    var tabPanel = classeContent.closest('.tab-panel');
    if (!tabPanel) return;

    window.switchMainTab(tabPanel.id);

    setTimeout(function () {
      var subBtn = tabPanel.querySelector('[data-subtab="classe-' + classeId + '"]');
      if (subBtn) {
        window.switchClasseTab({ stopPropagation: function () {}, target: subBtn, currentTarget: subBtn }, 'classe-' + classeId);
        classeContent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 80);
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
    restoreClasseFromUrl();
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
