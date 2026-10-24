// Barres d'onglets de tout le site : débordement (« Autres … ») et niveau principal / secondaire.
//
// Chaque barre n'affiche que les onglets qui tiennent sur une ligne, suivis d'un bouton qui ouvre
// la liste des autres. Les onglets en trop restent à leur place dans le DOM (masqués par la classe
// ovf-cache) : le menu contient des copies qui déclenchent l'onglet d'origine. Les écouteurs posés
// par les pages, les formulaires et les liens continuent donc de fonctionner.
//
// Niveau : une barre placée dans le panneau d'un autre onglet (ou marquée data-tabs-level="secondary")
// est secondaire et reçoit un style souligné ; les autres sont principales (onglets pleins).
(function () {
    'use strict';

    if (window.__ovfTabsBooted) {
        return;
    }
    window.__ovfTabsBooted = true;

    var PRESETS = [
        {
            bar: '.matiere-tabs-bar', track: '.matiere-tabs-track', moreWrap: '.matiere-tabs-more-wrap',
            moreBtn: '.matiere-tabs-more-btn', menu: '.matiere-tabs-overflow-menu', label: '.matiere-tabs-more-label'
        },
        {
            bar: '.cls-cat-nav-bar', track: '.cls-cat-nav-track', moreWrap: '.cls-cat-more-wrap',
            moreBtn: '.cls-cat-more-btn', menu: '.cls-cat-overflow-menu', label: '.cls-cat-more-label'
        },
        {
            bar: '.tabs-overflow-bar', track: '.tabs-overflow-track', moreWrap: '.tabs-overflow-more-wrap',
            moreBtn: '.tabs-overflow-more-btn', menu: '.tabs-overflow-menu', label: '.tabs-overflow-more-label'
        }
    ];
    var BAR_SELECTOR = PRESETS.map(function (p) { return p.bar; }).join(',');

    // Conteneurs candidats : ils ne sont retenus que s'ils ne contiennent qu'une suite d'onglets.
    var CANDIDATS = [
        '[role="tablist"]', '.tabs-nav', '.sub-tabs', 'nav[class*="tabs"]', 'div[class*="tabs"]',
        'form[class*="tabs"]', 'nav[class*="tab-bar"]', 'div[class*="tab-bar"]'
    ].join(',');
    var ITEM_SELECTOR = ':scope > button, :scope > a, :scope > [role="tab"]';
    var PANNEAUX = [
        '[role="tabpanel"]', '[data-main-panel]', '[data-tab-panel]', '.tab-content', '.tab-pane',
        '[class*="tab-panel"]', '[class*="tab-pane"]', '[class*="tab-content"]'
    ].join(',');

    function presetOf(bar) {
        for (var i = 0; i < PRESETS.length; i += 1) {
            if (bar.matches(PRESETS[i].bar)) {
                return PRESETS[i];
            }
        }
        return null;
    }

    function isActive(el) {
        return el.classList.contains('active') || el.classList.contains('is-active') ||
            el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-current') === 'page';
    }

    function itemsOf(track) {
        return Array.prototype.filter.call(track.querySelectorAll(ITEM_SELECTOR), function (el) {
            return !el.hasAttribute('hidden') && !el.matches('[class*="more-btn"], .ovf-more-btn');
        });
    }

    // ---------------------------------------------------------------- niveau principal / secondaire
    function levelOf(bar) {
        var explicite = bar.closest('[data-tabs-level]');
        if (explicite) {
            return explicite.getAttribute('data-tabs-level') === 'secondary' ? 'secondary' : 'primary';
        }
        var track = bar.querySelector('[data-ovf-track]') || bar;
        if (/subtab|sub-tab/.test(track.className + ' ' + (bar.parentElement ? bar.parentElement.className : ''))) {
            return 'secondary';
        }
        // Dans le panneau d'un onglet, avec une barre placée avant hors de ce panneau : secondaire.
        var panneau = bar.parentElement ? bar.parentElement.closest(PANNEAUX) : null;
        var premiere = document.querySelector(BAR_SELECTOR);
        if (panneau && premiere && premiere !== bar && !panneau.contains(premiere)) {
            return 'secondary';
        }
        return 'primary';
    }

    // ---------------------------------------------------------------- création d'une barre générique
    function buildGenericBar(track) {
        var plural = track.getAttribute('data-overflow-items-label') || 'onglets';
        var bar = document.createElement('div');
        bar.className = 'tabs-overflow-bar';
        bar.setAttribute('data-overflow-items-label', plural);
        bar.setAttribute('data-overflow-item-label', track.getAttribute('data-overflow-item-label') || 'onglet');
        track.parentNode.insertBefore(bar, track);
        bar.appendChild(track);
        track.classList.add('tabs-overflow-track');

        var wrap = document.createElement('div');
        wrap.className = 'tabs-overflow-more-wrap';
        wrap.hidden = true;
        wrap.innerHTML =
            '<button type="button" class="tabs-overflow-more-btn" aria-expanded="false" aria-haspopup="true">' +
            '<span class="tabs-overflow-more-label"></span></button>' +
            '<div class="tabs-overflow-menu" role="menu" hidden></div>';
        bar.appendChild(wrap);
        return bar;
    }

    function enhanceCandidates(root) {
        (root || document).querySelectorAll(CANDIDATS).forEach(function (track) {
            if (track.dataset.ovfTrack || track.getAttribute('data-tabs-overflow') === 'off' ||
                track.closest(BAR_SELECTOR) || track.closest('[data-tabs-overflow="off"]')) {
                return;
            }
            var items = itemsOf(track);
            if (items.length < 2) {
                return;
            }
            // Uniquement une suite d'onglets (champs cachés tolérés), pas un bloc de mise en page.
            var autres = Array.prototype.filter.call(track.children, function (c) {
                return items.indexOf(c) === -1 && !(c.tagName === 'INPUT' && c.type === 'hidden') &&
                    c.tagName !== 'SCRIPT' && !c.hasAttribute('hidden');
            });
            if (autres.length) {
                return;
            }
            initBar(buildGenericBar(track));
        });
        document.querySelectorAll(BAR_SELECTOR).forEach(function (bar) {
            if (!bar.dataset.ovfInit) {
                initBar(bar);
            }
        });
    }

    // ---------------------------------------------------------------- mise en page
    function parts(bar) {
        var p = presetOf(bar);
        if (!p) {
            return null;
        }
        var track = bar.querySelector(p.track);
        var wrap = bar.querySelector(p.moreWrap);
        var btn = bar.querySelector(p.moreBtn);
        var menu = bar.querySelector(p.menu);
        if (!track || !wrap || !btn || !menu) {
            return null;
        }
        return { track: track, wrap: wrap, btn: btn, menu: menu, label: bar.querySelector(p.label) };
    }

    function closeMenu(bar) {
        var q = parts(bar);
        if (q) {
            q.menu.hidden = true;
            q.btn.setAttribute('aria-expanded', 'false');
        }
    }

    function gapOf(track) {
        var g = parseFloat(window.getComputedStyle(track).columnGap);
        return isNaN(g) ? 6 : g;
    }

    function setMoreLabel(bar, q, count) {
        var plural = bar.getAttribute('data-overflow-items-label') || 'onglets';
        var singulier = bar.getAttribute('data-overflow-item-label') || 'onglet';
        var texte = count > 1 ? 'Afficher ' + count + ' autres ' + plural : 'Afficher 1 autre ' + singulier;
        if (q.label) {
            q.label.textContent = 'Autres ' + plural;
        }
        var badge = q.btn.querySelector('.ovf-more-count');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'ovf-more-count';
            q.btn.appendChild(badge);
        }
        badge.textContent = String(count);
        if (!q.btn.querySelector('.ovf-more-chevron')) {
            var chevron = document.createElement('i');
            chevron.className = 'fas fa-chevron-down ovf-more-chevron';
            chevron.setAttribute('aria-hidden', 'true');
            q.btn.appendChild(chevron);
        }
        Array.prototype.forEach.call(q.btn.querySelectorAll('i:not(.ovf-more-chevron)'), function (i) {
            i.remove();
        });
        q.btn.setAttribute('aria-label', texte);
        q.btn.setAttribute('title', texte);
    }

    function buildMenu(bar, q, caches) {
        q.menu.innerHTML = '';
        caches.forEach(function (orig) {
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'ovf-menu-item' + (isActive(orig) ? ' is-active' : '');
            item.setAttribute('role', 'menuitem');
            item.innerHTML = orig.innerHTML;
            Array.prototype.forEach.call(item.querySelectorAll('[id]'), function (n) { n.removeAttribute('id'); });
            item.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                closeMenu(bar);
                orig.click();
                window.requestAnimationFrame(function () { layout(bar); });
            });
            q.menu.appendChild(item);
        });
    }

    function layout(bar) {
        var q = parts(bar);
        if (!q) {
            return;
        }
        var items = itemsOf(q.track);
        items.forEach(function (el) { el.classList.remove('ovf-cache'); });
        q.wrap.hidden = true;
        closeMenu(bar);
        bar.dataset.ovfActive = String(items.findIndex(isActive));

        var dispo = bar.clientWidth;
        if (!dispo || items.length < 2) {
            return;
        }
        var gap = gapOf(q.track);
        var largeurs = items.map(function (el) { return el.offsetWidth; });
        var total = largeurs.reduce(function (a, w) { return a + w + gap; }, 0) - gap;
        if (total <= dispo + 1) {
            return;
        }

        q.wrap.hidden = false;
        setMoreLabel(bar, q, items.length);
        var place = dispo - q.wrap.offsetWidth - gap;
        var visibles = [];
        var utilise = 0;
        for (var i = 0; i < items.length; i += 1) {
            var w = largeurs[i] + (visibles.length ? gap : 0);
            if (utilise + w > place && visibles.length) {
                break;
            }
            visibles.push(i);
            utilise += w;
        }
        // L'onglet actif reste toujours visible : on retire les derniers visibles jusqu'à ce qu'il tienne.
        var actif = items.findIndex(isActive);
        if (actif >= 0 && visibles.indexOf(actif) === -1) {
            while (visibles.length && utilise + gap + largeurs[actif] > place) {
                var retire = visibles.pop();
                utilise -= largeurs[retire] + (visibles.length ? gap : 0);
            }
            visibles.push(actif);
        }
        var caches = items.filter(function (el, idx) { return visibles.indexOf(idx) === -1; });
        if (!caches.length) {
            q.wrap.hidden = true;
            return;
        }
        caches.forEach(function (el) { el.classList.add('ovf-cache'); });
        setMoreLabel(bar, q, caches.length);
        buildMenu(bar, q, caches);
    }

    function toggleMenu(bar) {
        var q = parts(bar);
        if (!q) {
            return;
        }
        if (!q.menu.hidden) {
            closeMenu(bar);
            return;
        }
        document.querySelectorAll(BAR_SELECTOR).forEach(function (b) { if (b !== bar) { closeMenu(b); } });
        q.menu.hidden = false;
        q.btn.setAttribute('aria-expanded', 'true');
        // Ouvre vers la gauche si le menu sortirait de l'écran.
        q.menu.classList.remove('ovf-menu--right');
        if (q.menu.getBoundingClientRect().right > window.innerWidth - 8) {
            q.menu.classList.add('ovf-menu--right');
        }
    }

    function initBar(bar) {
        var q = parts(bar);
        if (!q || bar.dataset.ovfInit) {
            return;
        }
        bar.dataset.ovfInit = '1';
        q.track.dataset.ovfTrack = '1';
        q.wrap.classList.add('ovf-more-wrap');
        q.btn.classList.add('ovf-more-btn');
        bar.classList.add('ovf-bar', 'ovf-bar--' + levelOf(bar));
        itemsOf(q.track).forEach(function (el) {
            el.classList.add('ovf-tab');
            if (!el.getAttribute('title')) {
                el.setAttribute('title', el.textContent.replace(/\s+/g, ' ').trim());
            }
        });

        layout(bar);
        if (typeof ResizeObserver !== 'undefined') {
            var largeur = bar.clientWidth;
            new ResizeObserver(function () {
                if (bar.clientWidth !== largeur) {
                    largeur = bar.clientWidth;
                    layout(bar);
                }
            }).observe(bar);
        }
        // Changement d'onglet piloté par la page (clic, script, URL) : on recalcule si l'actif change.
        new MutationObserver(function () {
            var actif = String(itemsOf(q.track).findIndex(isActive));
            if (actif !== bar.dataset.ovfActive) {
                window.requestAnimationFrame(function () { layout(bar); });
            }
        }).observe(q.track, { subtree: true, attributes: true, attributeFilter: ['class', 'aria-selected', 'aria-current'] });
    }

    // ---------------------------------------------------------------- événements globaux
    document.addEventListener('click', function (event) {
        var btn = event.target.closest('.ovf-more-btn');
        if (btn) {
            var bar = btn.closest(BAR_SELECTOR);
            if (bar) {
                event.preventDefault();
                event.stopPropagation();
                toggleMenu(bar);
            }
            return;
        }
        document.querySelectorAll(BAR_SELECTOR).forEach(function (b) {
            if (!b.contains(event.target)) {
                closeMenu(b);
            }
        });
    }, true);

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            document.querySelectorAll(BAR_SELECTOR).forEach(closeMenu);
        }
    });

    window.addEventListener('resize', function () {
        if (typeof ResizeObserver === 'undefined') {
            window.layoutTabsOverflowNav();
        }
    });

    function wrapGlobalTabSwitchers() {
        ['switchMainTab', 'showSubTab', 'showTab'].forEach(function (name) {
            if (typeof window[name] !== 'function' || window[name].__overflowWrapped) {
                return;
            }
            var original = window[name];
            window[name] = function () {
                var result = original.apply(this, arguments);
                window.layoutTabsOverflowNav();
                return result;
            };
            window[name].__overflowWrapped = true;
        });
    }

    window.layoutTabsOverflowNav = function () {
        enhanceCandidates(document);
        document.querySelectorAll(BAR_SELECTOR).forEach(layout);
    };
    window.layoutMatiereTabsNav = window.layoutTabsOverflowNav;
    window.layoutClassesCategoryNav = window.layoutTabsOverflowNav;

    function boot() {
        enhanceCandidates(document);
        wrapGlobalTabSwitchers();
        // Contenu remplacé en direct (temps réel, partiels) : nouvelles barres à équiper.
        var attente = null;
        new MutationObserver(function (mutations) {
            var ajout = mutations.some(function (m) { return m.addedNodes.length; });
            if (!ajout || attente) {
                return;
            }
            attente = window.setTimeout(function () {
                attente = null;
                enhanceCandidates(document);
            }, 150);
        }).observe(document.body, { childList: true, subtree: true });
        // Les polices (icônes) changent la largeur des onglets après le premier calcul.
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () { document.querySelectorAll(BAR_SELECTOR).forEach(layout); });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
