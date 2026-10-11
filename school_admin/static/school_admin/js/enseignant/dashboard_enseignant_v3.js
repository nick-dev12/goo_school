/**
 * Aria — tableau de bord enseignant (V3) : graphiques Chart.js.
 * Palette de référence validée (série 1 bleu, statut critique rouge), comme la direction.
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

  function readData() {
    var el = document.getElementById('axp-data');
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  var threshold = {
    id: 'axpThreshold',
    afterDatasetsDraw: function (chart, _a, opts) {
      if (!opts || opts.value == null) return;
      var axis = opts.axis || 'y';
      var scale = chart.scales[axis];
      if (!scale) return;
      var pos = scale.getPixelForValue(opts.value);
      var area = chart.chartArea;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = C.critical;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (axis === 'y') {
        ctx.moveTo(area.left, pos);
        ctx.lineTo(area.right, pos);
      } else {
        ctx.moveTo(pos, area.top);
        ctx.lineTo(pos, area.bottom);
      }
      ctx.stroke();
      if (opts.label) {
        ctx.font = '600 11px Inter, system-ui, sans-serif';
        ctx.fillStyle = C.critical;
        if (axis === 'y') {
          ctx.textAlign = 'right';
          ctx.textBaseline = 'bottom';
          ctx.fillText(opts.label, area.right, pos - 4);
        } else {
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(opts.label, pos + 4, area.top);
        }
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

  function fr(v, digits) {
    return Number(v).toLocaleString('fr-FR', { maximumFractionDigits: digits == null ? 1 : digits });
  }

  function trend(d) {
    var el = document.getElementById('axp-chart-trend');
    if (!el || !d.trend || !d.trend.values.length) return;
    var min = Math.min.apply(null, d.trend.values.concat([85]));
    new Chart(el, {
      type: 'line',
      data: {
        labels: d.trend.labels,
        datasets: [{
          data: d.trend.values, borderColor: C.s1, backgroundColor: C.s1Tint, borderWidth: 2, fill: 'origin',
          tension: 0.32, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderColor: C.surface, pointHoverBorderWidth: 2,
          pointHoverBackgroundColor: C.s1,
        }],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: catAxis({ ticks: { color: C.axis, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, padding: 6 } }),
          y: gridAxis({ min: Math.max(0, Math.floor((min - 5) / 5) * 5), max: 100, ticks: { padding: 8, color: C.axis, callback: function (v) { return v + ' %'; } } }),
        },
        plugins: {
          axpThreshold: { value: 85, label: 'Seuil 85 %' },
          tooltip: { callbacks: { label: function (i) { return 'Présence : ' + fr(i.parsed.y) + ' %'; } } },
        },
      },
    });
  }

  function presenceClasses(d) {
    var el = document.getElementById('axp-chart-presence-classes');
    var rows = d.classes_presence || [];
    if (!el || !rows.length) return;
    var colors = rows.map(function (r) { return r.watch ? C.critical : C.s1; });
    var min = Math.min.apply(null, rows.map(function (r) { return r.taux; }).concat([85]));
    new Chart(el, {
      type: 'bar',
      data: {
        labels: rows.map(function (r) { return (r.watch ? '▲ ' : '') + r.classe; }),
        datasets: [{ data: rows.map(function (r) { return r.taux; }), backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: 'start', maxBarThickness: 18, categoryPercentage: 0.8, barPercentage: 0.9 }],
      },
      options: {
        indexAxis: 'y',
        scales: {
          x: gridAxis({ min: Math.max(0, Math.floor((min - 5) / 5) * 5), max: 100, ticks: { padding: 6, color: C.axis, callback: function (v) { return v + ' %'; } } }),
          y: catAxis({ ticks: { color: C.ink2, padding: 6, autoSkip: false, font: { weight: '500' } } }),
        },
        plugins: {
          axpThreshold: { value: 85, axis: 'x', label: '85 %' },
          tooltip: { callbacks: { title: function (i) { return rows[i[0].dataIndex].classe; }, label: function (i) { return 'Présence : ' + fr(i.parsed.x) + ' %'; } } },
        },
      },
    });
  }

  function histogram(d) {
    var el = document.getElementById('axp-chart-histogram');
    if (!el || !d.histogram) return;
    var colors = d.histogram.labels.map(function (_l, i) { return i < 2 ? C.critical : C.s1; });
    var total = d.histogram.values.reduce(function (a, b) { return a + b; }, 0) || 1;
    new Chart(el, {
      type: 'bar',
      data: {
        labels: d.histogram.labels,
        datasets: [{ data: d.histogram.values, backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', maxBarThickness: 46, categoryPercentage: 0.82, barPercentage: 0.92 }],
      },
      options: {
        scales: {
          x: catAxis({ title: { display: true, text: 'Note ramenée sur 20', color: C.axis, padding: { top: 8 } } }),
          y: gridAxis({ beginAtZero: true, ticks: { padding: 8, color: C.axis, precision: 0 } }),
        },
        plugins: {
          tooltip: { callbacks: {
            title: function (i) { return 'Notes ' + i[0].label; },
            label: function (i) { return fr(i.parsed.y, 0) + ' note(s) · ' + Math.round(i.parsed.y / total * 100) + ' %'; },
          } },
        },
      },
    });
  }

  function classesMoyenne(d) {
    var el = document.getElementById('axp-chart-classes');
    var m = d.classes_moyenne;
    if (!el || !m || !m.values.length) return;
    var colors = m.values.map(function (v) { return v < 10 ? C.critical : C.s1; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: m.labels,
        datasets: [{ data: m.values, backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', maxBarThickness: 44, categoryPercentage: 0.8, barPercentage: 0.9 }],
      },
      options: {
        scales: {
          x: catAxis({ ticks: { color: C.ink2, padding: 6, autoSkip: false, font: { weight: '500' } } }),
          y: gridAxis({ min: 0, max: 20, ticks: { padding: 8, color: C.axis, stepSize: 5 } }),
        },
        plugins: {
          axpThreshold: { value: 10, label: '10/20' },
          tooltip: { callbacks: { label: function (i) { return 'Moyenne : ' + fr(i.parsed.y, 2) + ' /20'; } } },
        },
      },
    });
  }

  function matieres(d) {
    var el = document.getElementById('axp-chart-matieres');
    var m = d.matieres_moyenne;
    if (!el || !m || !m.values.length) return;
    var colors = m.values.map(function (v) { return v < 10 ? C.critical : C.s1; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: m.labels,
        datasets: [{ data: m.values, backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', maxBarThickness: 48, categoryPercentage: 0.8, barPercentage: 0.9 }],
      },
      options: {
        scales: {
          x: catAxis({ ticks: { color: C.ink2, padding: 6, autoSkip: false, font: { weight: '500' } } }),
          y: gridAxis({ min: 0, max: 20, ticks: { padding: 8, color: C.axis, stepSize: 5 } }),
        },
        plugins: {
          axpThreshold: { value: 10, label: '10/20' },
          tooltip: { callbacks: { label: function (i) { return 'Moyenne : ' + fr(i.parsed.y, 2) + ' /20'; } } },
        },
      },
    });
  }

  function weekdays(d) {
    var el = document.getElementById('axp-chart-weekdays');
    var w = d.weekdays;
    if (!el || !w || !w.values.length) return;
    var peak = w.values.indexOf(Math.max.apply(null, w.values));
    var colors = w.values.map(function (_v, i) { return i === peak ? C.s1 : '#b9c2cf'; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: w.labels,
        datasets: [{ data: w.values, backgroundColor: colors, hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'start', maxBarThickness: 40, categoryPercentage: 0.8, barPercentage: 0.9 }],
      },
      options: {
        scales: {
          x: catAxis(),
          y: gridAxis({ beginAtZero: true, ticks: { padding: 8, color: C.axis, callback: function (v) { return v + ' %'; } } }),
        },
        plugins: { tooltip: { callbacks: { label: function (i) { return 'Absences : ' + fr(i.parsed.y) + ' %'; } } } },
      },
    });
  }

  function evolution(d) {
    var el = document.getElementById('axp-chart-evolution');
    var e = d.evolution;
    if (!el || !e || !e.values.length) return;
    new Chart(el, {
      type: 'line',
      data: {
        labels: e.labels,
        datasets: [{
          data: e.values, borderColor: C.s1, borderWidth: 2, tension: 0.25, fill: false,
          pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: C.s1, pointBorderColor: C.surface, pointBorderWidth: 2,
        }],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: catAxis({ ticks: { color: C.axis, maxRotation: 0, autoSkip: true, maxTicksLimit: 6, padding: 6, callback: function (v) { return String(this.getLabelForValue(v)).split(' · ')[0]; } } }),
          y: gridAxis({ min: 0, max: 20, ticks: { padding: 8, color: C.axis, stepSize: 5 } }),
        },
        plugins: {
          axpThreshold: { value: 10, label: '10/20' },
          tooltip: { callbacks: {
            title: function (i) { return (e.titles[i[0].dataIndex] || '') + ' — ' + e.labels[i[0].dataIndex].split(' · ')[1]; },
            label: function (i) { return 'Moyenne : ' + fr(i.parsed.y, 2) + ' /20 · le ' + e.labels[i.dataIndex].split(' · ')[0]; },
          } },
        },
      },
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof Chart === 'undefined') return;
    var d = readData();
    if (!d) return;
    defaults();
    [trend, presenceClasses, weekdays, histogram, classesMoyenne, matieres, evolution].forEach(function (fn) {
      try {
        fn(d);
      } catch (err) {
        if (window.console) console.error('[dashboard enseignant]', fn.name, err);
      }
    });
  });
})();
