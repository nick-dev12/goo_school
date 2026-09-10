// Navigation fiche professeur — 3 sections : profil | enseignement | dossier

var LEGACY_ONGLET_MAP = {
    informations: 'profil',
    connexion: 'profil',
    classes: 'enseignement',
    cahier_notes: 'enseignement',
    complementaire: 'dossier'
};

function normalizeProfOnglet(raw) {
    if (!raw) {
        return 'profil';
    }
    if (LEGACY_ONGLET_MAP[raw]) {
        return LEGACY_ONGLET_MAP[raw];
    }
    if (raw === 'profil' || raw === 'enseignement' || raw === 'dossier') {
        return raw;
    }
    return 'profil';
}

document.addEventListener('DOMContentLoaded', function () {
    initProfDetailTabs();
    initDossierSubnav();
    initEnseignementSubnav();
    initModifierProfesseurModal();
    initModalMatiereSecondaire();
});

function initProfDetailTabs() {
    var root = document.querySelector('.prof-detail-page');
    var tabs = document.querySelectorAll('.prof-nav .prof-nav-btn[data-tab]');
    var panels = document.querySelectorAll('.prof-panels .prof-panel[data-tab-panel]');
    if (!tabs.length || !panels.length) {
        return;
    }

    function activateTab(tabName, pushState) {
        tabs.forEach(function (tab) {
            var isActive = tab.getAttribute('data-tab') === tabName;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        panels.forEach(function (panel) {
            panel.classList.toggle('active', panel.getAttribute('data-tab-panel') === tabName);
        });
        if (pushState !== false) {
            var url = new URL(window.location.href);
            url.searchParams.set('onglet', tabName);
            if (tabName !== 'dossier') {
                url.searchParams.delete('section');
            }
            if (tabName !== 'enseignement') {
                url.searchParams.delete('matiere');
                url.searchParams.delete('section');
            }
            window.history.replaceState({ onglet: tabName }, '', url.toString());
        }
    }

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            activateTab(tab.getAttribute('data-tab'));
        });
    });

    var params = new URLSearchParams(window.location.search);
    var initialRaw = params.get('onglet');
    var initial = normalizeProfOnglet(initialRaw);
    if (root && root.getAttribute('data-initial-onglet')) {
        initial = root.getAttribute('data-initial-onglet');
    }
    var hasPanel = document.querySelector('[data-tab-panel="' + initial + '"]');
    activateTab(hasPanel ? initial : 'profil', false);
}

function initDossierSubnav() {
    var root = document.querySelector('.prof-detail-page');
    var subBtns = document.querySelectorAll('.prof-subnav .prof-subnav-btn[data-dossier-tab]');
    var subPanels = document.querySelectorAll('.prof-dossier-pane[data-dossier-panel]');
    if (!subBtns.length || !subPanels.length) {
        return;
    }

    function activateSection(section, pushState) {
        subBtns.forEach(function (btn) {
            var isActive = btn.getAttribute('data-dossier-tab') === section;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        subPanels.forEach(function (panel) {
            panel.classList.toggle('active', panel.getAttribute('data-dossier-panel') === section);
        });
        if (pushState !== false) {
            var url = new URL(window.location.href);
            url.searchParams.set('onglet', 'dossier');
            if (section === 'completer') {
                url.searchParams.set('section', 'completer');
            } else {
                url.searchParams.delete('section');
            }
            window.history.replaceState({ onglet: 'dossier', section: section }, '', url.toString());
        }
    }

    subBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            activateSection(btn.getAttribute('data-dossier-tab'));
        });
    });

    var initial = 'consulter';
    if (root && root.getAttribute('data-dossier-section') === 'completer') {
        initial = 'completer';
    }
    var params = new URLSearchParams(window.location.search);
    if (params.get('section') === 'completer' || params.get('onglet') === 'complementaire') {
        initial = 'completer';
    }
    activateSection(initial, false);
}

function initEnseignementSubnav() {
    var root = document.querySelector('.prof-detail-page');
    var subBtns = document.querySelectorAll('.prof-enseignement-subnav .prof-subnav-btn[data-enseignement-tab]');
    var subPanels = document.querySelectorAll('.prof-enseignement-pane[data-enseignement-panel]');
    if (!subBtns.length || !subPanels.length) {
        return;
    }

    function activateSection(section, pushState) {
        subBtns.forEach(function (btn) {
            var isActive = btn.getAttribute('data-enseignement-tab') === section;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        subPanels.forEach(function (panel) {
            panel.classList.toggle('active', panel.getAttribute('data-enseignement-panel') === section);
        });
        if (pushState !== false) {
            var url = new URL(window.location.href);
            url.searchParams.set('onglet', 'enseignement');
            if (section === 'notes') {
                url.searchParams.set('section', 'notes');
            } else {
                url.searchParams.delete('section');
                url.searchParams.delete('matiere');
            }
            window.history.replaceState({ onglet: 'enseignement', section: section }, '', url.toString());
        }
    }

    subBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            activateSection(btn.getAttribute('data-enseignement-tab'));
        });
    });

    var initial = 'classes';
    if (root && root.getAttribute('data-enseignement-section') === 'notes') {
        initial = 'notes';
    }
    var params = new URLSearchParams(window.location.search);
    if (params.get('section') === 'notes' || params.get('matiere') || params.get('onglet') === 'cahier_notes') {
        initial = 'notes';
    }
    activateSection(initial, false);
}

function openModifierProfesseurModal() {
    var modal = document.getElementById('modalModifierProfesseur');
    if (!modal) {
        return;
    }
    modal.classList.add('active');
    document.body.classList.add('modal-personnel-open');
    if (typeof window.initAjouterProfesseurSuperieur === 'function' && document.getElementById('matiere-principale-list')) {
        window.initAjouterProfesseurSuperieur();
    }
}

function closeModifierProfesseurModal() {
    var modal = document.getElementById('modalModifierProfesseur');
    if (!modal) {
        return;
    }
    modal.classList.remove('active');
    document.body.classList.remove('modal-personnel-open');
}

function initModifierProfesseurModal() {
    var modal = document.getElementById('modalModifierProfesseur');
    if (!modal) {
        return;
    }
    if (modal.classList.contains('active')) {
        document.body.classList.add('modal-personnel-open');
        if (typeof window.initAjouterProfesseurSuperieur === 'function' && document.getElementById('matiere-principale-list')) {
            window.initAjouterProfesseurSuperieur();
        }
    }
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && modal.classList.contains('active')) {
            closeModifierProfesseurModal();
        }
    });
}

window.openModifierProfesseurModal = openModifierProfesseurModal;
window.closeModifierProfesseurModal = closeModifierProfesseurModal;

function initModalMatiereSecondaire() {
    if (document.getElementById('matiere-principale-list')) {
        return;
    }

    var list = document.getElementById('modal-matiere-pick-list');
    var searchInput = document.getElementById('modal-matiere-search');
    var hiddenId = document.getElementById('modal-matiere-id');
    var hint = document.getElementById('modal-matiere-selected-hint');
    var labelEl = document.getElementById('modal-matiere-selected-label');

    if (!list || !hiddenId) {
        return;
    }

    var items = list.querySelectorAll('.modal-matiere-pick-item');

    function normalizeStr(s) {
        var t = (s || '').toString().toLowerCase();
        try {
            if (typeof t.normalize === 'function') {
                t = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            }
        } catch (e) { /* ignore */ }
        return t;
    }

    function filterPickList() {
        var q = normalizeStr(searchInput ? searchInput.value : '');
        items.forEach(function (btn) {
            var raw = btn.getAttribute('data-matiere-search');
            var hay = normalizeStr(raw != null && raw !== '' ? raw : btn.textContent);
            btn.hidden = q && hay.indexOf(q) === -1;
        });
    }

    function selectMatiere(btn) {
        hiddenId.value = btn.getAttribute('data-matiere-id') || '';
        var main = btn.querySelector('.modal-matiere-pick-main');
        var txt = main ? main.textContent.trim() : btn.textContent.trim();
        items.forEach(function (b) {
            b.classList.toggle('is-selected', b === btn);
        });
        if (hint && labelEl) {
            labelEl.textContent = txt;
            hint.hidden = false;
        }
        filterPickList();
    }

    items.forEach(function (btn) {
        btn.addEventListener('click', function () {
            selectMatiere(btn);
        });
    });

    if (searchInput) {
        searchInput.addEventListener('input', filterPickList);
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function () {
        showNotification('Copié dans le presse-papiers', 'success');
    }).catch(function () {
        showNotification('Erreur lors de la copie', 'error');
    });
}

function showNotification(message, type) {
    type = type || 'info';
    var colors = { success: '#10b981', error: '#ef4444', info: '#3b82f6' };
    var notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = 'position:fixed;top:100px;right:20px;background:' + (colors[type] || colors.info) + ';color:#fff;padding:12px 24px;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,.1);z-index:9999;';
    document.body.appendChild(notification);
    setTimeout(function () {
        notification.remove();
    }, 3000);
}

window.copyToClipboard = copyToClipboard;
