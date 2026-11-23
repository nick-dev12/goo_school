/**
 * Modules (UE) et matières (EC) — refonte v5.
 * Bloc de filtres compact : une ligne de filtre qui n'offre qu'un seul choix est masquée
 * (rien à choisir), et les lignes visibles forment une seule carte aux coins arrondis.
 */
(function () {
  function rangees() {
    return Array.prototype.filter.call(
      document.querySelectorAll('.mm5 .gml-filter-level'),
      function (r) { return r.offsetParent !== null; }
    );
  }

  function marquerSolos() {
    document.querySelectorAll('.mm5 .gml-filter-level').forEach(function (r) {
      var choix = r.querySelectorAll('.matiere-tabs-track [role="tab"], .matiere-tabs-overflow-menu [role="menuitem"]');
      // La ligne « Classe » de la liste reste visible : elle indique la classe affichée.
      var filtreClasse = r.querySelector('[data-sx-set]') !== null;
      r.classList.toggle('mm-solo', choix.length <= 1 && !filtreClasse);
    });
  }

  function arrondir() {
    document.querySelectorAll('.mm5 .gml-filter-level, .mm5 .gml-main-panel .sx-toolbar').forEach(function (r) {
      r.classList.remove('mm-first', 'mm-last');
    });
    var visibles = rangees();
    var zone = document.querySelector('.mm5 .gml-main-panel');
    var barre = zone && Array.prototype.find.call(zone.querySelectorAll('.sx-toolbar'), function (t) { return t.offsetParent !== null; });
    if (!visibles.length) {
      if (barre) barre.classList.add('mm-first');
      return;
    }
    visibles[0].classList.add('mm-first');
    if (!barre) visibles[visibles.length - 1].classList.add('mm-last');
  }

  function rafraichir() {
    marquerSolos();
    arrondir();
  }

  document.addEventListener('DOMContentLoaded', function () {
    rafraichir();
    // Les onglets changent les panneaux visibles : on recalcule après chaque clic.
    document.addEventListener('click', function (e) {
      if (e.target.closest('.gml-filter-level, .matiere-tabs-overflow-menu')) {
        window.setTimeout(arrondir, 0);
      }
    });
    window.addEventListener('resize', function () { window.setTimeout(arrondir, 50); });
  });
  window.addEventListener('load', rafraichir);
})();
