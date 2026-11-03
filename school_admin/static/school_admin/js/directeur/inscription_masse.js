// Inscription en masse, dans une fenêtre de la liste des élèves.
// Les étapes (saisie → aperçu → résultat) sont chargées en AJAX depuis directeur:inscription_masse ;
// la saisie propose le dépôt d'un fichier Excel ou une grille de saisie rapide (collage depuis Excel accepté).
(function () {
    'use strict';

    var CHAMPS = ['nom', 'prenom', 'sexe', 'date_naissance', 'parent_telephone', 'parent_nom'];

    // ---------------------------------------------------------------- dépôt de fichier
    function initDepot(racine) {
        var depot = racine.querySelector('#imDepot');
        var input = racine.querySelector('#imInput');
        var nom = racine.querySelector('#imNomFichier');
        if (!depot || !input) { return; }
        input.addEventListener('change', function () {
            if (input.files.length) {
                nom.textContent = input.files[0].name;
                depot.classList.add('is-pret');
            }
        });
        ['dragenter', 'dragover'].forEach(function (ev) {
            depot.addEventListener(ev, function (e) { e.preventDefault(); depot.classList.add('is-survol'); });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            depot.addEventListener(ev, function () { depot.classList.remove('is-survol'); });
        });
        depot.addEventListener('drop', function (e) {
            e.preventDefault();
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                input.dispatchEvent(new Event('change'));
            }
        });
    }

    // ---------------------------------------------------------------- grille
    function initGrille(racine) {
        var table = racine.querySelector('#imGrille');
        if (!table) { return; }
        var corps = table.querySelector('tbody');

        function cellule(champ) {
            var td = document.createElement('td');
            var el;
            if (champ === 'sexe') {
                el = document.createElement('select');
                el.innerHTML = '<option value=""></option><option value="M">M</option><option value="F">F</option>';
            } else {
                el = document.createElement('input');
                el.type = 'text';
                if (champ === 'date_naissance') { el.placeholder = 'JJ/MM/AAAA'; el.inputMode = 'numeric'; }
                if (champ === 'parent_telephone') { el.inputMode = 'tel'; }
            }
            el.dataset.champ = champ;
            td.appendChild(el);
            return td;
        }

        function numeroter() {
            var n = 0;
            corps.querySelectorAll('tr').forEach(function (tr, i) {
                tr.querySelector('.im-num').textContent = String(i + 1);
                var rempli = Array.prototype.some.call(tr.querySelectorAll('[data-champ]'), function (el) { return el.value.trim(); });
                if (rempli) { n += 1; }
            });
            var compte = racine.querySelector('#imCompte');
            if (compte) { compte.textContent = n + ' élève(s) saisi(s)'; }
        }

        function ajouterLigne() {
            var tr = document.createElement('tr');
            var num = document.createElement('td');
            num.className = 'im-num';
            tr.appendChild(num);
            CHAMPS.forEach(function (c) { tr.appendChild(cellule(c)); });
            var td = document.createElement('td');
            var suppr = document.createElement('button');
            suppr.type = 'button';
            suppr.className = 'im-suppr';
            suppr.setAttribute('aria-label', 'Supprimer la ligne');
            suppr.innerHTML = '<i class="fas fa-xmark" aria-hidden="true"></i>';
            td.appendChild(suppr);
            tr.appendChild(td);
            corps.appendChild(tr);
            numeroter();
            return tr;
        }

        function sexe(v) {
            var t = (v || '').trim().toUpperCase().charAt(0);
            return t === 'M' || t === 'G' || t === 'H' ? 'M' : (t === 'F' ? 'F' : '');
        }

        for (var i = 0; i < 10; i += 1) { ajouterLigne(); }
        racine.querySelector('#imAjouter').addEventListener('click', function () {
            for (var k = 0; k < 5; k += 1) { ajouterLigne(); }
        });

        corps.addEventListener('click', function (e) {
            var b = e.target.closest('.im-suppr');
            if (b) {
                b.closest('tr').remove();
                if (!corps.querySelector('tr')) { ajouterLigne(); }
                numeroter();
            }
        });
        corps.addEventListener('input', numeroter);
        corps.addEventListener('change', numeroter);

        // Entrée = ligne suivante (créée si besoin) dans la même colonne.
        corps.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter' || !e.target.dataset.champ) { return; }
            e.preventDefault();
            var tr = e.target.closest('tr');
            var suivante = tr.nextElementSibling || ajouterLigne();
            suivante.querySelector('[data-champ="' + e.target.dataset.champ + '"]').focus();
        });

        // Collage de plusieurs lignes copiées depuis Excel (colonnes séparées par des tabulations).
        corps.addEventListener('paste', function (e) {
            var texte = (e.clipboardData || window.clipboardData).getData('text');
            if (!texte || (texte.indexOf('\t') === -1 && texte.indexOf('\n') === -1)) { return; }
            e.preventDefault();
            var depart = CHAMPS.indexOf(e.target.dataset.champ);
            var tr = e.target.closest('tr');
            texte.replace(/\r/g, '').split('\n').filter(function (l) { return l.trim(); }).forEach(function (ligne) {
                if (!tr) { tr = ajouterLigne(); }
                ligne.split('\t').forEach(function (val, j) {
                    var champ = CHAMPS[depart + j];
                    if (!champ) { return; }
                    var el = tr.querySelector('[data-champ="' + champ + '"]');
                    el.value = champ === 'sexe' ? sexe(val) : val.trim();
                });
                tr = tr.nextElementSibling;
            });
            numeroter();
        });
    }

    // Lignes de la grille → champ caché « grille » (JSON), juste avant l'envoi.
    function serialiserGrille(form) {
        var corps = form.querySelector('#imGrille tbody');
        var cible = form.querySelector('#imGrilleJson');
        if (!corps || !cible) { return; }
        var lignes = [];
        corps.querySelectorAll('tr').forEach(function (tr) {
            var l = {};
            tr.querySelectorAll('[data-champ]').forEach(function (el) { l[el.dataset.champ] = el.value.trim(); });
            if (CHAMPS.some(function (c) { return l[c]; })) { lignes.push(l); }
        });
        cible.value = JSON.stringify(lignes);
    }

    // ---------------------------------------------------------------- fenêtre
    var modal = document.getElementById('modalInscriptionMasse');
    if (!modal) { return; }
    var corpsModal = document.getElementById('imModalCorps');
    var url = modal.getAttribute('data-im-url');
    var inscriptionsFaites = false;

    function afficher(html) {
        corpsModal.innerHTML = html;
        corpsModal.scrollTop = 0;
        initDepot(corpsModal);
        initGrille(corpsModal);
        if (window.sxInitFiltres) { window.sxInitFiltres(); }
        if (corpsModal.querySelector('[data-im-etape="resultat"]')) { inscriptionsFaites = true; }
    }

    function erreurReseau() {
        corpsModal.innerHTML = '<p class="im-erreur" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i>'
            + 'La connexion a échoué. Vérifiez le réseau puis réessayez.</p>'
            + '<button type="button" class="sx-btn" data-im-recommencer><i class="fas fa-rotate-right" aria-hidden="true"></i>Réessayer</button>';
    }

    function charger(mode) {
        corpsModal.innerHTML = '<p class="im-chargement"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Chargement…</p>';
        fetch(url + '?mode=' + encodeURIComponent(mode || 'fichier'), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            cache: 'no-store',  // liste des classes toujours à jour
            credentials: 'same-origin'
        }).then(function (r) {
            if (!r.ok) { throw new Error(String(r.status)); }
            return r.text();
        }).then(afficher).catch(erreurReseau);
    }

    window.openModalInscriptionMasse = function (mode) {
        modal.classList.add('active');
        document.body.classList.add('modal-personnel-open');
        charger(mode);
    };

    window.closeModalInscriptionMasse = function () {
        modal.classList.remove('active');
        document.body.classList.remove('modal-personnel-open');
        corpsModal.innerHTML = '';
        // Après une inscription, on recharge la liste pour afficher les nouveaux élèves.
        if (inscriptionsFaites) {
            var adresse = new URL(window.location.href);
            adresse.searchParams.delete('masse');
            window.location.replace(adresse.toString());
        }
    };

    corpsModal.addEventListener('submit', function (e) {
        var form = e.target.closest('[data-im-form]');
        if (!form) { return; }
        e.preventDefault();
        serialiserGrille(form);
        var bouton = form.querySelector('[type="submit"]');
        if (bouton) {
            bouton.disabled = true;
            bouton.insertAdjacentHTML('afterbegin', '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>');
        }
        // getAttribute : le champ caché name="action" masque la propriété form.action.
        fetch(form.getAttribute('action'), {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (r) {
            if (!r.ok) { throw new Error(String(r.status)); }
            return r.text();
        }).then(afficher).catch(erreurReseau);
    });

    corpsModal.addEventListener('click', function (e) {
        if (e.target.closest('[data-im-recommencer]')) { charger('fichier'); }
        if (e.target.closest('[data-im-terminer]')) { window.closeModalInscriptionMasse(); }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) { window.closeModalInscriptionMasse(); }
    });

    var auDemarrage = document.body.getAttribute('data-open-masse-modal');
    if (auDemarrage) { window.openModalInscriptionMasse(auDemarrage); }
})();
