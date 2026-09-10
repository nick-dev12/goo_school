// Liste classes — navigation panneaux par catégorie (overflow via tabs_nav_overflow.js)

document.addEventListener('DOMContentLoaded', function () {
    initClassesCategoryTabs();
});

function slugifyClsCategory(text) {
    return text
        .toString()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');
}

function getAllClsCatButtons() {
    var track = document.getElementById('clsCatNavTrack');
    var menu = document.getElementById('clsCatOverflowMenu');
    if (!track || !menu) {
        return [];
    }
    var buttons = Array.prototype.slice.call(track.querySelectorAll('.cls-cat-btn'));
    buttons = buttons.concat(Array.prototype.slice.call(menu.querySelectorAll('.cls-cat-btn')));
    buttons.sort(function (a, b) {
        return parseInt(a.getAttribute('data-order') || '0', 10) - parseInt(b.getAttribute('data-order') || '0', 10);
    });
    return buttons;
}

function activateClsCategory(category) {
    var buttons = getAllClsCatButtons();
    var panels = document.querySelectorAll('.cls-panel[data-cls-panel]');

    buttons.forEach(function (btn) {
        var isActive = btn.getAttribute('data-category') === category;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    panels.forEach(function (panel) {
        panel.classList.toggle('active', panel.id === 'panel-' + slugifyClsCategory(category));
    });

    if (typeof window.layoutTabsOverflowNav === 'function') {
        window.layoutTabsOverflowNav();
    }
}

function initClassesCategoryTabs() {
    var track = document.getElementById('clsCatNavTrack');
    var menu = document.getElementById('clsCatOverflowMenu');
    if (!track) {
        return;
    }

    function onTabClick(event) {
        var btn = event.target.closest('.cls-cat-btn[data-category]');
        if (!btn) {
            return;
        }
        activateClsCategory(btn.getAttribute('data-category'));
    }

    track.addEventListener('click', onTabClick);
    if (menu) {
        menu.addEventListener('click', onTabClick);
    }
}
