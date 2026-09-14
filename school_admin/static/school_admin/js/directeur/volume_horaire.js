(function () {
  function syncPeriodFields(form) {
    var select = form.querySelector('#vh-periode');
    if (!select) {
      return;
    }
    var kind = select.value;
    form.querySelectorAll('[data-period-field]').forEach(function (el) {
      var on = el.getAttribute('data-period-field') === kind;
      el.hidden = !on;
      el.querySelectorAll('input, select').forEach(function (input) {
        input.disabled = !on;
      });
    });
  }

  function bindSearch() {
    var input = document.getElementById('vh-search');
    if (!input) {
      return;
    }
    input.addEventListener('input', function () {
      var q = (input.value || '').trim().toLowerCase();
      document.querySelectorAll('.vh-row').forEach(function (row) {
        var nom = row.getAttribute('data-nom') || '';
        row.hidden = Boolean(q) && nom.indexOf(q) === -1;
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('vh-filter-form');
    if (form) {
      syncPeriodFields(form);
      var select = form.querySelector('#vh-periode');
      if (select) {
        select.addEventListener('change', function () {
          syncPeriodFields(form);
        });
      }
    }
    bindSearch();
  });
})();
