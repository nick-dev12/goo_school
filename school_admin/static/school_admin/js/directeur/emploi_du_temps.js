// Liste emplois du temps — navigation, overflow onglets, filtres (UX v2.1)

var EDT_CAT_GAP = 6;
var EDT_MORE_BTN_WIDTH = 130;

document.addEventListener('DOMContentLoaded', function () {
    initEdtCategoryTabs();
    initEdtCategoryNavOverflow();
    initEdtFilters();
    initEdtSearch();
});

function slugify(text) {
    return text
        .toString()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');
}

function getAllEdtCatButtons() {
    var track = document.getElementById('edtCatNavTrack');
    var menu = document.getElementById('edtCatOverflowMenu');
    if (!track || !menu) {
        return [];
    }
    var buttons = Array.prototype.slice.call(track.querySelectorAll('.edt-cat-btn'));
    buttons = buttons.concat(Array.prototype.slice.call(menu.querySelectorAll('.edt-cat-btn')));
    buttons.sort(function (a, b) {
        return parseInt(a.getAttribute('data-order') || '0', 10) - parseInt(b.getAttribute('data-order') || '0', 10);
    });
    return buttons;
}

function closeEdtOverflowMenu() {
    var menu = document.getElementById('edtCatOverflowMenu');
    var moreBtn = document.getElementById('edtCatMoreBtn');
    if (!menu || !moreBtn) {
        return;
    }
    menu.hidden = true;
    moreBtn.setAttribute('aria-expanded', 'false');
}

function updateEdtMoreButtonLabel(overflowCount) {
    var bar = document.getElementById('edtCatNavBar');
    var labelEl = document.getElementById('edtCatMoreLabel');
    var moreBtn = document.getElementById('edtCatMoreBtn');
    if (!bar || !labelEl || !moreBtn) {
        return;
    }

    var singular = bar.getAttribute('data-overflow-item-label') || 'élément';
    var plural = bar.getAttribute('data-overflow-items-label') || 'éléments';
    var count = overflowCount || 0;
    var word = count > 1 ? plural : singular;

    labelEl.textContent = 'Autres ' + plural;
    moreBtn.setAttribute(
        'aria-label',
        'Afficher ' + count + ' autre' + (count > 1 ? 's' : '') + ' ' + word
    );
    moreBtn.setAttribute(
        'title',
        'Afficher ' + count + ' autre' + (count > 1 ? 's' : '') + ' ' + word
    );
}

function activateEdtCategory(category) {
    var buttons = getAllEdtCatButtons();
    var panels = document.querySelectorAll('.edt-panel[data-edt-panel]');

    buttons.forEach(function (btn) {
        var isActive = btn.getAttribute('data-category') === category;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    panels.forEach(function (panel) {
        panel.classList.toggle('active', panel.id === 'panel-' + slugify(category));
    });

    closeEdtOverflowMenu();
    layoutEdtCategoryNav();
}

function initEdtCategoryTabs() {
    var track = document.getElementById('edtCatNavTrack');
    var menu = document.getElementById('edtCatOverflowMenu');
    if (!track) {
        return;
    }

    function onTabClick(event) {
        var btn = event.target.closest('.edt-cat-btn[data-category]');
        if (!btn) {
            return;
        }
        activateEdtCategory(btn.getAttribute('data-category'));
    }

    track.addEventListener('click', onTabClick);
    if (menu) {
        menu.addEventListener('click', onTabClick);
    }
}

function layoutEdtCategoryNav() {
    var bar = document.getElementById('edtCatNavBar');
    var track = document.getElementById('edtCatNavTrack');
    var menu = document.getElementById('edtCatOverflowMenu');
    var moreWrap = document.getElementById('edtCatMoreWrap');
    var moreBtn = document.getElementById('edtCatMoreBtn');
    if (!bar || !track || !menu || !moreWrap) {
        return;
    }

    var allButtons = getAllEdtCatButtons();
    if (!allButtons.length) {
        return;
    }

    allButtons.forEach(function (btn) {
        track.appendChild(btn);
    });
    menu.innerHTML = '';
    moreWrap.hidden = true;
    closeEdtOverflowMenu();

    var totalWidth = 0;
    allButtons.forEach(function (btn) {
        totalWidth += btn.offsetWidth + EDT_CAT_GAP;
    });

    if (totalWidth <= bar.clientWidth) {
        return;
    }

    moreWrap.hidden = false;
    var moreBtnWidth = moreBtn ? moreBtn.offsetWidth + EDT_CAT_GAP : EDT_MORE_BTN_WIDTH;
    var availableWidth = Math.max(bar.clientWidth - moreBtnWidth, 100);
    var usedWidth = 0;
    var splitAt = allButtons.length;

    for (var i = 0; i < allButtons.length; i += 1) {
        var btnWidth = allButtons[i].offsetWidth + EDT_CAT_GAP;
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
        updateEdtMoreButtonLabel(overflowButtons.length);
    } else {
        moreWrap.hidden = true;
    }
}

function initEdtCategoryNavOverflow() {
    var bar = document.getElementById('edtCatNavBar');
    var moreBtn = document.getElementById('edtCatMoreBtn');
    var menu = document.getElementById('edtCatOverflowMenu');
    if (!bar || !moreBtn || !menu) {
        return;
    }

    layoutEdtCategoryNav();

    if (typeof ResizeObserver !== 'undefined') {
        var observer = new ResizeObserver(function () {
            layoutEdtCategoryNav();
        });
        observer.observe(bar);
    } else {
        window.addEventListener('resize', layoutEdtCategoryNav);
    }

    moreBtn.addEventListener('click', function (event) {
        event.stopPropagation();
        var isOpen = !menu.hidden;
        if (isOpen) {
            closeEdtOverflowMenu();
        } else {
            menu.hidden = false;
            moreBtn.setAttribute('aria-expanded', 'true');
        }
    });

    document.addEventListener('click', function (event) {
        if (!bar.contains(event.target)) {
            closeEdtOverflowMenu();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeEdtOverflowMenu();
        }
    });
}

function initEdtFilters() {
    var filterBtns = document.querySelectorAll('.edt-filter-btn[data-edt-filter]');
    if (!filterBtns.length) {
        return;
    }

    filterBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            filterBtns.forEach(function (b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            applyEdtFilters(btn.getAttribute('data-edt-filter'), getEdtSearchQuery());
        });
    });
}

function initEdtSearch() {
    var input = document.getElementById('edtSearchInput');
    if (!input) {
        return;
    }
    input.addEventListener('input', function () {
        var activeFilter = document.querySelector('.edt-filter-btn.active');
        var filter = activeFilter ? activeFilter.getAttribute('data-edt-filter') : 'all';
        applyEdtFilters(filter, input.value);
    });
}

function getEdtSearchQuery() {
    var input = document.getElementById('edtSearchInput');
    return input ? input.value : '';
}

function applyEdtFilters(statusFilter, searchQuery) {
    var query = (searchQuery || '').toLowerCase().trim();

    document.querySelectorAll('.edt-panel[data-edt-panel]').forEach(function (panel) {
        var visibleInPanel = 0;

        panel.querySelectorAll('.edt-classe-card').forEach(function (card) {
            var hasEdt = card.getAttribute('data-has-edt') === '1';
            var title = card.querySelector('.edt-classe-card-title');
            var text = title ? title.textContent.toLowerCase() : '';

            var statusOk = true;
            if (statusFilter === 'with-edt') {
                statusOk = hasEdt;
            } else if (statusFilter === 'without-edt') {
                statusOk = !hasEdt;
            }

            var searchOk = !query || text.indexOf(query) !== -1;
            var show = statusOk && searchOk;
            card.hidden = !show;
            if (show) {
                visibleInPanel += 1;
            }
        });

        panel.querySelectorAll('.edt-section').forEach(function (section) {
            var cards = section.querySelectorAll('.edt-classe-card:not([hidden])');
            section.classList.toggle('is-empty', cards.length === 0);
        });

        var noResults = panel.querySelector('.edt-no-results');
        if (noResults) {
            noResults.hidden = visibleInPanel > 0;
        }
    });
}

window.switchTab = function (category) {
    activateEdtCategory(category);
};

window.searchClasses = function (query) {
    var input = document.getElementById('edtSearchInput');
    if (input) {
        input.value = query;
    }
    var activeFilter = document.querySelector('.edt-filter-btn.active');
    var filter = activeFilter ? activeFilter.getAttribute('data-edt-filter') : 'all';
    applyEdtFilters(filter, query);
};

window.filterByStatus = function (filter) {
    var btn = document.querySelector('.edt-filter-btn[data-edt-filter="' + filter + '"]');
    if (btn) {
        btn.click();
    }
};
