/**
 * Convocations de classe — toggle liste élèves (UI v2)
 */

(function () {
  'use strict';

  document.addEventListener('click', function (event) {
    var toggleBtn = event.target.closest('[data-cvl-toggle-eleves]');
    if (!toggleBtn) return;

    var card = toggleBtn.closest('[data-cvl-card]');
    if (!card) return;

    var panel = card.querySelector('[data-cvl-eleves-panel]');
    if (!panel) return;

    var isOpen = panel.classList.contains('is-open');

    card.querySelectorAll('[data-cvl-eleves-panel]').forEach(function (p) {
      p.classList.remove('is-open');
      p.setAttribute('hidden', '');
    });
    card.querySelectorAll('[data-cvl-toggle-eleves]').forEach(function (btn) {
      btn.setAttribute('aria-expanded', 'false');
    });

    if (!isOpen) {
      panel.classList.add('is-open');
      panel.removeAttribute('hidden');
      toggleBtn.setAttribute('aria-expanded', 'true');
    }
  });
})();
