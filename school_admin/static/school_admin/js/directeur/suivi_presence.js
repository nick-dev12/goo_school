/**
 * Suivi présence — navigation onglets + modales (UI v2, Vague 3)
 */

(function () {
  'use strict';

  var SP_STORAGE_KEY = 'directeur:suivi-presence';

  function spSyncPeriodeStore() {
    if (!window.directeurTabStorage) return;
    var params = new URLSearchParams(window.location.search);
    window.directeurTabStorage.syncUrlAndStore(SP_STORAGE_KEY, {
      periode: params.get('periode') || '',
    });
  }

  window.updatePresenceNavUrl = function () {
    var params = new URLSearchParams(window.location.search);
    var niveauBtn = document.querySelector('.tab-btn.active[data-niveau-key]');
    var panel = document.querySelector('.tab-content-panel.active');
    var classeBtn = panel
      ? panel.querySelector('.classe-subtab-btn.active[data-classe-id]')
      : document.querySelector('.classe-subtab-btn.active[data-classe-id]');

    if (niveauBtn) {
      params.set('niveau', niveauBtn.getAttribute('data-niveau-key') || '');
      params.delete('tab');
    }
    if (classeBtn) {
      params.set('classe', classeBtn.getAttribute('data-classe-id') || '');
    }

    document.querySelectorAll('.sp-periodes-bar .periode-tab').forEach(function (link) {
      var url = new URL(link.href, window.location.origin);
      if (niveauBtn) {
        url.searchParams.set('niveau', niveauBtn.getAttribute('data-niveau-key') || '');
        url.searchParams.delete('tab');
      }
      if (classeBtn) {
        url.searchParams.set('classe', classeBtn.getAttribute('data-classe-id') || '');
      }
      link.href = url.pathname + '?' + url.searchParams.toString();
    });

    spSyncPeriodeStore();
    history.replaceState({}, '', window.location.pathname + '?' + params.toString());
  };

  window.switchMainTab = function (tabId, btn) {
    document.querySelectorAll('.tab-content-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }
    var targetBtn = btn || document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
    }

    if (panel) {
      var activeClasseBtn = panel.querySelector('.classe-subtab-btn.active');
      if (!activeClasseBtn && panel.querySelector('.classe-subtab-btn')) {
        var firstBtn = panel.querySelector('.classe-subtab-btn');
        var firstContent = panel.querySelector('.classe-subtab-content');
        panel.querySelectorAll('.classe-subtab-content').forEach(function (c) {
          c.classList.remove('active');
          c.hidden = true;
        });
        panel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
          b.classList.remove('active');
          b.setAttribute('aria-selected', 'false');
        });
        firstBtn.classList.add('active');
        firstBtn.setAttribute('aria-selected', 'true');
        if (firstContent) {
          firstContent.classList.add('active');
          firstContent.hidden = false;
        }
        var numericId = firstContent ? firstContent.id.replace('classe-', '') : null;
        if (numericId && typeof window.filterPresenceStudents === 'function') {
          window.filterPresenceStudents(numericId);
        }
      }
    }

    window.updatePresenceNavUrl();
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
      content.hidden = true;
    });
    parentPanel.querySelectorAll('.classe-subtab-btn').forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });

    var content = document.getElementById(classeId);
    if (content) {
      content.classList.add('active');
      content.hidden = false;
    }

    var subBtn = parentPanel.querySelector('.classe-subtab-btn[data-subtab="' + classeId + '"]');
    if (subBtn) {
      subBtn.classList.add('active');
      subBtn.setAttribute('aria-selected', 'true');
    }

    window.updatePresenceNavUrl();

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

  function spRestorePeriodeFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (params.has('periode')) {
      spSyncPeriodeStore();
      return false;
    }
    var stored = window.directeurTabStorage.readStore(SP_STORAGE_KEY);
    if (stored.periode) {
      params.set('periode', stored.periode);
      window.location.replace(window.location.pathname + '?' + params.toString());
      return true;
    }
    return false;
  }

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
    if (spRestorePeriodeFromStorage()) {
      return;
    }
    if (typeof window.enhanceDirecteurNiveauClasseTabs === 'function') {
      window.enhanceDirecteurNiveauClasseTabs({ storageKey: SP_STORAGE_KEY + ':niveau-classe' });
    } else {
      spSyncPeriodeStore();
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
