/**
 * Aria — comptabilité générale (V3) : graphiques Chart.js et saisie d'écriture.
 * Palette de référence validée : série 1 bleu, série 2 orange, seuils en trait fin. Une seule échelle par graphique.
 */
(function () {
  'use strict';

  var C = {
    s1: '#2a78d6', s1Tint: 'rgba(42, 120, 214, 0.10)', s2: '#eb6834', s3: '#7c4ddb', s4: '#1f93b8',
    critical: '#d03b3b', ink: '#101828', ink2: '#475467', axis: '#8a919e', grid: '#eef0f3', surface: '#ffffff',
  };
  var devise = document.body.getAttribute('data-devise') || '';

  function money(v) {
    return Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + (devise ? ' ' + devise : '');
  }

  function compact(v) {
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' Md';
    if (a >= 1e6) return (v / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' M';
    if (a >= 1e3) return (v / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + ' k';
    return Number(v).toLocaleString('fr-FR');
  }

  function data(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function defaults() {
    var d = Chart.defaults;
    d.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
    d.font.size = 12;
    d.color = C.axis;
    d.maintainAspectRatio = false;
    d.animation.duration = 450;
    d.plugins.legend.display = false;
    var t = d.plugins.tooltip;
    t.backgroundColor = C.ink;
    t.titleColor = '#fff';
    t.bodyColor = '#e4e7ec';
    t.titleFont = { weight: '600', size: 12 };
    t.padding = 10;
    t.cornerRadius = 8;
    t.boxPadding = 4;
  }

  function yAxis(extra) {
    return Object.assign({
      grid: { color: C.grid, drawTicks: false }, border: { display: false },
      ticks: { padding: 8, color: C.axis, callback: function (v) { return compact(v); } },
    }, extra || {});
  }

  function xAxis(extra) {
    return Object.assign({ grid: { display: false }, border: { color: '#d5d9e0' }, ticks: { padding: 6, color: C.ink2 } }, extra || {});
  }

  function zeroLine() {
    return {
      id: 'cgZero',
      afterDatasetsDraw: function (chart) {
        var y = chart.scales.y;
        if (!y || y.min >= 0) return;
        var px = y.getPixelForValue(0);
        var ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = C.ink2;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(chart.chartArea.left, px);
        ctx.lineTo(chart.chartArea.right, px);
        ctx.stroke();
        ctx.restore();
      },
    };
  }

  /* Produits et charges du mois (barres groupées, même échelle). */
  function mensuel(canvasId, m) {
    var el = document.getElementById(canvasId);
    if (!el || !m || !m.labels.length) return;
    new Chart(el, {
      type: 'bar',
      data: {
        labels: m.labels,
        datasets: [
          { label: 'Produits', data: m.produits, backgroundColor: C.s1, borderRadius: 4, maxBarThickness: 18, categoryPercentage: 0.7, barPercentage: 0.9 },
          { label: 'Charges', data: m.charges, backgroundColor: C.s2, borderRadius: 4, maxBarThickness: 18, categoryPercentage: 0.7, barPercentage: 0.9 },
        ],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: { x: xAxis(), y: yAxis({ beginAtZero: true }) },
        plugins: { tooltip: { callbacks: { label: function (i) { return ' ' + i.dataset.label + ' : ' + money(i.parsed.y); } } } },
      },
    });
  }

  /* Une courbe (trésorerie de fin de mois ou résultat cumulé). */
  function courbe(canvasId, labels, values, label, color) {
    var el = document.getElementById(canvasId);
    if (!el || !labels || !labels.length) return;
    new Chart(el, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: label, data: values, borderColor: color || C.s1, backgroundColor: C.s1Tint, fill: 'origin', borderWidth: 2,
          tension: 0.3, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: color || C.s1, pointBorderColor: C.surface, pointBorderWidth: 2,
        }],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: { x: xAxis(), y: yAxis() },
        plugins: { tooltip: { callbacks: { label: function (i) { return ' ' + label + ' : ' + money(i.parsed.y); } } } },
      },
      plugins: [zeroLine()],
    });
  }

  /* Bilan : actif et passif empilés côte à côte. */
  function bilan(canvasId, b) {
    var el = document.getElementById(canvasId);
    if (!el || !b) return;
    var parts = [
      { label: 'Actif immobilisé net', a: b.actif[0], p: 0, c: C.s1 },
      { label: 'Actif circulant', a: b.actif[1], p: 0, c: C.s4 },
      { label: 'Trésorerie actif', a: b.actif[2], p: 0, c: '#0ca30c' },
      { label: 'Capitaux propres', a: 0, p: b.passif[0], c: C.s3 },
      { label: 'Dettes financières', a: 0, p: b.passif[1], c: C.s2 },
      { label: 'Passif circulant', a: 0, p: b.passif[2], c: '#fab219' },
      { label: 'Trésorerie passif', a: 0, p: b.passif[3], c: C.critical },
    ].filter(function (x) { return x.a || x.p; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: ['Actif', 'Passif'],
        datasets: parts.map(function (x) {
          return { label: x.label, data: [x.a, x.p], backgroundColor: x.c, borderColor: C.surface, borderWidth: 2, borderRadius: 4, maxBarThickness: 64 };
        }),
      },
      options: {
        indexAxis: 'y',
        scales: { x: yAxis({ stacked: true, beginAtZero: true }), y: xAxis({ stacked: true }) },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: false, color: C.ink2, padding: 12 } },
          tooltip: { callbacks: { label: function (i) { return ' ' + i.dataset.label + ' : ' + money(i.parsed.x); } } },
        },
      },
    });
  }

  /* Balance : mouvements débit / crédit par classe. */
  function classes(canvasId, rows) {
    var el = document.getElementById(canvasId);
    if (!el || !rows || !rows.length) return;
    new Chart(el, {
      type: 'bar',
      data: {
        labels: rows.map(function (r) { return r.label; }),
        datasets: [
          { label: 'Débit', data: rows.map(function (r) { return r.debit; }), backgroundColor: C.s1, borderRadius: 4, maxBarThickness: 18 },
          { label: 'Crédit', data: rows.map(function (r) { return r.credit; }), backgroundColor: C.s2, borderRadius: 4, maxBarThickness: 18 },
        ],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: { x: xAxis(), y: yAxis({ beginAtZero: true }) },
        plugins: { tooltip: { callbacks: { label: function (i) { return ' ' + i.dataset.label + ' : ' + money(i.parsed.y); } } } },
      },
    });
  }

  /* Répartition en anneau (valeur nette des biens par catégorie). */
  function anneau(canvasId, rows) {
    var el = document.getElementById(canvasId);
    if (!el || !rows || !rows.length) return;
    var palette = [C.s1, C.s2, C.s3, C.s4, '#0ca30c', '#fab219'];
    new Chart(el, {
      type: 'doughnut',
      data: {
        labels: rows.map(function (r) { return r.label; }),
        datasets: [{ data: rows.map(function (r) { return r.montant; }), backgroundColor: palette, borderColor: C.surface, borderWidth: 2 }],
      },
      options: {
        cutout: '64%',
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, color: C.ink2, padding: 12 } },
          tooltip: { callbacks: { label: function (i) { return ' ' + i.label + ' : ' + money(i.parsed); } } },
        },
      },
    });
  }

  /* ---------- Saisie d'écriture : lignes dynamiques et contrôle d'équilibre ---------- */
  function initSaisie() {
    var form = document.getElementById('cg3-saisie');
    if (!form) return;
    var tbody = form.querySelector('tbody');
    var tpl = document.getElementById('cg3-ligne-tpl');
    var bar = form.querySelector('.cg3-balance-bar');
    var submit = form.querySelector('[type="submit"]');

    function num(input) {
      var v = parseFloat(String(input.value || '').replace(/\s/g, '').replace(',', '.'));
      return isNaN(v) ? 0 : v;
    }

    function refresh() {
      var d = 0, c = 0, lignes = 0;
      tbody.querySelectorAll('tr').forEach(function (tr) {
        var dv = num(tr.querySelector('[name="debit"]'));
        var cv = num(tr.querySelector('[name="credit"]'));
        d += dv; c += cv;
        if (dv || cv) lignes += 1;
      });
      var ecart = Math.round((d - c) * 100) / 100;
      bar.querySelector('[data-total-debit]').textContent = money(d);
      bar.querySelector('[data-total-credit]').textContent = money(c);
      bar.querySelector('[data-ecart]').textContent = (d === 0 && c === 0) ? 'Saisissez les montants'
        : (ecart === 0 ? 'Équilibrée' : 'Écart : ' + money(Math.abs(ecart)));
      var ok = ecart === 0 && d > 0 && lignes >= 2;
      bar.classList.toggle('is-ok', ok);
      bar.classList.toggle('is-ko', !ok && (d > 0 || c > 0));
      submit.disabled = !ok;
    }

    function addLine() {
      var row = tpl.content.firstElementChild.cloneNode(true);
      tbody.appendChild(row);
      return row;
    }

    form.addEventListener('input', function (e) {
      var t = e.target;
      if (t.name === 'debit' && t.value) t.closest('tr').querySelector('[name="credit"]').value = '';
      if (t.name === 'credit' && t.value) t.closest('tr').querySelector('[name="debit"]').value = '';
      refresh();
    });
    form.addEventListener('click', function (e) {
      if (e.target.closest('[data-add-line]')) { e.preventDefault(); addLine(); refresh(); }
      var del = e.target.closest('[data-del-line]');
      if (del) {
        e.preventDefault();
        if (tbody.querySelectorAll('tr').length > 2) del.closest('tr').remove();
        refresh();
      }
      var eq = e.target.closest('[data-equilibrer]');
      if (eq) {
        e.preventDefault();
        var d = 0, c = 0;
        tbody.querySelectorAll('tr').forEach(function (tr) { d += num(tr.querySelector('[name="debit"]')); c += num(tr.querySelector('[name="credit"]')); });
        var ecart = Math.round((d - c) * 100) / 100;
        if (!ecart) return;
        var row = Array.prototype.slice.call(tbody.querySelectorAll('tr')).find(function (tr) {
          return !num(tr.querySelector('[name="debit"]')) && !num(tr.querySelector('[name="credit"]'));
        }) || addLine();
        row.querySelector(ecart > 0 ? '[name="credit"]' : '[name="debit"]').value = Math.abs(ecart);
        refresh();
      }
    });
    refresh();
  }

  function initModals() {
    document.addEventListener('click', function (e) {
      var open = e.target.closest('[data-cg3-open]');
      if (open) {
        e.preventDefault();
        var m = document.getElementById(open.getAttribute('data-cg3-open'));
        if (m) {
          m.hidden = false;
          document.documentElement.style.overflow = 'hidden';
          var f = m.querySelector('input:not([type="hidden"]), select');
          if (f) f.focus();
          if (open.dataset.ecriture) {
            var input = m.querySelector('[name="ecriture_id"]');
            if (input) input.value = open.dataset.ecriture;
            var lbl = m.querySelector('[data-piece]');
            if (lbl) lbl.textContent = open.dataset.piece || '';
          }
        }
      }
      var close = e.target.closest('[data-cg3-close]');
      if (close || (e.target.classList && e.target.classList.contains('cg3-modal'))) {
        var modal = (close || e.target).closest('.cg3-modal');
        if (modal) { modal.hidden = true; document.documentElement.style.overflow = ''; }
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      document.querySelectorAll('.cg3-modal:not([hidden])').forEach(function (m) { m.hidden = true; });
      document.documentElement.style.overflow = '';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initModals();
    initSaisie();
    if (typeof Chart === 'undefined') return;
    defaults();
    var d = data('cg3-data');
    if (!d) return;
    if (d.mensuel) {
      mensuel('cg3-chart-mensuel', d.mensuel);
      courbe('cg3-chart-treso', d.mensuel.labels, d.mensuel.tresorerie, 'Trésorerie fin de mois', C.s1);
      courbe('cg3-chart-resultat', d.mensuel.labels, d.mensuel.resultat_cumule, 'Résultat cumulé', C.s3);
    }
    if (d.bilan) bilan('cg3-chart-bilan', d.bilan);
    if (d.classes) classes('cg3-chart-classes', d.classes);
    if (d.categories) anneau('cg3-chart-categories', d.categories);
  });
})();
