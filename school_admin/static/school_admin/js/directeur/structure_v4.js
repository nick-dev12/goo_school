// Structure pédagogique v4 : menus « ⋯ », filtres de tableaux et de cartes, ouverture des formulaires pré-remplis.
(function () {
    'use strict';

    // ---------------------------------------------------------------- menus « ⋯ »
    function closeMenus(except) {
        document.querySelectorAll('.sx-menu__list:not([hidden])').forEach(function (list) {
            if (list !== except) {
                list.hidden = true;
                var t = list.parentElement.querySelector('.sx-menu__toggle');
                if (t) { t.setAttribute('aria-expanded', 'false'); }
            }
        });
    }

    document.addEventListener('click', function (event) {
        var toggle = event.target.closest('.sx-menu__toggle');
        if (toggle) {
            event.preventDefault();
            var list = toggle.parentElement.querySelector('.sx-menu__list');
            closeMenus(list);
            list.hidden = !list.hidden;
            toggle.setAttribute('aria-expanded', list.hidden ? 'false' : 'true');
            if (!list.hidden) {
                list.style.left = '';
                list.style.right = '';
                var r = list.getBoundingClientRect();
                if (r.left < 8) { list.style.left = '0'; list.style.right = 'auto'; }
            }
            return;
        }
        if (!event.target.closest('.sx-menu__list')) {
            closeMenus(null);
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closeMenus(null); }
    });

    // Confirmation des actions sensibles (data-sx-confirm sur un bouton de formulaire ou un lien).
    document.addEventListener('click', function (event) {
        var el = event.target.closest('[data-sx-confirm]');
        if (el && !window.confirm(el.getAttribute('data-sx-confirm'))) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);

    // ---------------------------------------------------------------- filtres
    // <div data-sx-filter="cible"> contient un input [data-sx-q] et des select [data-sx-f="champ"].
    // Les éléments filtrés portent data-sx-item, data-sx-text (texte cherché) et data-sx-<champ>.
    function normaliser(s) {
        return (s || '').toString().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    }

    function appliquer(bar) {
        var cible = document.querySelector(bar.getAttribute('data-sx-filter'));
        if (!cible) { return; }
        var qInput = bar.querySelector('[data-sx-q]');
        var q = normaliser(qInput ? qInput.value : '').trim();
        var filtres = Array.prototype.map.call(bar.querySelectorAll('[data-sx-f]'), function (s) {
            return { champ: s.getAttribute('data-sx-f'), val: s.value, onglet: s.hidden };
        }).filter(function (f) { return f.val !== ''; });
        var visibles = 0;
        var items = cible.querySelectorAll('[data-sx-item]');
        items.forEach(function (el) {
            var ok = !q || normaliser(el.getAttribute('data-sx-text') || el.textContent).indexOf(q) !== -1;
            filtres.forEach(function (f) {
                if (!ok) { return; }
                var v = el.getAttribute('data-sx-' + f.champ) || '';
                // Valeur multiple « |3|5| » (ex. plusieurs matières) : on cherche l'élément dans la liste.
                ok = v.charAt(0) === '|' ? v.indexOf('|' + f.val + '|') !== -1 : v === f.val;
            });
            el.hidden = !ok;
            if (ok) { visibles += 1; }
        });
        // Titres de groupe sans élément visible : masqués.
        cible.querySelectorAll('[data-sx-group]').forEach(function (g) {
            var nom = g.getAttribute('data-sx-group');
            var reste = cible.querySelector('[data-sx-item][data-sx-in="' + nom + '"]:not([hidden])');
            g.hidden = !reste;
        });
        var vide = cible.querySelector('[data-sx-none]');
        if (vide) { vide.hidden = visibles !== 0; }
        var compte = bar.querySelector('[data-sx-count]');
        if (compte) {
            var unite = compte.getAttribute('data-sx-count') || 'éléments';
            compte.textContent = visibles + ' / ' + items.length + ' ' + unite;
        }
        var reset = bar.querySelector('[data-sx-reset]');
        // Les filtres pilotés par des onglets (sélecteurs masqués) ne comptent pas : l'onglet reste choisi.
        if (reset) { reset.hidden = !q && !filtres.filter(function (f) { return !f.onglet; }).length; }
    }

    function initFiltres() {
        document.querySelectorAll('[data-sx-filter]').forEach(function (bar) {
            if (bar.dataset.sxInit) { return; }
            bar.dataset.sxInit = '1';
            bar.addEventListener('input', function () { appliquer(bar); });
            bar.addEventListener('change', function () { appliquer(bar); });
            var reset = bar.querySelector('[data-sx-reset]');
            if (reset) {
                reset.addEventListener('click', function () {
                    bar.querySelectorAll('[data-sx-q], [data-sx-f]:not([hidden])').forEach(function (c) { c.value = ''; });
                    appliquer(bar);
                });
            }
            // Pré-sélection depuis l'URL (?filiere=…&niveau=…)
            var params = new URLSearchParams(window.location.search);
            bar.querySelectorAll('[data-sx-f]').forEach(function (s) {
                var v = params.get('f_' + s.getAttribute('data-sx-f'));
                if (v !== null && s.querySelector('option[value="' + CSS.escape(v) + '"]')) { s.value = v; }
            });
            appliquer(bar);
        });
    }

    // ---------------------------------------------------------------- formulaires pré-remplis
    // <button data-sx-open="#addClasseModal" data-sx-set='{"department":"3","niveau_lmd":"L2"}'>
    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-sx-open]');
        if (!btn) { return; }
        var modal = document.querySelector(btn.getAttribute('data-sx-open'));
        if (!modal) { return; }
        event.preventDefault();
        var valeurs = {};
        try { valeurs = JSON.parse(btn.getAttribute('data-sx-set') || '{}'); } catch (e) { valeurs = {}; }
        Object.keys(valeurs).forEach(function (nom) {
            var champ = modal.querySelector('[name="' + nom + '"]');
            if (champ) {
                champ.value = valeurs[nom];
                champ.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        var premier = modal.querySelector('input:not([type="hidden"]), select, textarea');
        if (premier) { window.setTimeout(function () { premier.focus(); }, 60); }
    });

    // ---------------------------------------------------------------- onglets sx
    // <div class="sx-tabs" role="tablist" data-sx-tabs="cle"> avec des boutons .sx-tab :
    //   data-sx-panel="id"            → affiche le panneau #id (les autres panneaux du même groupe sont masqués) ;
    //   data-sx-set="#select|valeur"  → règle un filtre de la barre d'outils (onglets qui filtrent un tableau).
    // Le dernier onglet choisi est retenu pour la page (confort, sans conséquence s'il est perdu).
    function activerOnglet(btn, memoriser) {
        var barre = btn.closest('.sx-tabs');
        if (!barre) { return; }
        barre.querySelectorAll('.sx-tab').forEach(function (b) {
            var actif = b === btn;
            b.classList.toggle('active', actif);
            b.setAttribute('aria-selected', actif ? 'true' : 'false');
        });
        var panneau = btn.getAttribute('data-sx-panel');
        if (panneau) {
            var cible = document.getElementById(panneau);
            if (cible && cible.parentElement) {
                Array.prototype.forEach.call(cible.parentElement.children, function (p) {
                    if (p.classList.contains('sx-tabpanel')) { p.hidden = p !== cible; }
                });
            }
        }
        var reglage = btn.getAttribute('data-sx-set');
        if (reglage) {
            var parts = reglage.split('|');
            var champ = document.querySelector(parts[0]);
            if (champ) {
                champ.value = parts.slice(1).join('|');
                champ.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        if (memoriser && barre.getAttribute('data-sx-tabs')) {
            try { window.sessionStorage.setItem('sx-tab:' + location.pathname + ':' + barre.getAttribute('data-sx-tabs'), btn.getAttribute('data-sx-key') || ''); } catch (e) { /* stockage indisponible */ }
        }
    }
    document.addEventListener('click', function (event) {
        var btn = event.target.closest('.sx-tab');
        if (btn) {
            event.preventDefault();
            activerOnglet(btn, true);
        }
    });
    function initOnglets() {
        document.querySelectorAll('.sx-tabs[data-sx-tabs]').forEach(function (barre) {
            var cle = null;
            try { cle = window.sessionStorage.getItem('sx-tab:' + location.pathname + ':' + barre.getAttribute('data-sx-tabs')); } catch (e) { cle = null; }
            var btn = (cle && barre.querySelector('.sx-tab[data-sx-key="' + CSS.escape(cle) + '"]')) || barre.querySelector('.sx-tab.active') || barre.querySelector('.sx-tab');
            if (btn) { activerOnglet(btn, false); }
        });
    }

    // ---------------------------------------------------------------- tout déplier / replier (<details>)
    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-sx-deplier]');
        if (!btn) { return; }
        var zone = document.querySelector(btn.getAttribute('data-sx-deplier'));
        if (!zone) { return; }
        var blocs = zone.querySelectorAll('details:not([hidden])');
        var ouvrir = Array.prototype.some.call(blocs, function (d) { return !d.open; });
        blocs.forEach(function (d) { d.open = ouvrir; });
        btn.lastChild.textContent = ouvrir ? 'Tout replier' : 'Tout déplier';
    });

    // ---------------------------------------------------------------- liens vers un onglet de la page
    // [data-sx-tab="eleves"] ou adresse terminée par #eleves : ouvre l'onglet .tab-btn[data-tab="eleves"].
    function ouvrirOnglet(nom) {
        var btn = document.querySelector('.tab-btn[data-tab="' + CSS.escape(nom) + '"]');
        if (btn) {
            btn.click();
            var conteneur = btn.closest('.tabs-container') || btn;
            window.setTimeout(function () { conteneur.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 30);
        }
        return !!btn;
    }
    document.addEventListener('click', function (event) {
        var lien = event.target.closest('[data-sx-tab]');
        if (lien) {
            event.preventDefault();
            ouvrirOnglet(lien.getAttribute('data-sx-tab'));
        }
    });
    window.addEventListener('load', function () {
        if (window.location.hash.length > 1) { ouvrirOnglet(window.location.hash.slice(1)); }
    });

    function demarrer() {
        initFiltres();
        initOnglets();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', demarrer);
    } else {
        demarrer();
    }
    window.sxInitFiltres = initFiltres;
})();
