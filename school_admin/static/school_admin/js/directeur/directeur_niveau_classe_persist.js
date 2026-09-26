/**
 * Persistance onglets niveau/classe — query string + localStorage (directeur UI).
 */
(function (global) {
  'use strict';

  function readSelection(storageKey) {
    var params = new global.URLSearchParams(global.location.search);
    var niveau = (params.get('niveau') || '').trim().toLowerCase();
    var classeRaw = params.get('classe');
    var classe = classeRaw ? String(parseInt(classeRaw, 10)) : '';

    if (!niveau && !classe) {
      try {
        var stored = JSON.parse(global.localStorage.getItem(storageKey) || 'null');
        if (stored && typeof stored === 'object') {
          niveau = (stored.niveau || '').trim().toLowerCase();
          if (stored.classe != null && stored.classe !== '') {
            classe = String(parseInt(stored.classe, 10));
          }
        }
      } catch (err) {
        /* ignore */
      }
    }
    if (classe === 'NaN') {
      classe = '';
    }
    return { niveau: niveau, classe: classe };
  }

  function activeFromDom() {
    var niveauBtn =
      document.querySelector('.matiere-tab-btn.active[data-niveau-key]') ||
      document.querySelector('[role="tab"].active[data-niveau-key]');
    var classeBtn =
      document.querySelector('.ele-niveau-panel:not([hidden]) .classe-subtab-btn.active[data-classe-id]') ||
      document.querySelector('.tab-panel.active .classe-subtab-btn.active[data-classe-id]') ||
      document.querySelector('.tab-panel:not([hidden]) .classe-subtab-btn.active[data-classe-id]') ||
      document.querySelector('.classe-subtab-btn.active[data-classe-id]');
    return {
      niveau: niveauBtn ? niveauBtn.getAttribute('data-niveau-key') || '' : '',
      classe: classeBtn ? String(classeBtn.getAttribute('data-classe-id') || '') : '',
    };
  }

  function writeSelection(storageKey, niveau, classe) {
    var sel = {
      niveau: niveau || activeFromDom().niveau,
      classe: classe || activeFromDom().classe,
    };
    if (!sel.niveau && !sel.classe) {
      return;
    }
    try {
      global.localStorage.setItem(
        storageKey,
        JSON.stringify({ niveau: sel.niveau, classe: sel.classe, at: Date.now() })
      );
    } catch (err) {
      /* ignore */
    }
    var params = new global.URLSearchParams(global.location.search);
    if (sel.niveau) {
      params.set('niveau', sel.niveau);
    } else {
      params.delete('niveau');
    }
    if (sel.classe) {
      params.set('classe', sel.classe);
    } else {
      params.delete('classe');
    }
    var query = params.toString();
    var next = global.location.pathname + (query ? '?' + query : '') + global.location.hash;
    var current = global.location.pathname + global.location.search + global.location.hash;
    if (next !== current) {
      global.history.replaceState(null, '', next);
    }
  }

  function layoutOverflow() {
    if (typeof global.layoutTabsOverflowNav === 'function') {
      global.layoutTabsOverflowNav();
    }
  }

  function applySelection(selection) {
    if (!selection || (!selection.niveau && !selection.classe)) {
      return;
    }
    var niveauBtn = selection.niveau
      ? document.querySelector('[data-niveau-key="' + CSS.escape(selection.niveau) + '"]')
      : null;
    if (niveauBtn && typeof global.switchMainTab === 'function') {
      var tabId = niveauBtn.getAttribute('data-tab');
      global.switchMainTab(tabId, niveauBtn, { skipPersist: true, skipResetClasse: true });
    }
    if (selection.classe && typeof global.switchClasseTab === 'function') {
      global.switchClasseTab(null, 'classe-' + selection.classe, { skipPersist: true });
    }
  }

  global.enhanceDirecteurNiveauClasseTabs = function (cfg) {
    cfg = cfg || {};
    var storageKey = cfg.storageKey || 'directeur:niveau-classe';
    var origMain = global.switchMainTab;
    var origClasse = global.switchClasseTab;

    if (typeof origMain === 'function' && !origMain.__persistWrapped) {
      global.switchMainTab = function (tabId, btn, opts) {
        opts = opts || {};
        origMain(tabId, btn, opts);
        if (!opts.skipPersist) {
          writeSelection(storageKey);
        }
        layoutOverflow();
      };
      global.switchMainTab.__persistWrapped = true;
    }

    if (typeof origClasse === 'function' && !origClasse.__persistWrapped) {
      global.switchClasseTab = function (event, subtabId, opts) {
        opts = opts || {};
        origClasse(event, subtabId, opts);
        if (!opts.skipPersist) {
          writeSelection(storageKey);
        }
        layoutOverflow();
      };
      global.switchClasseTab.__persistWrapped = true;
    }

    var params = readSelection(storageKey);
    var hasQuery =
      global.location.search.indexOf('niveau=') !== -1 ||
      global.location.search.indexOf('classe=') !== -1;
    if (hasQuery || params.niveau || params.classe) {
      applySelection(params);
      writeSelection(storageKey);
    } else {
      writeSelection(storageKey);
    }
    layoutOverflow();
  };
})(window);
