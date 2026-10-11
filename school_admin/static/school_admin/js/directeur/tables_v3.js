/**
 * Tableaux et listes v3 : chaque cellule reçoit le libellé de sa colonne (data-label),
 * ce qui permet de transformer les lignes en cartes lisibles sur mobile.
 * Gère les vrais <table> et les listes en grille (…-list-header / …-list-row),
 * y compris celles ajoutées ou rafraîchies en direct.
 */
(function () {
  'use strict';
  if (!document.body.classList.contains('gv3')) return;

  var RE_HEAD = /(^|\s)([a-z0-9]+-)?list-header(\s|$)/;
  var RE_ROW = /(^|\s)([a-z0-9]+-)?list-row(\s|$)/;

  function texte(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  // Cellule titre de la carte mobile = première cellule qui contient du texte ;
  // une cellule ne contenant qu'une case à cocher est placée en coin.
  function marquer(cells) {
    var titre = null;
    Array.prototype.forEach.call(cells, function (c) {
      var seuleCase = c.querySelector('input[type="checkbox"]') && !texte(c);
      if (seuleCase) c.classList.add('v3-cell-check');
      if (!titre && !seuleCase && texte(c) && !c.classList.contains('v3-cell-actions')) titre = c;
    });
    if (titre) titre.classList.add('v3-cell-main');
  }

  function etiqueterTable(table) {
    var heads = table.querySelectorAll('thead th');
    if (!heads.length) {
      var first = table.querySelector('tr');
      if (first && first.querySelector('th')) heads = first.querySelectorAll('th');
    }
    if (!heads.length) return;
    var libelles = [];
    heads.forEach(function (th) {
      var span = parseInt(th.getAttribute('colspan') || '1', 10);
      for (var k = 0; k < span; k++) libelles.push(texte(th));
    });
    table.classList.add('v3-table');
    table.querySelectorAll('tbody tr').forEach(function (tr) {
      var i = 0;
      Array.prototype.forEach.call(tr.children, function (td) {
        if (!td.hasAttribute('data-label') && libelles[i]) td.setAttribute('data-label', libelles[i]);
        if (/actions?/i.test(libelles[i] || '')) td.classList.add('v3-cell-actions');
        i += parseInt(td.getAttribute('colspan') || '1', 10);
      });
      marquer(tr.children);
    });
    if (!table.parentElement.classList.contains('v3-table-scroll') && !table.closest('.v3-table-scroll')) {
      var wrap = document.createElement('div');
      wrap.className = 'v3-table-scroll';
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    }
  }

  function etiqueterListe(header) {
    var liste = header.parentElement;
    if (!liste) return;
    var libelles = Array.prototype.map.call(header.children, texte);
    liste.classList.add('v3-list');
    Array.prototype.forEach.call(liste.querySelectorAll(':scope > *'), function (row) {
      if (row === header || !RE_ROW.test(row.className)) return;
      row.classList.add('v3-row');
      Array.prototype.forEach.call(row.children, function (cell, i) {
        if (!cell.hasAttribute('data-label') && libelles[i]) cell.setAttribute('data-label', libelles[i]);
        if (/actions?/i.test(libelles[i] || '')) cell.classList.add('v3-cell-actions');
      });
      marquer(row.children);
    });
  }

  function tout() {
    var main = document.querySelector('main, .content-container, .main-content-container') || document.body;
    main.querySelectorAll('table').forEach(etiqueterTable);
    Array.prototype.forEach.call(main.querySelectorAll('[class*="list-header"]'), function (h) {
      if (RE_HEAD.test(h.className)) etiqueterListe(h);
    });
  }

  tout();
  var minuteur = null;
  new MutationObserver(function () {
    clearTimeout(minuteur);
    minuteur = setTimeout(tout, 120);
  }).observe(document.body, { childList: true, subtree: true });
})();
