// Overflow générique des barres d'onglets (directeur)

var TABS_OVERFLOW_GAP = 6;
var TABS_OVERFLOW_MORE_WIDTH = 140;

var TAB_BUTTON_SELECTORS = [
    '.cls-cat-btn',
    '.matiere-tab-btn',
    '.edt-cat-btn',
    '.tab-btn',
    '.tab-button',
    '.sub-tab-button'
];

var OVERFLOW_PRESETS = [
    {
        bar: '.cls-cat-nav-bar',
        track: '.cls-cat-nav-track',
        menu: '.cls-cat-overflow-menu',
        moreWrap: '.cls-cat-more-wrap',
        moreBtn: '.cls-cat-more-btn',
        label: '.cls-cat-more-label',
        btn: '.cls-cat-btn'
    },
    {
        bar: '.matiere-tabs-bar',
        track: '.matiere-tabs-track',
        menu: '.matiere-tabs-overflow-menu',
        moreWrap: '.matiere-tabs-more-wrap',
        moreBtn: '.matiere-tabs-more-btn',
        label: '.matiere-tabs-more-label',
        btn: '.matiere-tab-btn, .tab-btn'
    },
    {
        bar: '.tabs-overflow-bar',
        track: '.tabs-overflow-track',
        menu: '.tabs-overflow-menu',
        moreWrap: '.tabs-overflow-more-wrap',
        moreBtn: '.tabs-overflow-more-btn',
        label: '.tabs-overflow-more-label',
        btn: null
    }
];

function bootTabsNavOverflow() {
    autoEnhanceTabTracks();
    OVERFLOW_PRESETS.forEach(function (preset) {
        document.querySelectorAll(preset.bar).forEach(function (bar) {
            initTabsOverflowBar(bar, preset);
        });
    });
    wrapGlobalTabSwitchers();
}

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

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootTabsNavOverflow);
} else {
    bootTabsNavOverflow();
}

function resolveTabButtons(container, btnSelector) {
    if (btnSelector) {
        return Array.prototype.slice.call(container.querySelectorAll(btnSelector));
    }
    var i;
    for (i = 0; i < TAB_BUTTON_SELECTORS.length; i += 1) {
        var found = container.querySelectorAll(TAB_BUTTON_SELECTORS[i]);
        if (found.length) {
            return Array.prototype.slice.call(found);
        }
    }
    return Array.prototype.slice.call(container.querySelectorAll(':scope > button'));
}

function detectOverflowLabels(track) {
    var labelled = track.closest('[data-overflow-items-label]');
    if (labelled) {
        return {
            singular: labelled.getAttribute('data-overflow-item-label') || 'élément',
            plural: labelled.getAttribute('data-overflow-items-label') || 'éléments'
        };
    }
    if (track.closest('.types-tabs, .salles-section')) {
        return { singular: 'type', plural: 'types' };
    }
    if (track.closest('.sub-tabs-container')) {
        return { singular: 'niveau', plural: 'niveaux' };
    }
    if (track.closest('.tabs-container, .tabs-header, .main-content-container, .page-container')) {
        return { singular: 'niveau', plural: 'niveaux' };
    }
    return { singular: 'élément', plural: 'éléments' };
}

function autoEnhanceTabTracks() {
    var selectors = [
        '.types-tabs > .tabs-nav',
        '.tabs-header > .tabs-nav',
        '.tabs-container > .tabs-nav',
        '.sub-tabs-container > .sub-tabs'
    ];

    selectors.forEach(function (selector) {
        document.querySelectorAll(selector).forEach(function (track) {
            enhanceTabTrack(track);
        });
    });
}

function enhanceTabTrack(track) {
    if (!track || track.dataset.overflowEnhanced === '1') {
        return;
    }
    if (track.closest('.tabs-overflow-bar, .matiere-tabs-bar, .cls-cat-nav-bar')) {
        return;
    }
    if (track.getAttribute('data-tabs-overflow') === 'off') {
        return;
    }

    var buttons = resolveTabButtons(track);
    if (buttons.length < 2) {
        return;
    }

    var labels = detectOverflowLabels(track);
    var bar = document.createElement('div');
    bar.className = 'tabs-overflow-bar';
    bar.setAttribute('data-overflow-item-label', labels.singular);
    bar.setAttribute('data-overflow-items-label', labels.plural);

    var parent = track.parentNode;
    parent.insertBefore(bar, track);

    track.classList.add('tabs-overflow-track');
    bar.appendChild(track);

    var moreWrap = document.createElement('div');
    moreWrap.className = 'tabs-overflow-more-wrap';
    moreWrap.hidden = true;

    var moreBtn = document.createElement('button');
    moreBtn.type = 'button';
    moreBtn.className = 'tabs-overflow-more-btn';
    moreBtn.setAttribute('aria-expanded', 'false');
    moreBtn.setAttribute('aria-haspopup', 'true');
    moreBtn.innerHTML =
        '<i class="fas fa-chevron-down" aria-hidden="true"></i>' +
        '<span class="tabs-overflow-more-label">Autres ' + labels.plural + '</span>';

    var menu = document.createElement('div');
    menu.className = 'tabs-overflow-menu';
    menu.setAttribute('role', 'menu');
    menu.hidden = true;

    moreWrap.appendChild(moreBtn);
    moreWrap.appendChild(menu);
    bar.appendChild(moreWrap);

    buttons.forEach(function (btn, index) {
        if (!btn.getAttribute('data-order')) {
            btn.setAttribute('data-order', String(index));
        }
    });

    track.dataset.overflowEnhanced = '1';
    initTabsOverflowBar(bar, OVERFLOW_PRESETS[2]);
}

function getOverflowButtons(bar, preset) {
    var track = bar.querySelector(preset.track);
    var menu = bar.querySelector(preset.menu);
    if (!track || !menu) {
        return [];
    }

    var buttons = resolveTabButtons(track, preset.btn);
    buttons = buttons.concat(resolveTabButtons(menu, preset.btn));
    buttons.sort(function (a, b) {
        return parseInt(a.getAttribute('data-order') || '0', 10) - parseInt(b.getAttribute('data-order') || '0', 10);
    });
    return buttons;
}

function closeTabsOverflowMenu(bar, preset) {
    var menu = bar.querySelector(preset.menu);
    var moreBtn = bar.querySelector(preset.moreBtn);
    if (!menu || !moreBtn) {
        return;
    }
    menu.hidden = true;
    moreBtn.setAttribute('aria-expanded', 'false');
}

function updateTabsOverflowLabel(bar, preset, overflowCount) {
    var labelEl = bar.querySelector(preset.label);
    var moreBtn = bar.querySelector(preset.moreBtn);
    if (!labelEl || !moreBtn) {
        return;
    }

    var singular = bar.getAttribute('data-overflow-item-label') || 'élément';
    var plural = bar.getAttribute('data-overflow-items-label') || 'éléments';
    var count = overflowCount || 0;

    labelEl.textContent = 'Autres ' + plural;
    moreBtn.setAttribute(
        'aria-label',
        'Afficher ' + count + ' autre' + (count > 1 ? 's' : '') + ' ' + (count > 1 ? plural : singular)
    );
    moreBtn.setAttribute(
        'title',
        'Afficher ' + count + ' autre' + (count > 1 ? 's' : '') + ' ' + (count > 1 ? plural : singular)
    );
}

function layoutTabsOverflowBar(bar, preset) {
    var track = bar.querySelector(preset.track);
    var menu = bar.querySelector(preset.menu);
    var moreWrap = bar.querySelector(preset.moreWrap);
    var moreBtn = bar.querySelector(preset.moreBtn);
    if (!track || !menu || !moreWrap) {
        return;
    }

    var allButtons = getOverflowButtons(bar, preset);
    if (!allButtons.length) {
        return;
    }

    allButtons.forEach(function (btn) {
        track.appendChild(btn);
    });
    menu.innerHTML = '';
    moreWrap.hidden = true;
    closeTabsOverflowMenu(bar, preset);

    var totalWidth = 0;
    allButtons.forEach(function (btn) {
        totalWidth += btn.offsetWidth + TABS_OVERFLOW_GAP;
    });

    if (totalWidth <= bar.clientWidth) {
        return;
    }

    moreWrap.hidden = false;
    var moreBtnWidth = moreBtn ? moreBtn.offsetWidth + TABS_OVERFLOW_GAP : TABS_OVERFLOW_MORE_WIDTH;
    var availableWidth = Math.max(bar.clientWidth - moreBtnWidth, 100);
    var usedWidth = 0;
    var splitAt = allButtons.length;

    for (var i = 0; i < allButtons.length; i += 1) {
        var btnWidth = allButtons[i].offsetWidth + TABS_OVERFLOW_GAP;
        if (i > 0 && usedWidth + btnWidth > availableWidth) {
            splitAt = i;
            break;
        }
        usedWidth += btnWidth;
    }

    var activeBtn = allButtons.filter(function (b) {
        return b.classList.contains('active');
    })[0];
    var activeIndex = activeBtn ? allButtons.indexOf(activeBtn) : 0;

    if (activeIndex >= splitAt && splitAt > 0) {
        var lastVisible = allButtons[splitAt - 1];
        var active = allButtons[activeIndex];
        allButtons[splitAt - 1] = active;
        allButtons[activeIndex] = lastVisible;
    }

    var visibleButtons = allButtons.slice(0, splitAt);
    var overflowButtons = allButtons.slice(splitAt);

    visibleButtons.forEach(function (btn) {
        track.appendChild(btn);
    });

    if (overflowButtons.length) {
        overflowButtons.forEach(function (btn) {
            menu.appendChild(btn);
        });
        moreWrap.hidden = false;
        updateTabsOverflowLabel(bar, preset, overflowButtons.length);
    } else {
        moreWrap.hidden = true;
    }
}

function resolveOverflowPreset(bar) {
    var i;
    for (i = 0; i < OVERFLOW_PRESETS.length; i += 1) {
        if (bar.matches(OVERFLOW_PRESETS[i].bar)) {
            return OVERFLOW_PRESETS[i];
        }
    }
    return null;
}

function toggleTabsOverflowMenu(bar, preset) {
    var menu = bar.querySelector(preset.menu);
    var moreBtn = bar.querySelector(preset.moreBtn);
    if (!menu || !moreBtn) {
        return;
    }
    if (!menu.hidden) {
        closeTabsOverflowMenu(bar, preset);
    } else {
        menu.hidden = false;
        moreBtn.setAttribute('aria-expanded', 'true');
    }
}

function initTabsOverflowBar(bar, preset) {
    if (bar.dataset.overflowInit === '1') {
        layoutTabsOverflowBar(bar, preset);
        return;
    }

    var moreBtn = bar.querySelector(preset.moreBtn);
    var menu = bar.querySelector(preset.menu);
    if (!moreBtn || !menu) {
        return;
    }

    bar.dataset.overflowInit = '1';
    layoutTabsOverflowBar(bar, preset);

    if (typeof ResizeObserver !== 'undefined') {
        var observer = new ResizeObserver(function () {
            layoutTabsOverflowBar(bar, preset);
        });
        observer.observe(bar);
    } else {
        window.addEventListener('resize', function () {
            layoutTabsOverflowBar(bar, preset);
        });
    }

    bar.addEventListener('click', function (event) {
        var btnSelector = preset.btn || TAB_BUTTON_SELECTORS.join(',');
        if (event.target.closest(btnSelector)) {
            closeTabsOverflowMenu(bar, preset);
            window.requestAnimationFrame(function () {
                layoutTabsOverflowBar(bar, preset);
            });
        }
    });

    document.addEventListener('click', function (event) {
        if (!bar.contains(event.target)) {
            closeTabsOverflowMenu(bar, preset);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeTabsOverflowMenu(bar, preset);
        }
    });
}

if (!window.__tabsOverflowCaptureBound) {
    window.__tabsOverflowCaptureBound = true;
    document.addEventListener('click', function (event) {
        var moreBtn = event.target.closest('.matiere-tabs-more-btn, .tabs-overflow-more-btn, .cls-cat-more-btn');
        if (!moreBtn) {
            return;
        }
        var bar = moreBtn.closest('.matiere-tabs-bar, .tabs-overflow-bar, .cls-cat-nav-bar');
        if (!bar) {
            return;
        }
        var preset = resolveOverflowPreset(bar);
        if (!preset) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        toggleTabsOverflowMenu(bar, preset);
    }, true);
}

window.layoutTabsOverflowNav = function () {
    OVERFLOW_PRESETS.forEach(function (preset) {
        document.querySelectorAll(preset.bar).forEach(function (bar) {
            layoutTabsOverflowBar(bar, preset);
        });
    });
};

window.layoutMatiereTabsNav = window.layoutTabsOverflowNav;
window.layoutClassesCategoryNav = window.layoutTabsOverflowNav;
