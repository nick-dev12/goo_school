// Listes d'élèves responsive (direction et enseignants, tous types d'établissement).
//
// Activation sur le conteneur de la liste (un <table> ou une liste en <div>) :
//   data-rl                 active le composant
//   data-rl-mobile="1,2,4"  colonnes (numérotées à partir de 1, -1 = dernière) gardées sur mobile — trois au plus
//   data-rl-actions="6"     colonne des boutons ("last" ou -1 = dernière) ; masquée sur mobile, reprise dans la fenêtre
// Liste en <div> : l'en-tête est l'enfant [data-rl-head] ou .list-header, les lignes [data-rl-row] ou .list-row.
// Sur une ligne (facultatif) : data-rl-titre="Nom complet" (titre de la fenêtre) et, dans une cellule, des éléments
// <span hidden data-rl-extra data-rl-label="Sexe">…</span> : informations en plus, montrées seulement dans la fenêtre.
//
//   data-rl-conteneur       (sur l'enveloppe du tableau) la garde visible sur mobile
//   data-rl-masquer         (sur un bloc de cartes « mobile » en double) le masque : la liste compacte le remplace
//
// Ordinateur et tablette : tableau complet ; un bouton qui n'a qu'une icône reçoit son libellé (title / aria-label).
// Mobile : liste compacte (trois informations) ; un appui sur la ligne ouvre une fenêtre plein écran
// avec toutes les informations de l'élève et ses boutons, libellés en clair.
(function () {
    'use strict';

    var MOBILE = window.matchMedia('(max-width: 760px)');
    var INTERACTIF = 'a, button, input, select, textarea, label, [role="button"], [onclick]';

    function texte(el) { return (el && el.textContent || '').replace(/\s+/g, ' ').trim(); }
    // "1,2,-1" → index 0, 1 et la dernière colonne (les négatifs comptent depuis la fin).
    function indices(valeur, nb) {
        return (valeur || '').split(',').map(function (v) {
            var n = parseInt(v, 10);
            return n < 0 ? nb + n : n - 1;
        }).filter(function (n) { return n >= 0 && n < nb; });
    }

    function enTetes(liste) {
        if (liste.tagName === 'TABLE') {
            var lignes = liste.tHead ? liste.tHead.rows : [];
            return lignes.length ? Array.prototype.slice.call(lignes[lignes.length - 1].cells) : [];
        }
        var tete = liste.querySelector(':scope > [data-rl-head], :scope > .list-header');
        return tete ? Array.prototype.slice.call(tete.children) : [];
    }

    function lignes(liste) {
        if (liste.tagName === 'TABLE') {
            var toutes = [];
            Array.prototype.forEach.call(liste.tBodies, function (tb) { toutes = toutes.concat(Array.prototype.slice.call(tb.rows)); });
            return toutes;
        }
        return Array.prototype.slice.call(liste.querySelectorAll(':scope > [data-rl-row], :scope > .list-row'));
    }

    function cellules(ligne) {
        return Array.prototype.slice.call(ligne.tagName === 'TR' ? ligne.cells : ligne.children);
    }

    // Bouton « icône seule » → libellé visible pris dans title / aria-label.
    function libellerBoutons(racine) {
        racine.querySelectorAll('a, button').forEach(function (b) {
            if (b.dataset.rlLibelle || texte(b)) { return; }
            var lib = b.getAttribute('title') || b.getAttribute('aria-label') || b.getAttribute('data-title');
            if (!lib) { return; }
            var span = document.createElement('span');
            span.className = 'rl-btn-txt';
            span.textContent = lib.trim();
            b.appendChild(span);
            b.classList.add('rl-btn-libelle');
            b.dataset.rlLibelle = '1';
        });
    }

    function preparerLigne(liste, ligne) {
        if (ligne.dataset.rlPret) { return; }
        var cel = cellules(ligne);
        // Ligne « vide » (colspan, message) : on n'y touche pas.
        if (cel.length !== liste._rl.nb) { return; }
        ligne.dataset.rlPret = '1';
        ligne.classList.add('rl-row');
        var dernier = null;
        cel.forEach(function (c, i) {
            if (liste._rl.mobile.indexOf(i) === -1) { c.setAttribute('data-rl-cache', ''); } else { dernier = c; }
            if (i === liste._rl.actions) { libellerBoutons(c); }
        });
        if (dernier) { dernier.classList.add('rl-dernier'); }
    }

    function initialiser(liste) {
        if (liste._rl) {
            lignes(liste).forEach(function (l) { preparerLigne(liste, l); });
            return;
        }
        var tetes = enTetes(liste);
        if (!tetes.length) { return; }
        var actions = liste.getAttribute('data-rl-actions');
        liste._rl = {
            nb: tetes.length,
            libelles: tetes.map(function (t) {
                var c = t.cloneNode(true);
                c.querySelectorAll('button, a, .sr-only').forEach(function (n) { n.remove(); });
                return texte(c);
            }),
            mobile: indices(liste.getAttribute('data-rl-mobile') || '1,2,3', tetes.length).slice(0, 3),
            actions: actions === 'last' ? tetes.length - 1 : (actions ? indices(actions, tetes.length)[0] : -1)
        };
        liste.classList.add(liste.tagName === 'TABLE' ? 'rl-table' : 'rl-div');
        liste.style.setProperty('--rl-cols', 'minmax(0, 1.8fr)' + new Array(liste._rl.mobile.length).join(' minmax(0, 1fr)'));
        // Ordinateur / tablette : toutes les colonnes, celle des boutons à la largeur de ses boutons libellés.
        liste.style.setProperty('--rl-cols-all', tetes.map(function (t, i) {
            return i === liste._rl.actions ? 'max-content' : (i === 0 ? 'minmax(0, 1.5fr)' : 'minmax(max-content, 1fr)');
        }).join(' '));
        tetes.forEach(function (t, i) {
            if (liste._rl.mobile.indexOf(i) === -1) { t.setAttribute('data-rl-cache', ''); }
        });
        // Les lignes ajoutées plus tard (inscription, temps réel) sont reprises au passage suivant (voir plus bas).
        lignes(liste).forEach(function (l) { preparerLigne(liste, l); });
    }

    // ---------------------------------------------------------------- fenêtre plein écran (mobile)
    var fenetre = null;
    function creerFenetre() {
        fenetre = document.createElement('div');
        fenetre.className = 'rl-modal';
        fenetre.hidden = true;
        fenetre.setAttribute('role', 'dialog');
        fenetre.setAttribute('aria-modal', 'true');
        fenetre.innerHTML =
            '<div class="rl-modal__tete"><button type="button" class="rl-modal__retour" data-rl-fermer><i class="fas fa-arrow-left" aria-hidden="true"></i>Retour</button></div>' +
            '<div class="rl-modal__corps"><h2 class="rl-modal__titre"></h2><dl class="rl-modal__infos"></dl></div>' +
            '<div class="rl-modal__actions"></div>';
        document.body.appendChild(fenetre);
        fenetre.addEventListener('click', function (e) { if (e.target.closest('[data-rl-fermer]')) { fermer(); } });
    }

    function fermer() {
        if (!fenetre || fenetre.hidden) { return; }
        fenetre.hidden = true;
        document.documentElement.classList.remove('rl-modal-ouverte');
    }

    // Copie d'une cellule pour la fenêtre : sans identifiants, sans variantes « mobile » ni informations en plus.
    function copieCellule(cellule) {
        var copie = cellule.cloneNode(true);
        copie.querySelectorAll('[id]').forEach(function (n) { n.removeAttribute('id'); });
        copie.querySelectorAll('[class*="mobile"], .rl-btn-txt, [data-rl-extra]').forEach(function (n) { n.remove(); });
        return copie;
    }
    function copieAffichable(cellule) {
        var html = copieCellule(cellule).innerHTML.trim();
        return html ? html : '—';
    }
    // Titre de la fenêtre : l'élément « nom » de la cellule s'il existe (sans le matricule affiché dessous).
    function titreDe(cellule) {
        var c = copieCellule(cellule);
        var nom = c.querySelector('[class*="name"], [class*="nom"], strong, h4, b');
        return texte(nom) || texte(c);
    }
    function ajouterInfo(dl, libelle, html) {
        var bloc = document.createElement('div');
        bloc.innerHTML = '<dt></dt><dd></dd>';
        bloc.querySelector('dt').textContent = libelle || '';
        bloc.querySelector('dd').innerHTML = html;
        dl.appendChild(bloc);
    }

    function ouvrir(ligne) {
        var liste = ligne.closest('[data-rl]');
        if (!liste || !liste._rl) { return; }
        if (!fenetre) { creerFenetre(); }
        var cel = cellules(ligne);
        var info = liste._rl;
        var titre = ligne.getAttribute('data-rl-titre') || titreDe(cel[info.mobile[0]] || cel[0]);
        fenetre.querySelector('.rl-modal__titre').textContent = titre;
        var dl = fenetre.querySelector('.rl-modal__infos');
        dl.innerHTML = '';
        cel.forEach(function (c, i) {
            if (i === info.actions || i === info.mobile[0]) { return; }
            ajouterInfo(dl, info.libelles[i], copieAffichable(c));
        });
        ligne.querySelectorAll('[data-rl-extra]').forEach(function (x) {
            var valeur = x.innerHTML.trim();
            ajouterInfo(dl, x.getAttribute('data-rl-label'), valeur && texte(x) ? valeur : '—');
        });
        var zone = fenetre.querySelector('.rl-modal__actions');
        zone.innerHTML = '';
        var source = info.actions >= 0 ? cel[info.actions] : null;
        if (source) {
            source.querySelectorAll('a, button').forEach(function (orig) {
                if (orig.hidden || orig.disabled || orig.closest('[hidden]')) { return; }
                var lib = texte(orig) || orig.getAttribute('title') || orig.getAttribute('aria-label') || '';
                var icone = orig.querySelector('i');
                var b;
                if (orig.tagName === 'A' && orig.getAttribute('href') && orig.getAttribute('href') !== '#') {
                    b = document.createElement('a');
                    b.href = orig.getAttribute('href');
                    if (orig.target) { b.target = orig.target; }
                } else {
                    b = document.createElement('button');
                    b.type = 'button';
                    b.addEventListener('click', function () { fermer(); orig.click(); });
                }
                b.className = 'rl-modal__btn';
                if (icone) { b.appendChild(icone.cloneNode(true)); }
                b.appendChild(document.createTextNode(lib));
                zone.appendChild(b);
            });
        }
        zone.hidden = !zone.children.length;
        fenetre.hidden = false;
        fenetre.querySelector('.rl-modal__corps').scrollTop = 0;
        document.documentElement.classList.add('rl-modal-ouverte');
        fenetre.querySelector('[data-rl-fermer]').focus();
    }

    document.addEventListener('click', function (e) {
        if (!MOBILE.matches) { return; }
        var ligne = e.target.closest('[data-rl] .rl-row');
        if (!ligne || e.target.closest(INTERACTIF)) { return; }
        ouvrir(ligne);
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { fermer(); } });
    MOBILE.addEventListener('change', function () { if (!MOBILE.matches) { fermer(); } });

    function tout(racine) { (racine || document).querySelectorAll('[data-rl]').forEach(initialiser); }
    window.rlInit = tout;  // pour les listes chargées après coup (onglets AJAX, fragments)
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', function () { tout(); }); } else { tout(); }
    // Listes insérées plus tard dans la page (fragments, rafraîchissements).
    var prevu = false;
    new MutationObserver(function () {
        if (prevu) { return; }
        prevu = true;
        window.requestAnimationFrame(function () { prevu = false; tout(); });
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
