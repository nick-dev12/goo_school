(function () {
  if (window.__notesListUiBound) return;
  window.__notesListUiBound = true;

  function activateView(block, view, evalId) {
    if (!block) return;
    var mode = view || 'eval';
    var id = evalId == null ? '' : String(evalId);
    var list = block.querySelector('.notes-list');

    block.setAttribute('data-view', mode);
    if (list) {
      list.setAttribute('data-view', mode);
      if (mode === 'eval' && id) {
        list.setAttribute('data-active-eval', id);
      }
    }

    block.querySelectorAll('.notes-view-mode').forEach(function (btn) {
      var on = btn.getAttribute('data-view') === mode;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });

    block.querySelectorAll('.notes-eval-tab').forEach(function (tab) {
      var on = mode === 'eval' && tab.getAttribute('data-eval-id') === id;
      tab.classList.toggle('active', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
    });

    if (mode === 'eval' && id) {
      if (list) {
        list.querySelectorAll('[data-eval-id]').forEach(function (cell) {
          cell.classList.toggle('is-active', cell.getAttribute('data-eval-id') === id);
        });
      }
      syncEvalHead(block, id);
    } else if (mode === 'moyenne') {
      syncMoyenneHead(block);
    }

    var table = block.querySelector('.notation-table');
    if (table) {
      table.querySelectorAll('.has-evaluation').forEach(function (cell) {
        if (mode === 'eval' && id) {
          cell.classList.toggle('is-eval-on', cell.getAttribute('data-eval-id') === id);
        } else {
          cell.classList.remove('is-eval-on');
        }
      });
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
    if (typeof window.sortNotesBlock === 'function') {
      window.sortNotesBlock(block);
    }
  }

  function evalTitleFrom(block, evalId) {
    var tab = block.querySelector('.notes-eval-tab[data-eval-id="' + evalId + '"]');
    if (tab) {
      return (tab.getAttribute('title') || tab.textContent || '').replace(/\s+/g, ' ').trim();
    }
    var cell = block.querySelector('.notes-list-row__devoir[data-eval-id="' + evalId + '"]');
    if (cell) {
      return (cell.getAttribute('title') || cell.textContent || '').replace(/\s+/g, ' ').trim();
    }
    return '';
  }

  function syncEvalHead(block, evalId) {
    var head = block.querySelector('.notes-list-head__devoir');
    if (!head) return;
    var title = evalTitleFrom(block, evalId);
    if (!title) return;
    head.textContent = title;
    head.setAttribute('title', title);
  }

  function syncMoyenneHead(block) {
    var head = block.querySelector('.notes-list-head__devoir');
    if (!head) return;
    head.textContent = 'Moyenne';
    head.setAttribute('title', 'Moyenne');
  }

  function getTip() {
    var tip = document.getElementById('notes-title-tip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'notes-title-tip';
      tip.className = 'notes-title-tip';
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    return tip;
  }

  function hideTip() {
    var tip = document.getElementById('notes-title-tip');
    if (tip) tip.hidden = true;
  }

  function fullTitle(el) {
    return (el.getAttribute('title') || el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function showTip(el) {
    var text = fullTitle(el);
    if (!text) return;
    var tip = getTip();
    tip.textContent = text;
    tip.hidden = false;
    var rect = el.getBoundingClientRect();
    var maxW = Math.min(280, window.innerWidth - 16);
    tip.style.maxWidth = maxW + 'px';
    var left = Math.min(Math.max(8, rect.left), window.innerWidth - maxW - 8);
    var top = rect.bottom + 8;
    if (top + 72 > window.innerHeight) {
      top = Math.max(8, rect.top - 56);
    }
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function activateElevesView(block, view) {
    if (!block) return;
    var mode = view || 'liste';
    block.setAttribute('data-view', mode);
    var list = block.querySelector('.notes-list');
    if (list) list.setAttribute('data-view', mode);
    block.querySelectorAll('.notes-eleves-view').forEach(function (btn) {
      var on = btn.getAttribute('data-view') === mode;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  document.addEventListener('click', function (event) {
    var elevesBtn = event.target.closest('.notes-eleves-view');
    if (elevesBtn) {
      event.preventDefault();
      var elevesBlock = elevesBtn.closest('.notes-eleves-block');
      var nextView = elevesBtn.getAttribute('data-view') || 'liste';
      if (elevesBlock && elevesBlock.getAttribute('data-view') === nextView) {
        nextView = 'liste';
      }
      activateElevesView(elevesBlock, nextView);
      return;
    }
    var modeBtn = event.target.closest('.notes-view-mode');
    if (modeBtn) {
      event.preventDefault();
      hideTip();
      var modeBlock = modeBtn.closest('.notes-eval-block') || document.querySelector('.notes-eval-block');
      activateView(modeBlock, modeBtn.getAttribute('data-view') || 'moyenne', '');
      return;
    }
    var tab = event.target.closest('.notes-eval-tab');
    if (tab) {
      event.preventDefault();
      hideTip();
      var block = tab.closest('.notes-eval-block') || document.querySelector('.notes-eval-block');
      activateView(block, 'eval', tab.getAttribute('data-eval-id'));
      return;
    }
    var devoir = event.target.closest('.notes-list-row__devoir.is-active');
    if (!devoir) {
      hideTip();
      return;
    }
    var tip = getTip();
    var text = fullTitle(devoir);
    if (!tip.hidden && tip.textContent === text) {
      hideTip();
      return;
    }
    showTip(devoir);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') hideTip();
  });

  document.addEventListener('scroll', hideTip, true);

  function boot(root) {
    (root || document).querySelectorAll('.notes-eval-block').forEach(function (block) {
      if (block.getAttribute('data-view') === 'moyenne') {
        activateView(block, 'moyenne', '');
        return;
      }
      var active = block.querySelector('.notes-eval-tab.active');
      if (active) {
        activateView(block, 'eval', active.getAttribute('data-eval-id'));
      }
    });
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  document.addEventListener('prof-hub-panel-loaded', function () {
    hideTip();
    boot();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { boot(); });
  } else {
    boot();
  }
})();
