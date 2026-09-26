/**
 * Onglets principaux Matières / Modules
 */
(function () {
  function initMatieresMainTabs() {
    var root = document.querySelector('[data-matieres-main-tabs]');
    if (!root) return;

    var buttons = root.querySelectorAll('.matieres-main-tab-btn');
    var panels = document.querySelectorAll('[data-matieres-main-panel]');
    var addModuleHeader = document.getElementById('addModuleBtnHeader');

    function activateTab(target) {
      buttons.forEach(function (btn) {
        var active = btn.getAttribute('data-main-tab') === target;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      panels.forEach(function (panel) {
        var show = panel.getAttribute('data-matieres-main-panel') === target;
        panel.classList.toggle('is-active', show);
        if (show) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', 'hidden');
        }
      });
      if (addModuleHeader) {
        addModuleHeader.hidden = target !== 'modules';
      }
      if (window.directeurTabStorage) {
        window.directeurTabStorage.syncUrlAndStore('directeur:liste-matieres:main', {
          tab: target === 'matieres' ? '' : target,
        });
      } else if (window.history && window.history.replaceState) {
        var url = new URL(window.location.href);
        if (target === 'modules') {
          url.searchParams.set('tab', 'modules');
        } else {
          url.searchParams.delete('tab');
          url.searchParams.delete('ouvrir_modal');
          url.searchParams.delete('department');
          url.searchParams.delete('nom');
        }
        window.history.replaceState({}, '', url.toString());
      }
    }

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        activateTab(btn.getAttribute('data-main-tab'));
      });
    });

    var initial = root.getAttribute('data-initial-tab') || 'matieres';
    if (window.directeurTabStorage) {
      var sel = window.directeurTabStorage.mergeUrlFromStore('directeur:liste-matieres:main', ['tab']);
      if (sel.tab) initial = sel.tab;
    }
    activateTab(initial);
  }

  document.addEventListener('DOMContentLoaded', initMatieresMainTabs);
})();
