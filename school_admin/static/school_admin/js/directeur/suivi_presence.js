/**
 * Suivi présence — navigation onglets + modale sanction (UI v2)
 */

(function () {
  'use strict';

  window.updatePresenceNavUrl = function (tabId, classeId) {
    var params = new URLSearchParams(window.location.search);
    params.set('tab', tabId);
    if (classeId) {
      params.set('classe', classeId.replace('classe-', ''));
    }
    document.querySelectorAll('.sp-periodes-bar .periode-tab').forEach(function (link) {
      var url = new URL(link.href, window.location.origin);
      url.searchParams.set('tab', tabId);
      if (classeId) {
        url.searchParams.set('classe', classeId.replace('classe-', ''));
      }
      link.href = url.pathname + '?' + url.searchParams.toString();
    });
    history.replaceState({}, '', window.location.pathname + '?' + params.toString());
  };

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.tab-content-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');
    var targetBtn = btn || document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }

    var activeClasseId = null;
    if (panel) {
      var activeClasseContent = panel.querySelector('.classe-subtab-content.active');
      if (!panel.querySelector('.classe-subtab-btn.active') && panel.querySelector('.classe-subtab-btn')) {
        var firstBtn = panel.querySelector('.classe-subtab-btn');
        var firstContent = panel.querySelector('.classe-subtab-content');
        firstBtn.classList.add('active');
        firstBtn.setAttribute('aria-selected', 'true');
        if (firstContent) firstContent.classList.add('active');
        activeClasseId = firstContent ? firstContent.id : null;
      } else if (activeClasseContent) {
        activeClasseId = activeClasseContent.id;
      }
    }
    window.updatePresenceNavUrl(tabId, activeClasseId);
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.switchClasseTab = function (event, classeId) {
    if (event) event.stopPropagation();
    var parentPanel = event && event.target
      ? event.target.closest('.tab-content-panel')
      : document.getElementById(classeId);
    if (parentPanel && !parentPanel.classList.contains('tab-content-panel')) {
      parentPanel = parentPanel.closest('.tab-content-panel');
    }
    if (!parentPanel) return;

    parentPanel.querySelectorAll('.classe-subtab-content').forEach(function (content) {
      content.classList.remove('active');
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var content = document.getElementById(classeId);
    if (content) content.classList.add('active');

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }

    window.updatePresenceNavUrl(parentPanel.id, classeId);

    var numericId = classeId.replace('classe-', '');
    if (typeof window.filterPresenceStudents === 'function') {
      window.filterPresenceStudents(numericId);
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  };

  window.ouvrirModalSanction = function (eleveId, eleveNom, classeId) {
    var eleveInput = document.getElementById('eleveIdInput');
    var classeInput = document.getElementById('classeIdInput');
    var eleveNomEl = document.getElementById('eleveNomModal');
    var dateInput = document.getElementById('date_sanction');
    var modal = document.getElementById('modalSanction');
    if (!modal) return;
    if (eleveInput) eleveInput.value = eleveId;
    if (classeInput) classeInput.value = classeId;
    if (eleveNomEl) eleveNomEl.textContent = eleveNom;
    if (dateInput) dateInput.value = new Date().toISOString().split('T')[0];
    modal.style.display = 'block';
  };

  window.fermerModalSanction = function () {
    var modal = document.getElementById('modalSanction');
    if (!modal) return;
    var form = modal.querySelector('form');
    if (form) form.reset();
    modal.style.display = 'none';
  };

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.tab-btn[data-tab]');
    if (tabBtn) {
      window.switchMainTab(tabBtn.getAttribute('data-tab'), tabBtn);
      return;
    }
    var classeBtn = event.target.closest('.classe-subtab-btn[data-subtab]');
    if (classeBtn) {
      window.switchClasseTab(event, classeBtn.getAttribute('data-subtab'));
      return;
    }
    var modal = document.getElementById('modalSanction');
    if (modal && event.target === modal) {
      window.fermerModalSanction();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
