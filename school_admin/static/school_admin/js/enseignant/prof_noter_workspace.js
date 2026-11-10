/**
 * UI workspace saisie notes (compteur, tout cocher / décocher)
 */
(function () {
    if (window.__notesWorkspaceBound) return;
    window.__notesWorkspaceBound = true;

    function panelRoot() {
        return document.querySelector('.prof-noter-panel');
    }

    function evalCheckboxes() {
        const root = panelRoot();
        if (!root) return [];
        return root.querySelectorAll('.eval-checkbox:not([disabled])');
    }

    function updateCounter() {
        const root = panelRoot();
        if (!root) return;
        const n = root.querySelectorAll('.eval-checkbox:checked').length;
        const ids = ['count-selected', 'selectedCount'];
        ids.forEach(function (id) {
            const el = document.getElementById(id);
            if (el) el.textContent = String(n);
        });
    }

    function setAll(checked) {
        evalCheckboxes().forEach(function (cb) {
            cb.checked = checked;
            cb.dispatchEvent(new Event('change', { bubbles: true }));
        });
        updateCounter();
    }

    function colorInputs() {
        const root = panelRoot();
        if (!root || typeof window.colorNote !== 'function') return;
        root.querySelectorAll('.note-input, .moyenne-input').forEach(function (input) {
            window.colorNote(input);
        });
    }

    function boot() {
        updateCounter();
        colorInputs();
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-prof-noter-select-all')) {
            setAll(true);
            return;
        }
        if (event.target.closest('.js-prof-noter-select-none')) {
            setAll(false);
            return;
        }
        var link = event.target.closest('.js-prof-noter-open-eval-modal');
        if (!link) return;
        var modalBody = document.getElementById('modalCreerEvaluationBody');
        if (!modalBody || typeof window.loadEvaluationFormModal !== 'function') {
            return;
        }
        event.preventDefault();
        var classeId =
            link.getAttribute('data-classe-id') ||
            (link.pathname.match(/\/creer\/(\d+)\//) || [])[1];
        if (!classeId) {
            window.location.assign(link.href);
            return;
        }
        var opened = window.loadEvaluationFormModal(
            classeId,
            link.getAttribute('data-matiere-id'),
            link.getAttribute('data-periode-id')
        );
        if (opened === false) {
            window.location.assign(link.href);
        }
    });

    document.addEventListener('change', function (event) {
        if (!event.target.closest('.prof-noter-panel')) return;
        if (event.target.closest('.eval-checkbox')) {
            updateCounter();
            var item = event.target.closest('.notes-noter-select__item');
            if (item) item.classList.toggle('is-checked', event.target.checked);
        }
    });

    document.addEventListener('input', function (event) {
        var input = event.target.closest('.note-input');
        if (input && typeof window.colorNote === 'function') window.colorNote(input);
    });

    document.addEventListener('prof-hub-panel-loaded', boot);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
