/**
 * Emploi du temps examens — UX v2
 */

function getMatieresParSession() {
    var el = document.getElementById('exam-matieres-session-data');
    if (!el || !el.textContent) return {};
    try {
        return JSON.parse(el.textContent);
    } catch (e) {
        return {};
    }
}

var matieresParSession = getMatieresParSession();

window.switchSessionTab = function (tabId, btn) {
    document.querySelectorAll('.edtex-session-panel').forEach(function (panel) {
        panel.classList.remove('active');
    });
    document.querySelectorAll('.edtex-session-tab').forEach(function (button) {
        button.classList.remove('active');
        button.setAttribute('aria-selected', 'false');
    });

    var panel = document.getElementById(tabId);
    if (panel) panel.classList.add('active');

    var targetBtn = btn || document.querySelector('.edtex-session-tab[data-tab="' + tabId + '"]');
    if (targetBtn) {
        targetBtn.classList.add('active');
        targetBtn.setAttribute('aria-selected', 'true');
    }

    if (typeof window.layoutTabsOverflowNav === 'function') {
        window.layoutTabsOverflowNav();
    }
};

function openModal() {
    document.getElementById('creneauModal').classList.add('show');
}

function openModalWithSession(sessionId) {
    openModal();
    var select = document.getElementById('session_examen_id');
    if (select) {
        select.value = String(sessionId);
        updateMatieresForSession();
    }
}

function closeModal() {
    var modal = document.getElementById('creneauModal');
    modal.classList.remove('show');
    var form = modal.querySelector('form');
    if (form) form.reset();
    var matiereSelect = document.getElementById('matiere_id');
    if (matiereSelect) {
        matiereSelect.innerHTML = '<option value="">Sélectionnez d\'abord une session</option>';
        matiereSelect.disabled = true;
    }
}

function updateMatieresForSession() {
    var sessionSelect = document.getElementById('session_examen_id');
    var matiereSelect = document.getElementById('matiere_id');
    if (!sessionSelect || !matiereSelect) return;

    var sessionId = sessionSelect.value;
    if (!sessionId) {
        matiereSelect.innerHTML = '<option value="">Sélectionnez d\'abord une session</option>';
        matiereSelect.disabled = true;
        return;
    }

    var matieres = matieresParSession[sessionId];
    if (!matieres || matieres.length === 0) {
        matiereSelect.innerHTML = '<option value="">Aucune matière disponible</option>';
        matiereSelect.disabled = true;
        return;
    }

    matiereSelect.innerHTML = '<option value="">Sélectionnez une matière</option>';
    matieres.forEach(function (matiere) {
        var option = document.createElement('option');
        option.value = matiere.id;
        option.textContent = matiere.nom;
        matiereSelect.appendChild(option);
    });
    matiereSelect.disabled = false;
}

function printTimetable() {
    window.print();
}

function animateCreneaux() {
    var blocks = document.querySelectorAll('.edtex-session-panel.active .edtex-exam-block');
    blocks.forEach(function (block, index) {
        block.style.opacity = '0';
        block.style.transform = 'scale(0.96)';
        setTimeout(function () {
            block.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            block.style.opacity = '1';
            block.style.transform = 'scale(1)';
        }, index * 40);
    });
}

document.addEventListener('DOMContentLoaded', function () {
    var sessionSelect = document.getElementById('session_examen_id');
    if (sessionSelect) {
        sessionSelect.addEventListener('change', updateMatieresForSession);
    }

    window.addEventListener('click', function (event) {
        var modal = document.getElementById('creneauModal');
        if (event.target === modal) closeModal();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeModal();
    });

    setTimeout(animateCreneaux, 300);
});
