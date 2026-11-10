(function () {
  if (window.__notesScaleBound) return;
  window.__notesScaleBound = true;

  var DRAFT_PREFIX = 'aria.notesDraft.v1.';

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function parseNote(raw) {
    if (raw == null) return NaN;
    var s = String(raw).trim().replace(/,/g, '.').replace(/\s/g, '');
    if (!s || s === '--' || s === '—' || /^abs/i.test(s)) return NaN;
    var n = parseFloat(s);
    return isFinite(n) ? n : NaN;
  }

  function noteHsl(n, max) {
    var sur20 = clamp((n / max) * 20, 0, 20);
    if (sur20 < 10) {
      var t = sur20 / 10;
      return {
        h: Math.round(t * 4),
        s: Math.round(90 - t * 10),
        l: Math.round(22 + t * 26)
      };
    }
    var u = (sur20 - 10) / 10;
    return {
      h: Math.round(78 + u * 42),
      s: 76,
      l: 32
    };
  }

  function applyNoteColor(el, value, maxNote) {
    if (!el) return;
    var n = parseNote(value);
    var max = parseNote(maxNote);
    if (isNaN(n) || n < 0 || isNaN(max) || max <= 0) {
      el.style.removeProperty('color');
      el.style.removeProperty('background-color');
      el.style.removeProperty('border-color');
      return;
    }
    var c = noteHsl(n, max);
    var fg = 'hsl(' + c.h + ', ' + c.s + '%, ' + c.l + '%)';
    el.style.setProperty('color', fg, 'important');
    el.style.setProperty('-webkit-text-fill-color', fg, 'important');
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.style.setProperty('background-color', 'hsl(' + c.h + ', 78%, 94%)', 'important');
      el.style.setProperty('border-color', 'hsl(' + c.h + ', 62%, 52%)', 'important');
      el.style.setProperty('font-weight', '700', 'important');
    }
  }

  function syncCellSort(input) {
    var cell = input.closest('td[data-eval-id], td.moyenne-cell, .notes-list-row__note, .notes-list-row__moy');
    if (!cell) return;
    var n = parseNote(input.value);
    cell.setAttribute('data-note-sort', isNaN(n) ? '' : String(n));
  }

  function colorNote(input) {
    if (!input) return;
    input.classList.remove('note-faible', 'note-moyenne-faible', 'note-bonne', 'note-excellente');
    var max = input.getAttribute('data-max') || input.getAttribute('data-bareme') || input.getAttribute('max') || '20';
    applyNoteColor(input, input.value, max);
    syncCellSort(input);
  }

  function colorAll(root) {
    var scope = root || document;
    scope.querySelectorAll('.notes-chip__value[data-note-sort]').forEach(function (el) {
      if (el.classList.contains('muted') || el.classList.contains('absent')) return;
      applyNoteColor(el, el.getAttribute('data-note-sort'), el.getAttribute('data-bareme') || '20');
    });
    scope.querySelectorAll('.note-input, .examen-input, .moyenne-input').forEach(function (input) {
      colorNote(input);
    });
  }

  function rowScore(row, mode, evalId) {
    var cell = null;
    if (mode === 'moyenne') {
      cell = row.querySelector('.notes-list-row__moy, td.moyenne-cell, .moyenne-cell');
    } else if (evalId) {
      cell = row.querySelector('.notes-list-row__note[data-eval-id="' + evalId + '"], td[data-eval-id="' + evalId + '"]');
    }
    if (!cell) return -1;
    var attr = cell.getAttribute('data-note-sort');
    if (attr != null && attr !== '') {
      var fromAttr = parseNote(attr);
      return isNaN(fromAttr) ? -1 : fromAttr;
    }
    var input = cell.querySelector('input');
    if (input) {
      var fromInput = parseNote(input.value);
      return isNaN(fromInput) ? -1 : fromInput;
    }
    var chip = cell.querySelector('.notes-chip__value');
    if (!chip || chip.classList.contains('muted') || chip.classList.contains('absent')) return -1;
    var fromChip = parseNote(chip.getAttribute('data-note-sort') || chip.textContent);
    return isNaN(fromChip) ? -1 : fromChip;
  }

  function sortNotesBlock(block) {
    if (!block) return;
    var mode = block.getAttribute('data-view') || 'eval';
    var list = block.querySelector('.notes-list');
    var evalId = '';
    if (mode === 'eval') {
      evalId = (list && list.getAttribute('data-active-eval')) || '';
      if (!evalId) {
        var on = block.querySelector('.notes-eval-tab.active, .has-evaluation.is-eval-on');
        if (on) evalId = on.getAttribute('data-eval-id') || '';
      }
    }
    var container = list || (block.querySelector('.notation-table') && block.querySelector('.notation-table tbody'));
    if (!container) return;
    var rows = [];
    for (var i = 0; i < container.children.length; i++) {
      var child = container.children[i];
      if (child.classList && (child.classList.contains('notes-list-row') || (child.tagName === 'TR' && child.getAttribute('data-eleve-id')))) {
        rows.push(child);
      }
    }
    if (!rows.length) return;
    rows.sort(function (a, b) {
      var diff = rowScore(b, mode, evalId) - rowScore(a, mode, evalId);
      if (diff !== 0) return diff;
      var na = a.getAttribute('data-eleve-name') || '';
      var nb = b.getAttribute('data-eleve-name') || '';
      return na.localeCompare(nb, 'fr', { sensitivity: 'base' });
    });
    rows.forEach(function (row, i) {
      container.appendChild(row);
      row.classList.toggle('row-even', i % 2 === 0);
      row.classList.toggle('row-odd', i % 2 === 1);
      var idx = row.querySelector('.notes-list-row__index');
      if (idx) idx.textContent = String(i + 1);
    });
  }

  function draftScope() {
    var el = document.querySelector('[data-notes-draft]');
    return el ? el.getAttribute('data-notes-draft') : '';
  }

  function draftKey() {
    var scope = draftScope();
    return scope ? DRAFT_PREFIX + scope : '';
  }

  function readDrafts() {
    var key = draftKey();
    if (!key) return {};
    try {
      return JSON.parse(localStorage.getItem(key) || '{}') || {};
    } catch (err) {
      return {};
    }
  }

  function writeDrafts(map) {
    var key = draftKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(map));
    } catch (err) {}
  }

  function persistInput(input) {
    if (!input || !input.name || input.readOnly || input.disabled) return;
    if (!input.classList.contains('note-input') && !input.classList.contains('examen-input')) return;
    var map = readDrafts();
    map[input.name] = input.value;
    writeDrafts(map);
  }

  function restoreDrafts() {
    var map = readDrafts();
    var names = Object.keys(map);
    if (!names.length) return;
    names.forEach(function (name) {
      var found = document.getElementsByName(name);
      var input = found && found[0];
      if (!input || input.readOnly || input.disabled) return;
      if (!input.classList.contains('note-input') && !input.classList.contains('examen-input')) return;
      input.value = map[name];
      colorNote(input);
    });
  }

  function bindDrafts() {
    if (!draftKey()) return;
    restoreDrafts();
    document.addEventListener('input', function (event) {
      var input = event.target.closest('.note-input, .examen-input');
      if (!input) return;
      colorNote(input);
      persistInput(input);
      var block = input.closest('.notes-eval-block');
      if (block) sortNotesBlock(block);
    });
    document.addEventListener('change', function (event) {
      var input = event.target.closest('.note-input, .examen-input');
      if (!input) return;
      colorNote(input);
      persistInput(input);
    });
  }

  window.__notesScaleColor = colorNote;
  window.colorNote = colorNote;
  window.sortNotesBlock = sortNotesBlock;
  window.applyNotesScale = colorAll;

  function boot(root) {
    colorAll(root || document);
    (root || document).querySelectorAll('.notes-eval-block').forEach(function (block) {
      sortNotesBlock(block);
    });
    window.requestAnimationFrame(function () {
      colorAll(root || document);
    });
    window.setTimeout(function () {
      colorAll(root || document);
    }, 400);
  }

  document.addEventListener('prof-hub-panel-loaded', function () {
    boot();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      bindDrafts();
      boot();
    });
  } else {
    bindDrafts();
    boot();
  }
})();
