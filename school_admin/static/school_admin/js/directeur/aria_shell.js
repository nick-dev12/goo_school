/**
 * Aria — coquille de l'espace direction : feuille « Menu » sur mobile, raccourci de
 * recherche et installation PWA.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  function openSheet() {
    root.classList.add('ax-sheet-open');
    var btn = document.getElementById('axMoreBtn');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    var sheet = document.getElementById('axSheet');
    if (sheet) sheet.setAttribute('aria-hidden', 'false');
    var first = sheet && sheet.querySelector('a, button');
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
