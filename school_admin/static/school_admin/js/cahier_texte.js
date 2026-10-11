/**
 * Aria — cahier de texte : éditeur d'entrée et rédaction par Aria.
 */
(function () {
  'use strict';

  function lire(id) {
    var el = document.getElementById(id);
    try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
  }

  var entrees = lire('ct-entrees') || {};
  var paires = lire('ct-paires') || [];
  var modal = document.getElementById('ct-editeur');
  var form = document.getElementById('ct-form');
  if (!modal || !form) return;
  var msg = form.querySelector('[data-ct-msg]');
  var champs = ['titre', 'objectifs', 'contenu', 'travail_a_faire', 'date_travail', 'observations'];

  function remplirClasses(classeId) {
    var sel = form.classe_id;
    sel.innerHTML = '';
    paires.forEach(function (p) {
      var o = document.createElement('option');
      o.value = p.id; o.textContent = p.nom;
      if (String(p.id) === String(classeId)) o.selected = true;
      sel.appendChild(o);
    });
    if (!paires.length) {
      var o = document.createElement('option');
      o.value = ''; o.textContent = '— aucune classe à l’emploi du temps —';
      sel.appendChild(o);
    }
  }

  function remplirMatieres(matiereId) {
    var sel = form.matiere_id;
    var p = paires.find(function (x) { return String(x.id) === String(form.classe_id.value); });
    sel.innerHTML = '<option value="">—</option>';
    (p ? p.matieres : []).forEach(function (m) {
      var o = document.createElement('option');
      o.value = m.id; o.textContent = m.nom;
      if (String(m.id) === String(matiereId)) o.selected = true;
      sel.appendChild(o);
    });
    if (p && p.matieres.length === 1 && !matiereId) sel.value = p.matieres[0].id;
  }

  function ouvrir(valeurs, titre) {
    valeurs = valeurs || {};
    form.reset();
    form.entree_id.value = valeurs.id || '';
    form.ia.value = '0';
    remplirClasses(valeurs.classe_id || (paires[0] && paires[0].id));
    remplirMatieres(valeurs.matiere_id);
    form.date.value = valeurs.date || new Date().toISOString().slice(0, 10);
    form.heure_debut.value = valeurs.heure_debut || '';
    form.heure_fin.value = valeurs.heure_fin || '';
    champs.forEach(function (c) { if (form[c]) form[c].value = valeurs[c] || ''; });
    form.statut.value = 'brouillon';
    document.getElementById('ct-notes').value = '';
    msg.textContent = ''; msg.classList.remove('is-error');
    modal.querySelector('[data-ct-titre]').textContent = titre || 'Nouvelle entrée';
    modal.hidden = false;
    document.documentElement.style.overflow = 'hidden';
    (valeurs.id ? form.titre : document.getElementById('ct-notes')).focus();
  }

  form.classe_id.addEventListener('change', function () { remplirMatieres(''); });

  // Popup d'avertissement avant toute validation définitive.
  var confirmModal = document.getElementById('ct-confirm');
  var validerForm = document.getElementById('ct-valider-form');
  var demande = document.getElementById('ct-demande');
  var suite = null;

  function confirmer(titre, action) {
    suite = action;
    confirmModal.querySelector('[data-ct-confirm-titre]').textContent = titre ? '« ' + titre + ' »' : '';
    confirmModal.hidden = false;
    document.documentElement.style.overflow = 'hidden';
    confirmModal.querySelector('[data-ct-confirm-annuler]').focus();
  }

  function fermerConfirm() {
    confirmModal.hidden = true;
    suite = null;
    if (modal.hidden) document.documentElement.style.overflow = '';
  }

  confirmModal.querySelector('[data-ct-confirm-annuler]').addEventListener('click', fermerConfirm);
  confirmModal.addEventListener('click', function (e) { if (e.target === confirmModal) fermerConfirm(); });
  confirmModal.querySelector('[data-ct-confirm-ok]').addEventListener('click', function () {
    var action = suite;
    this.disabled = true;
    if (action) action();
  });
  document.addEventListener('keydown', function (e) {
    // Échap ferme d'abord l'avertissement, sans perdre l'éditeur ouvert derrière.
    if (e.key === 'Escape' && !confirmModal.hidden) { e.stopImmediatePropagation(); fermerConfirm(); }
  }, true);

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.ct-help')) {
      document.querySelectorAll('.ct-help.is-open').forEach(function (b) {
        b.classList.remove('is-open');
        b.querySelector('[data-ct-aide]').setAttribute('aria-expanded', 'false');
      });
    }
    if (e.target.closest('[data-ct-nouveau]')) { ouvrir({}, 'Nouvelle entrée'); return; }
    var r = e.target.closest('[data-ct-remplir]');
    if (r) {
      ouvrir({ classe_id: r.dataset.classe, matiere_id: r.dataset.matiere, date: r.dataset.date,
               heure_debut: r.dataset.debut, heure_fin: r.dataset.fin }, 'Remplir le cours');
      return;
    }
    var ed = e.target.closest('[data-ct-edit]');
    if (ed) {
      var v = entrees[ed.dataset.ctEdit];
      if (v && v.modifiable !== false) ouvrir(v, 'Modifier le brouillon');
      return;
    }
    if (e.target.closest('[data-ct-brouillon]')) { form.statut.value = 'brouillon'; return; }
    if (e.target.closest('[data-ct-valider]')) {
      // Valider depuis l'éditeur : champs vérifiés d'abord, puis avertissement.
      if (!form.reportValidity()) return;
      confirmer(form.titre.value, function () { form.statut.value = 'valide'; form.submit(); });
      return;
    }
    var ve = e.target.closest('[data-ct-valider-entree]');
    if (ve) {
      confirmer(ve.dataset.titre, function () {
        validerForm.entree_id.value = ve.dataset.ctValiderEntree;
        validerForm.submit();
      });
      return;
    }
    var dm = e.target.closest('[data-ct-demande]');
    if (dm && demande) {
      var f = demande.querySelector('form');
      f.reset();
      f.entree_id.value = dm.dataset.ctDemande;
      demande.querySelector('[data-ct-demande-titre]').textContent = '« ' + dm.dataset.titre + ' »';
      demande.hidden = false;
      document.documentElement.style.overflow = 'hidden';
      f.motif.focus();
      return;
    }
    var aide = e.target.closest('[data-ct-aide]');
    if (aide) {
      var box = aide.closest('.ct-help');
      var ouvert = box.classList.toggle('is-open');
      aide.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
      return;
    }
    var chip = e.target.closest('[data-ct-chip]');
    if (chip) {
      var notes = document.getElementById('ct-notes');
      notes.value = (notes.value ? notes.value.trim() + ' ' : '') + chip.dataset.ctChip;
      notes.focus();
    }
  });

  function cookie(nom) {
    var m = document.cookie.match('(^|;)\\s*' + nom + '=([^;]*)');
    return m ? decodeURIComponent(m[2]) : '';
  }

  var bouton = form.querySelector('[data-ct-rediger]');
  if (bouton) {
    bouton.addEventListener('click', function () {
      if (!form.classe_id.value) { msg.textContent = 'Choisissez d’abord la classe.'; msg.classList.add('is-error'); return; }
      var label = bouton.querySelector('span');
      var ancien = label.textContent;
      bouton.disabled = true;
      bouton.querySelector('i').className = 'ct-spin';
      label.textContent = 'Aria rédige…';
      msg.textContent = ''; msg.classList.remove('is-error');
      fetch(window.CT_REDIGER_URL, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.csrfmiddlewaretoken.value || cookie('csrftoken') },
        body: JSON.stringify({
          classe_id: form.classe_id.value, matiere_id: form.matiere_id.value, date: form.date.value,
          heure_debut: form.heure_debut.value, heure_fin: form.heure_fin.value,
          notes: document.getElementById('ct-notes').value,
        }),
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) throw new Error(d.erreur || 'Erreur');
        ['titre', 'objectifs', 'contenu', 'travail_a_faire', 'date_travail'].forEach(function (c) {
          if (form[c] && d.proposition[c] !== undefined) {
            form[c].value = d.proposition[c];
            form[c].classList.remove('ct-filled'); void form[c].offsetWidth; form[c].classList.add('ct-filled');
          }
        });
        form.ia.value = '1';
        msg.textContent = 'Proposition d’Aria insérée : relisez et ajustez avant d’enregistrer.';
      }).catch(function (err) {
        msg.textContent = err.message || 'Aria n’a pas pu rédiger.';
        msg.classList.add('is-error');
      }).finally(function () {
        bouton.disabled = false;
        bouton.querySelector('.ct-spin, i').className = 'fas fa-wand-magic-sparkles';
        label.textContent = ancien;
      });
    });
  }
})();
