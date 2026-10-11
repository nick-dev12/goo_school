/**
 * Aria — tableau de bord élève (V3) : onglets des jours et graphiques Chart.js.
 * Palette de référence validée (série bleue, statut critique rouge), comme la direction.
 */
(function () {
  'use strict';

  var C = {
    s1: '#2a78d6',
    s1Tint: 'rgba(42, 120, 214, 0.10)',
    critical: '#d03b3b',
    ink: '#101828',
    ink2: '#475467',
    axis: '#8a919e',
    grid: '#eef0f3',
    surface: '#ffffff',
  };

  /* ---------- Onglets des jours de l'emploi du temps ---------- */
  function initDays() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll('.ex-day'));
    if (!tabs.length) return;
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.classList.toggle('is-active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab, i) {
      tab.tabIndex = tab.classList.contains('is-active') ? 0 : -1;
      tab.addEventListener('click', function () { select(tab); });
      tab.addEventListener('keydown', function (e) {
        var next = null;
        if (e.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
        if (e.key === 'ArrowLeft') next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (next) { e.preventDefault(); select(next, true); }
      });
    });
  }

  /* ---------- Graphiques ---------- */
  function readData() {
    var el = document.getElementById('ex-data');
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  var threshold = {
    id: 'exThreshold',
    afterDatasetsDraw: function (chart, _a, opts) {
      if (!opts || opts.value == null) return;
      var scale = chart.scales.y;
      if (!scale) return;
      var y = scale.getPixelForValue(opts.value);
      var area = chart.chartArea;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = C.critical;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(area.left, y);
      ctx.lineTo(area.right, y);
      ctx.stroke();
      if (opts.label) {
        ctx.font = '600 11px Inter, system-ui, sans-serif';
        ctx.fillStyle = C.critical;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(opts.label, area.right, y - 4);
      }
      ctx.restore();
    },
  };

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
    t.displayColors = false;
    Chart.register(threshold);
  }

  function gridAxis(extra) {
    return Object.assign({ grid: { color: C.grid, drawTicks: false }, border: { display: false }, ticks: { padding: 8, color: C.axis } }, extra || {});
  }

  function catAxis(extra) {
    return Object.assign({ grid: { display: false }, border: { color: '#d5d9e0' }, ticks: { padding: 6, color: C.ink2 } }, extra || {});
  }

  function fr(v) {
    return Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
  }

  function evolution(d) {
    var el = document.getElementById('ex-chart-evolution');
    var ev = d.evolution;
    if (!el || !ev || ev.values.length < 2) return;
    var colors = ev.values.map(function (v) { return v < 10 ? C.critical : C.s1; });
    new Chart(el, {
      type: 'line',
      data: {
        labels: ev.labels,
        datasets: [{
          data: ev.values, borderColor: C.s1, backgroundColor: C.s1Tint, borderWidth: 2, fill: 'origin', tension: 0.3,
          pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: colors, pointBorderColor: C.surface, pointBorderWidth: 2,
        }],
      },
      options: {
        interaction: { mode: 'nearest', intersect: false, axis: 'x' },
        scales: {
          x: catAxis({ ticks: { color: C.axis, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, padding: 6 } }),
          y: gridAxis({ min: 0, max: 20, ticks: { stepSize: 5, padding: 8, color: C.axis } }),
        },
        plugins: {
          exThreshold: { value: 10, label: '10/20' },
          tooltip: {
            callbacks: {
              title: function (i) { return ev.details[i[0].dataIndex] || ''; },
              label: function (i) { return ev.labels[i.dataIndex] + ' · ' + fr(i.parsed.y) + ' / 20'; },
            },
          },
        },
      },
    });
  }

  function presence(d) {
    var el = document.getElementById('ex-chart-presence');
    var p = d.presence_mois;
    if (!el || !p || !p.values.length) return;
    var colors = p.values.map(function (v) { return v < 85 ? C.critical : C.s1; });
    var min = Math.min.apply(null, p.values.concat([85]));
    new Chart(el, {
      type: 'bar',
      data: {
        labels: p.labels,
        datasets: [{ data: p.values, backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', maxBarThickness: 26 }],
      },
      options: {
        scales: {
          x: catAxis(),
          y: gridAxis({ min: Math.max(0, Math.floor((min - 10) / 10) * 10), max: 100, ticks: { padding: 6, color: C.axis, callback: function (v) { return v + ' %'; } } }),
        },
        plugins: {
          exThreshold: { value: 85, label: '85 %' },
          tooltip: { callbacks: { label: function (i) { return 'Présence : ' + fr(i.parsed.y) + ' %'; } } },
        },
      },
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initDays();
    var d = readData();
    if (!d || typeof Chart === 'undefined') return;
    defaults();
    evolution(d);
    presence(d);
  });
})();
