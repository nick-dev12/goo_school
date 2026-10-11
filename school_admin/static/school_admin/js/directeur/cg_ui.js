(function () {
    function sheetOf(node) {
        return node.closest('.cg-sheet');
    }

    function openSheet(id, trigger) {
        var sheet = document.getElementById(id);
        if (!sheet) return;
        if (trigger && trigger.dataset.cgAction) {
            var form = sheet.querySelector('form');
            if (form) form.action = trigger.dataset.cgAction;
        }
        if (trigger && trigger.dataset.cgBind) {
            var field = sheet.querySelector('[name="' + trigger.dataset.cgBind + '"]');
            if (field) field.value = trigger.dataset.cgValue || '';
        }
        if (trigger && (trigger.dataset.cgBind || trigger.dataset.cgAction)) {
            sheet.querySelectorAll('input[type="text"], input[type="number"], textarea').forEach(function (input) {
                input.value = '';
            });
        }
        var amount = sheet.querySelector('input[name="montant"]');
        if (amount && trigger && trigger.dataset.cgMax) {
            amount.max = trigger.dataset.cgMax;
        }
        sheet.hidden = false;
        var focusable = sheet.querySelector('input:not([type="hidden"]), select, textarea');
        if (focusable) focusable.focus();
    }

    function closeSheet(sheet) {
        if (sheet) sheet.hidden = true;
    }

    document.addEventListener('click', function (event) {
        var opener = event.target.closest('[data-cg-open]');
        if (opener) {
            event.preventDefault();
            openSheet(opener.getAttribute('data-cg-open'), opener);
            return;
        }
        var closer = event.target.closest('[data-cg-close]');
        if (closer) {
            closeSheet(sheetOf(closer));
            return;
        }
        var tab = event.target.closest('[data-cg-tab]');
        if (!tab) return;
        var workspace = tab.closest('.cg-workspace');
        if (!workspace) return;
        var key = tab.getAttribute('data-cg-tab');
        workspace.querySelectorAll('[data-cg-tab]').forEach(function (button) {
            var on = button.getAttribute('data-cg-tab') === key;
            button.classList.toggle('active', on);
            button.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        workspace.querySelectorAll('[data-cg-panel]').forEach(function (panel) {
            panel.hidden = panel.getAttribute('data-cg-panel') !== key;
        });
        if (window.layoutTabsOverflowNav) window.layoutTabsOverflowNav();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('.cg-sheet:not([hidden])').forEach(function (sheet) {
            sheet.hidden = true;
        });
    });
})();
