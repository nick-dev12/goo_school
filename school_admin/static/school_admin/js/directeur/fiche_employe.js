/**
 * Fiche employé (enseignant / personnel) : onglets, sous-onglets, copie, modales, filtres.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-fe-root]');
  if (!root) return;

  // ---------- Onglets principaux (URL ?onglet=… conservée pour le retour et le partage) ----------
  var tabs = root.querySelectorAll('[data-fe-tab]');
  var panels = root.querySelectorAll('[data-fe-panel]');

  function activer(nom, pousser) {
    var trouve = false;
    tabs.forEach(function (t) {
      var on = t.getAttribute('data-fe-tab') === nom;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (on) {
        trouve = true;
        if (t.scrollIntoView) t.scrollIntoView({ block: 'nearest', inline: 'center' });
      }
    });
    if (!trouve) return false;
    panels.forEach(function (p) { p.classList.toggle('is-active', p.getAttribute('data-fe-panel') === nom); });
    if (pousser) {
      var url = new URL(window.location.href);
      url.searchParams.set('onglet', nom);
      ['section', 'matiere'].forEach(function (k) { if (nom !== 'enseignement' && nom !== 'dossier') url.searchParams.delete(k); });
      window.history.replaceState({ onglet: nom }, '', url.toString());
    }
    return true;
  }

  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { activer(t.getAttribute('data-fe-tab'), true); });
    t.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      var n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      n.focus();
      activer(n.getAttribute('data-fe-tab'), true);
    });
  });
  activer(root.getAttribute('data-fe-initial') || 'profil', false);

  // Liens internes vers un onglet (ex. « Voir l'emploi du temps »).
  document.addEventListener('click', function (e) {
    var go = e.target.closest('[data-fe-goto]');
    if (!go) return;
    e.preventDefault();
    if (activer(go.getAttribute('data-fe-goto'), true)) {
      root.querySelector('.fe-tabs').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  // ---------- Sous-onglets ----------
  root.querySelectorAll('[data-fe-subtabs]').forEach(function (groupe) {
    var nomGroupe = groupe.getAttribute('data-fe-subtabs');
    var boutons = groupe.querySelectorAll('[data-fe-subtab]');
    boutons.forEach(function (b) {
      b.addEventListener('click', function () {
        var cible = b.getAttribute('data-fe-subtab');
        boutons.forEach(function (x) {
          x.classList.toggle('is-active', x === b);
          x.setAttribute('aria-selected', x === b ? 'true' : 'false');
        });
        root.querySelectorAll('[data-fe-subpanel^="' + nomGroupe + ':"]').forEach(function (p) {
          p.classList.toggle('is-active', p.getAttribute('data-fe-subpanel') === nomGroupe + ':' + cible);
        });
      });
    });
  });

  // ---------- Copie ----------
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fe-copy]');
    if (!b) return;
    var texte = b.getAttribute('data-fe-copy');
    var fini = function () {
      var i = b.querySelector('i');
      var avant = i ? i.className : '';
      b.classList.add('is-done');
      if (i) i.className = 'fas fa-check';
      setTimeout(function () { b.classList.remove('is-done'); if (i) i.className = avant; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texte).then(fini, function () { window.prompt('Copiez :', texte); });
    } else {
      window.prompt('Copiez :', texte);
    }
  });

  // ---------- Modales génériques (data-fe-open="id") ----------
  function ouvrirModale(m) {
    if (!m) return;
    m.hidden = false;
    m.classList.add('is-open');
    document.documentElement.style.overflow = 'hidden';
    var f = m.querySelector('input:not([type=hidden]), select, textarea, button');
    if (f) setTimeout(function () { f.focus(); }, 30);
  }
  function fermerModale(m) {
    if (!m) return;
    m.classList.remove('is-open');
    if (m.classList.contains('cg3-modal')) m.hidden = true;
    document.documentElement.style.overflow = '';
  }
  document.addEventListener('click', function (e) {
    var o = e.target.closest('[data-fe-open]');
    if (o) { ouvrirModale(document.getElementById(o.getAttribute('data-fe-open'))); return; }
    var c = e.target.closest('[data-fe-close]');
    if (c) { fermerModale(c.closest('.fe-matiere-modal, .cg3-modal')); return; }
    if (e.target.classList && (e.target.classList.contains('fe-matiere-modal') || e.target.classList.contains('cg3-modal'))) fermerModale(e.target);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.fe-matiere-modal.is-open, .cg3-modal.is-open').forEach(fermerModale);
    var mm = document.getElementById('modalModifierProfesseur');
    if (mm && mm.classList.contains('active')) window.closeModifierProfesseurModal();
  });
  document.querySelectorAll('.cg3-modal[data-fe-auto-open]').forEach(ouvrirModale);

  // ---------- Modale de modification de l'enseignant (formulaire existant) ----------
  window.openModifierProfesseurModal = function () {
    var m = document.getElementById('modalModifierProfesseur');
    if (!m) return;
    m.classList.add('active');
    document.body.classList.add('modal-personnel-open');
    if (typeof window.initAjouterProfesseurSuperieur === 'function' && document.getElementById('matiere-principale-list')) {
      window.initAjouterProfesseurSuperieur();
    }
  };
  window.closeModifierProfesseurModal = function () {
    var m = document.getElementById('modalModifierProfesseur');
    if (!m) return;
    m.classList.remove('active');
    document.body.classList.remove('modal-personnel-open');
  };
  var mm = document.getElementById('modalModifierProfesseur');
  if (mm && mm.classList.contains('active')) window.openModifierProfesseurModal();

  // ---------- Matières secondaires ----------
  var modalMatiere = document.getElementById('modal-ajout-matiere');
  window.ouvrirModalAjoutMatiere = function () {
    if (!modalMatiere) return;
    var dep = document.getElementById('department');
    if (dep) { dep.value = ''; dep.dispatchEvent(new Event('change', { bubbles: true })); }
    var hid = document.getElementById('modal-matiere-id');
    var search = document.getElementById('modal-matiere-search');
    var hint = document.getElementById('modal-matiere-selected-hint');
    if (hid) hid.value = '';
    if (search) search.value = '';
    if (hint) hint.hidden = true;
    modalMatiere.querySelectorAll('.modal-matiere-pick-item').forEach(function (b) { b.classList.remove('is-selected'); b.hidden = false; });
    ouvrirModale(modalMatiere);
  };
  window.fermerModalAjoutMatiere = function () { fermerModale(modalMatiere); };

  var liste = document.getElementById('modal-matiere-pick-list');
  if (liste && !document.getElementById('matiere-principale-list')) {
    var items = liste.querySelectorAll('.modal-matiere-pick-item');
    var search = document.getElementById('modal-matiere-search');
    var hid = document.getElementById('modal-matiere-id');
    var norm = function (s) {
      s = (s || '').toString().toLowerCase();
      try { s = s.normalize('NFD').replace(/[̀-ͯ]/g, ''); } catch (err) { /* ignore */ }
      return s;
    };
    var filtrer = function () {
      var q = norm(search ? search.value : '');
      items.forEach(function (b) { b.hidden = q && norm(b.getAttribute('data-matiere-search') || b.textContent).indexOf(q) === -1; });
    };
    items.forEach(function (b) {
      b.addEventListener('click', function () {
        hid.value = b.getAttribute('data-matiere-id') || '';
        items.forEach(function (x) { x.classList.toggle('is-selected', x === b); });
        var hint = document.getElementById('modal-matiere-selected-hint');
        var lbl = document.getElementById('modal-matiere-selected-label');
        if (hint && lbl) { lbl.textContent = (b.querySelector('.modal-matiere-pick-main') || b).textContent.trim(); hint.hidden = false; }
      });
    });
    if (search) search.addEventListener('input', filtrer);
  }

  window.retirerMatiereSecondaire = function (professeurId, matiereId, nom) {
    if (!window.confirm('Retirer « ' + (nom || 'cette matière') + ' » des matières secondaires ?')) return;
    var f = document.getElementById('fe-retirer-matiere');
    if (!f) return;
    f.querySelector('[name="matiere_id"]').value = matiereId;
    f.submit();
  };

  // ---------- Cahier de texte : filtre par classe ----------
  document.addEventListener('click', function (e) {
    var chip = e.target.closest('[data-pct-classe]');
    if (!chip) return;
    var id = chip.getAttribute('data-pct-classe');
    document.querySelectorAll('[data-pct-classe]').forEach(function (c) { c.classList.toggle('is-active', c === chip); });
    document.querySelectorAll('.pct-item').forEach(function (li) { li.hidden = !!id && li.getAttribute('data-classe') !== id; });
  });

  // ---------- Autorisations : recherche et « actives seulement » ----------
  var permSearch = root.querySelector('[data-fe-perm-search]');
  var permOnly = root.querySelector('[data-fe-perm-only]');
  function filtrerPerms() {
    var q = permSearch ? permSearch.value.trim().toLowerCase() : '';
    var only = permOnly && permOnly.checked;
    root.querySelectorAll('.fe-perm-cat').forEach(function (cat) {
      var visibles = 0;
      cat.querySelectorAll('.fe-perm').forEach(function (p) {
        var ok = (!q || p.textContent.toLowerCase().indexOf(q) !== -1) && (!only || p.classList.contains('is-on'));
        p.hidden = !ok;
        if (ok) visibles += 1;
      });
      cat.hidden = visibles === 0;
    });
  }
  if (permSearch) permSearch.addEventListener('input', filtrerPerms);
  if (permOnly) permOnly.addEventListener('change', filtrerPerms);
})();

/* Fiche élève : source de la photo et correction d'un appel (enseignant). */
(function () {
  'use strict';
  document.addEventListener('change', function (e) {
    var r = e.target.closest('[data-fe-photo-source]');
    if (!r) return;
    var form = r.closest('form');
    form.querySelectorAll('[data-source]').forEach(function (bloc) {
      var on = bloc.getAttribute('data-source') === r.value;
      bloc.hidden = !on;
      var input = bloc.querySelector('input');
      if (input) { input.disabled = !on; if (!on) input.value = ''; }
    });
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fe-presence]');
    if (!b) return;
    var modal = document.getElementById('fe-presence');
    if (!modal) return;
    var form = modal.querySelector('form');
    form.action = form.getAttribute('data-url').replace(/\/0\/$/, '/' + b.getAttribute('data-fe-presence') + '/');
    var radio = form.querySelector('input[name="statut"][value="' + b.getAttribute('data-statut') + '"]');
    form.querySelectorAll('input[name="statut"]').forEach(function (x) { x.checked = false; });
    if (radio) radio.checked = true;
    modal.querySelector('[data-fe-presence-date]').textContent = b.getAttribute('data-date');
    modal.hidden = false;
    modal.classList.add('is-open');
    document.documentElement.style.overflow = 'hidden';
  });
})();
