// Inscription en masse : dépôt de fichier et grille de saisie rapide (collage depuis Excel accepté).
(function () {
    'use strict';

    // ---------------------------------------------------------------- dépôt de fichier
    var depot = document.getElementById('imDepot');
    var input = document.getElementById('imInput');
    var nom = document.getElementById('imNomFichier');
    if (depot && input) {
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
    var table = document.getElementById('imGrille');
    if (!table) { return; }
    var corps = table.querySelector('tbody');
    var CHAMPS = ['nom', 'prenom', 'sexe', 'date_naissance', 'parent_telephone', 'parent_nom'];

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

    function numeroter() {
        var n = 0;
        corps.querySelectorAll('tr').forEach(function (tr, i) {
            tr.querySelector('.im-num').textContent = String(i + 1);
            var rempli = Array.prototype.some.call(tr.querySelectorAll('[data-champ]'), function (el) { return el.value.trim(); });
            if (rempli) { n += 1; }
        });
        var compte = document.getElementById('imCompte');
        if (compte) { compte.textContent = n + ' élève(s) saisi(s)'; }
    }

    function sexe(v) {
        var t = (v || '').trim().toUpperCase().charAt(0);
        return t === 'M' || t === 'G' || t === 'H' ? 'M' : (t === 'F' ? 'F' : '');
    }

    for (var i = 0; i < 10; i += 1) { ajouterLigne(); }
    document.getElementById('imAjouter').addEventListener('click', function () {
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

    document.getElementById('imFormGrille').addEventListener('submit', function () {
        var lignes = [];
        corps.querySelectorAll('tr').forEach(function (tr) {
            var l = {};
            tr.querySelectorAll('[data-champ]').forEach(function (el) { l[el.dataset.champ] = el.value.trim(); });
            if (CHAMPS.some(function (c) { return l[c]; })) { lignes.push(l); }
        });
        document.getElementById('imGrilleJson').value = JSON.stringify(lignes);
    });
})();
