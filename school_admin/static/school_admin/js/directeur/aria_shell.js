/**
 * Aria — coquille de l'espace direction : feuille « Menu » sur mobile, raccourci de
 * recherche et installation PWA.
 */
(function () {
  'use strict';

  var root = document.documentElement;

  function isVisible(el) {
    return !!(el && el.getClientRects().length);
  }

  function syncSheetWithDock() {
    var dock = document.querySelector('.ax-dock');
    var sheet = document.getElementById('axSheet');
    if (!dock || !sheet) return;
    var shown = Object.create(null);
    dock.querySelectorAll('a.ax-dock__item').forEach(function (item) {
      if (!isVisible(item)) return;
      shown[item.pathname] = true;
    });
    sheet.querySelectorAll('a.ax-nav__link, a.ex-tile').forEach(function (link) {
      if (shown[link.pathname]) link.setAttribute('hidden', '');
      else link.removeAttribute('hidden');
    });
    sheet.querySelectorAll('.ax-nav__group').forEach(function (group) {
      if (group.querySelector('a.ax-nav__link:not([hidden])')) group.removeAttribute('hidden');
      else group.setAttribute('hidden', '');
    });
  }

  function openSheet() {
    syncSheetWithDock();
    root.classList.add('ax-sheet-open');
    var btn = document.getElementById('axMoreBtn');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    var sheet = document.getElementById('axSheet');
    if (sheet) sheet.setAttribute('aria-hidden', 'false');
    var first = sheet && (
      sheet.querySelector('.ax-nav a.ax-nav__link:not([hidden]), .ex-sheet-grid a.ex-tile:not([hidden])') ||
      sheet.querySelector('button')
    );
    if (first) first.focus({ preventScroll: true });
  }

  function closeSheet() {
    root.classList.remove('ax-sheet-open');
    var btn = document.getElementById('axMoreBtn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    var sheet = document.getElementById('axSheet');
    if (sheet) sheet.setAttribute('aria-hidden', 'true');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var moreBtn = document.getElementById('axMoreBtn');
    if (moreBtn) moreBtn.addEventListener('click', openSheet);
    syncSheetWithDock();
    window.addEventListener('resize', syncSheetWithDock);
    document.querySelectorAll('[data-ax-sheet-close]').forEach(function (el) {
      el.addEventListener('click', closeSheet);
    });

    var search = document.getElementById('axSearchInput');
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && root.classList.contains('ax-sheet-open')) {
        closeSheet();
        return;
      }
      if (!search) return;
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test((event.target && event.target.tagName) || '') ||
        (event.target && event.target.isContentEditable);
      if ((event.key === 'k' || event.key === 'K') && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        search.focus();
        search.select();
      } else if (event.key === '/' && !typing) {
        event.preventDefault();
        search.focus();
      }
    });

    // Installation PWA
    var pwaBtn = document.getElementById('pwa-install-btn');
    var deferredPrompt = null;
    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      deferredPrompt = e;
      if (pwaBtn && !window.matchMedia('(display-mode: standalone)').matches) {
        pwaBtn.style.display = 'inline-flex';
      }
    });
    if (pwaBtn) {
      pwaBtn.addEventListener('click', function (e) {
        e.preventDefault();
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function () {
          pwaBtn.style.display = 'none';
          deferredPrompt = null;
        });
      });
    }
    window.addEventListener('appinstalled', function () {
      if (pwaBtn) pwaBtn.style.display = 'none';
      deferredPrompt = null;
    });

    // Badge de notifications : valeur la plus récente connue du navigateur.
    var badgeHost = document.getElementById('axNotifBtn');
    try {
      var stored = window.localStorage.getItem('notifications_directeur_non_lues');
      if (badgeHost && stored !== null) {
        var count = parseInt(stored, 10) || 0;
        var badge = badgeHost.querySelector('.ax-dot-badge');
        if (count > 0) {
          if (!badge) {
            badge = document.createElement('span');
            badge.className = 'ax-dot-badge';
            badgeHost.appendChild(badge);
          }
          badge.textContent = count > 99 ? '99+' : String(count);
        } else if (badge) {
          badge.remove();
        }
      }
    } catch (e) {
      /* stockage indisponible */
    }
  });

  // Compatibilité avec les anciens scripts qui ouvraient le menu complémentaire.
  window.directeurNavMenu = { open: openSheet, close: closeSheet };
})();
