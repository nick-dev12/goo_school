/**
 * UI workspace saisie notes (compteur, tout cocher / décocher)
 */
(function () {
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

    document.addEventListener('DOMContentLoaded', function () {
        const root = panelRoot();
        if (!root) return;

        root.querySelectorAll('.eval-checkbox').forEach(function (cb) {
            cb.addEventListener('change', updateCounter);
        });

        root.querySelectorAll('.js-prof-noter-select-all').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setAll(true);
            });
        });

        root.querySelectorAll('.js-prof-noter-select-none').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setAll(false);
            });
        });

        updateCounter();

        root.querySelectorAll('.js-prof-noter-open-eval-modal').forEach(function (link) {
            link.addEventListener('click', function (event) {
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
        });
    });
})();
