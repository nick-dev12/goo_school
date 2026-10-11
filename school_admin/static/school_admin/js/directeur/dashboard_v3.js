/**
 * Aria — tableau de bord de la direction (V3).
 * Graphiques Chart.js alimentés par les blocs json_script du gabarit.
 * Palette de référence validée : série 1 bleu, série 2 orange, statuts réservés.
 */
(function () {
  'use strict';

  var C = {
    s1: '#2a78d6',
    s1Tint: 'rgba(42, 120, 214, 0.10)',
    s2: '#eb6834',
    critical: '#d03b3b',
    warning: '#fab219',
    good: '#0ca30c',
    track: '#e7eaef',
    muted: '#b9c2cf',
    ink: '#101828',
    ink2: '#475467',
    axis: '#8a919e',
    grid: '#eef0f3',
    surface: '#ffffff',
  };

  function data(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function fmtNumber(value) {
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value || 0);
  }

  function fmtShort(value) {
    var v = Number(value) || 0;
    if (Math.abs(v) >= 1e6) return (v / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' M';
    if (Math.abs(v) >= 1e3) return (v / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + ' k';
    return fmtNumber(v);
  }

  /* Ligne de seuil fine (horizontale ou verticale) avec son libellé. */
  var thresholdPlugin = {
    id: 'axdThreshold',
    afterDatasetsDraw: function (chart, _args, opts) {
      if (!opts || opts.value == null) return;
      var ctx = chart.ctx;
      var area = chart.chartArea;
      var scale = chart.scales[opts.axis || 'y'];
      if (!scale) return;
      var pos = scale.getPixelForValue(opts.value);
      ctx.save();
      ctx.strokeStyle = opts.color || C.critical;
      ctx.lineWidth = 1;
      ctx.beginPath();
      if ((opts.axis || 'y') === 'y') {
        ctx.moveTo(area.left, pos);
        ctx.lineTo(area.right, pos);
      } else {
        ctx.moveTo(pos, area.top);
        ctx.lineTo(pos, area.bottom);
      }
      ctx.stroke();
      if (opts.label) {
        ctx.font = '600 11px Inter, system-ui, sans-serif';
        ctx.fillStyle = opts.color || C.critical;
        if ((opts.axis || 'y') === 'y') {
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

  /* Réticule vertical au survol des courbes. */
  var crosshairPlugin = {
    id: 'axdCrosshair',
    afterDatasetsDraw: function (chart, _args, opts) {
      if (!opts || !opts.enabled) return;
      var active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      var x = active[0].element.x;
      var area = chart.chartArea;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = 'rgba(16, 24, 40, 0.18)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, area.top);
      ctx.lineTo(x, area.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  function setDefaults() {
    var d = Chart.defaults;
    d.font.family = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
    d.font.size = 12;
    d.color = C.axis;
    d.animation.duration = 450;
    d.maintainAspectRatio = false;
    d.responsive = true;
    d.plugins.legend.display = false;
    var t = d.plugins.tooltip;
    t.backgroundColor = C.ink;
    t.titleColor = '#ffffff';
    t.bodyColor = '#e4e7ec';
    t.titleFont = { weight: '600', size: 12 };
    t.bodyFont = { size: 12 };
    t.padding = 10;
    t.cornerRadius = 8;
    t.boxWidth = 8;
    t.boxHeight = 8;
    t.boxPadding = 4;
    t.usePointStyle = true;
    t.caretSize = 5;
    Chart.register(thresholdPlugin, crosshairPlugin);
  }

  function axisCommon(extra) {
    return Object.assign({
      grid: { color: C.grid, drawTicks: false },
      border: { display: false },
      ticks: { padding: 8, color: C.axis },
    }, extra || {});
  }

  function noGrid(extra) {
    return Object.assign({
      grid: { display: false },
      border: { color: '#d5d9e0' },
      ticks: { padding: 6, color: C.ink2 },
    }, extra || {});
  }

  /* ---------- 1. Présence quotidienne ---------- */
  function trendChart() {
    var d = data('axd-data-trend');
    var el = document.getElementById('axd-chart-trend');
    if (!d || !el || !d.values || !d.values.length) return;
    var min = Math.min.apply(null, d.values.concat([85]));
    new Chart(el, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'Présence',
          data: d.values,
          borderColor: C.s1,
          backgroundColor: C.s1Tint,
          borderWidth: 2,
          fill: 'origin',
          tension: 0.32,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: C.surface,
          pointHoverBackgroundColor: C.s1,
        }],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: noGrid({ ticks: { color: C.axis, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, padding: 6 } }),
          y: axisCommon({
            min: Math.max(0, Math.floor((min - 5) / 5) * 5),
            max: 100,
            ticks: { padding: 8, color: C.axis, stepSize: 5, callback: function (v) { return v + ' %'; } },
          }),
        },
        plugins: {
          axdThreshold: { value: 85, label: 'Seuil 85 %', color: C.critical },
          axdCrosshair: { enabled: true },
          tooltip: {
            callbacks: {
              label: function (item) { return ' Présence : ' + item.parsed.y.toLocaleString('fr-FR') + ' %'; },
            },
          },
        },
      },
    });
  }

  /* ---------- 2. Mini-courbe de l'indicateur présence ---------- */
  function sparkline() {
    var d = data('axd-data-trend');
    var el = document.getElementById('axd-spark');
    if (!d || !el || !d.values || d.values.length < 2) return;
    new Chart(el, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [{
          data: d.values,
          borderColor: C.s1,
          backgroundColor: C.s1Tint,
          borderWidth: 2,
          fill: 'origin',
          tension: 0.35,
          pointRadius: 0,
        }],
      },
      options: {
        animation: false,
        events: [],
        scales: { x: { display: false }, y: { display: false, min: Math.max(0, Math.min.apply(null, d.values) - 4) } },
        plugins: { tooltip: { enabled: false } },
        layout: { padding: { top: 2, bottom: 2 } },
      },
    });
  }

  /* ---------- 3. Répartition des moyennes ---------- */
  function gradesChart() {
    var d = data('axd-data-grades');
    var el = document.getElementById('axd-chart-grades');
    if (!d || !el || !d.values) return;
    var seuil = parseFloat(el.getAttribute('data-seuil')) || 10;
    var highs = [8, 10, 12, 14, 16, 20.01];
    var colors = d.labels.map(function (_l, i) { return highs[i] <= seuil ? C.critical : C.s1; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'Élèves',
          data: d.values,
          backgroundColor: colors,
          hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 },
          borderSkipped: 'start',
          maxBarThickness: 46,
          categoryPercentage: 0.82,
          barPercentage: 0.92,
        }],
      },
      options: {
        scales: {
          x: noGrid({ title: { display: true, text: 'Moyenne générale (/20)', color: C.axis, padding: { top: 8 } } }),
          y: axisCommon({ beginAtZero: true, ticks: { padding: 8, color: C.axis, precision: 0 } }),
        },
        plugins: {
          tooltip: {
            callbacks: {
              title: function (items) { return 'Moyenne ' + items[0].label; },
              label: function (item) {
                var total = d.values.reduce(function (a, b) { return a + b; }, 0) || 1;
                return ' ' + fmtNumber(item.parsed.y) + ' (' + Math.round(item.parsed.y / total * 100) + ' %)';
              },
            },
          },
        },
      },
    });
  }

  /* ---------- 4. Présence par classe (barres horizontales) ---------- */
  function presenceClassesChart() {
    var rows = data('axd-data-presence-classes');
    var el = document.getElementById('axd-chart-presence-classes');
    if (!rows || !el || !rows.length) return;
    var colors = rows.map(function (r) { return r.watch ? C.critical : C.s1; });
    var min = Math.min.apply(null, rows.map(function (r) { return r.taux; }).concat([85]));
    new Chart(el, {
      type: 'bar',
      data: {
        labels: rows.map(function (r) { return (r.watch ? '▲ ' : '') + r.classe; }),
        datasets: [{
          label: 'Présence',
          data: rows.map(function (r) { return r.taux; }),
          backgroundColor: colors,
          hoverBackgroundColor: colors,
          borderRadius: { topRight: 4, bottomRight: 4 },
          borderSkipped: 'start',
          maxBarThickness: 18,
          categoryPercentage: 0.8,
          barPercentage: 0.9,
        }],
      },
      options: {
        indexAxis: 'y',
        scales: {
          x: axisCommon({
            min: Math.max(0, Math.floor((min - 5) / 5) * 5),
            max: 100,
            ticks: { padding: 6, color: C.axis, callback: function (v) { return v + ' %'; } },
          }),
          y: noGrid({ ticks: { color: C.ink2, padding: 6, autoSkip: false, font: { weight: '500' } } }),
        },
        plugins: {
          axdThreshold: { value: 85, axis: 'x', label: '85 %', color: C.critical },
          tooltip: {
            callbacks: {
              title: function (items) { return rows[items[0].dataIndex].classe; },
              label: function (item) {
                var r = rows[item.dataIndex];
                return ' ' + r.taux.toLocaleString('fr-FR') + ' % · ' + fmtNumber(r.n) + ' appels';
              },
            },
          },
        },
      },
    });
  }

  /* ---------- 5. Effectifs et capacité (barres empilées) ---------- */
  function occupationChart() {
    var d = data('axd-data-occupation');
    var el = document.getElementById('axd-chart-occupation');
    if (!d || !el || !d.labels || !d.labels.length) return;
    var hasOver = d.depassement.some(function (v) { return v > 0; });
    var datasets = [
      { label: 'Inscrits', data: d.effectif, backgroundColor: C.s1, hoverBackgroundColor: C.s1 },
      { label: 'Places libres', data: d.libres, backgroundColor: C.track, hoverBackgroundColor: '#dde1e8' },
    ];
    if (hasOver) {
      datasets.push({ label: 'Dépassement', data: d.depassement, backgroundColor: C.critical, hoverBackgroundColor: C.critical });
    }
    datasets.forEach(function (ds) {
      ds.borderColor = C.surface;
      ds.borderWidth = { right: 2 };
      ds.borderSkipped = false;
      ds.borderRadius = 3;
      ds.maxBarThickness = 18;
      ds.categoryPercentage = 0.8;
      ds.barPercentage = 0.9;
    });
    new Chart(el, {
      type: 'bar',
      data: { labels: d.labels, datasets: datasets },
      options: {
        indexAxis: 'y',
        interaction: { mode: 'index', axis: 'y', intersect: false },
        scales: {
          x: axisCommon({ stacked: true, beginAtZero: true, ticks: { padding: 6, color: C.axis, precision: 0 } }),
          y: noGrid({ stacked: true, ticks: { color: C.ink2, padding: 6, autoSkip: false, font: { weight: '500' } } }),
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: function (item) { return ' ' + item.dataset.label + ' : ' + fmtNumber(item.parsed.x); },
              footer: function (items) {
                var i = items[0].dataIndex;
                var cap = d.effectif[i] + d.libres[i] - d.depassement[i];
                return cap ? 'Taux : ' + Math.round(d.effectif[i] / cap * 100) + ' %' : '';
              },
            },
          },
        },
      },
    });
  }

  /* ---------- 6. Encaissements + statuts des dossiers ---------- */
  function financeCharts() {
    var d = data('axd-data-finance');
    if (!d) return;
    var el = document.getElementById('axd-chart-payments');
    var devise = el ? el.getAttribute('data-devise') || '' : '';
    if (el && d.payments && d.payments.labels && d.payments.labels.length) {
      new Chart(el, {
        type: 'bar',
        data: {
          labels: d.payments.labels,
          datasets: [{
            label: 'Encaissé',
            data: d.payments.values,
            backgroundColor: C.s1,
            hoverBackgroundColor: '#1c5cab',
            borderRadius: { topLeft: 4, topRight: 4 },
            borderSkipped: 'start',
            maxBarThickness: 22,
            categoryPercentage: 0.8,
            barPercentage: 0.9,
          }],
        },
        options: {
          scales: {
            x: noGrid({ ticks: { color: C.axis, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, padding: 6 } }),
            y: axisCommon({ beginAtZero: true, ticks: { padding: 8, color: C.axis, callback: fmtShort } }),
          },
          plugins: {
            tooltip: {
              callbacks: {
                label: function (item) { return ' ' + fmtNumber(item.parsed.y) + ' ' + devise; },
              },
            },
          },
        },
      });
    }

    var bar = document.getElementById('axd-status-bar');
    var legend = document.getElementById('axd-status-legend');
    if (!bar || !legend || !d.statuts || !d.statuts.labels) return;
    var total = d.statuts.values.reduce(function (a, b) { return a + b; }, 0) || 1;
    function style(label) {
      var l = (label || '').toLowerCase();
      if (l.indexOf('jour') >= 0) return { color: C.good, icon: 'fa-circle-check', iconColor: '#0f7b4a' };
      if (l.indexOf('retard') >= 0) return { color: C.warning, icon: 'fa-clock', iconColor: '#9a5b00' };
      return { color: C.critical, icon: 'fa-circle-xmark', iconColor: '#c0352e' };
    }
    d.statuts.labels.forEach(function (label, i) {
      var value = d.statuts.values[i];
      var s = style(label);
      var pct = Math.round(value / total * 100);
      var seg = document.createElement('span');
      seg.style.width = (value / total * 100) + '%';
      seg.style.background = s.color;
      seg.title = label + ' : ' + value + ' (' + pct + ' %)';
      bar.appendChild(seg);
      var li = document.createElement('li');
      li.innerHTML = '<i class="fas ' + s.icon + '" style="color:' + s.iconColor + '" aria-hidden="true"></i>' +
        '<span></span> <strong>' + fmtNumber(value) + '</strong> <span class="axd-muted-inline">(' + pct + ' %)</span>';
      li.querySelector('span').textContent = label;
      legend.appendChild(li);
    });
  }

  /* ---------- 7. Absences selon le jour ---------- */
  function weekdaysChart() {
    var d = data('axd-data-weekdays');
    var el = document.getElementById('axd-chart-weekdays');
    if (!d || !el || !d.labels || !d.labels.length) return;
    var peak = d.absences.indexOf(Math.max.apply(null, d.absences));
    var colors = d.absences.map(function (_v, i) { return i === peak ? C.s1 : C.muted; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'Absences',
          data: d.absences,
          backgroundColor: colors,
          hoverBackgroundColor: colors,
          borderRadius: { topLeft: 4, topRight: 4 },
          borderSkipped: 'start',
          maxBarThickness: 40,
          categoryPercentage: 0.8,
          barPercentage: 0.9,
        }],
      },
      options: {
        scales: {
          x: noGrid(),
          y: axisCommon({ beginAtZero: true, ticks: { padding: 8, color: C.axis, callback: function (v) { return v + ' %'; } } }),
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: function (item) {
                var r = d.retards ? d.retards[item.dataIndex] : null;
                return [' Absences : ' + item.parsed.y.toLocaleString('fr-FR') + ' %'].concat(
                  r != null ? [' Retards : ' + r.toLocaleString('fr-FR') + ' %'] : []
                );
              },
            },
          },
        },
      },
    });
  }

  /* ---------- Interactions ---------- */
  function activityFilter() {
    var chips = document.querySelectorAll('.axd-chip');
    var items = document.querySelectorAll('.axd-feed__item');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var kind = chip.getAttribute('data-kind');
        chips.forEach(function (c) {
          c.classList.toggle('is-active', c === chip);
          c.setAttribute('aria-pressed', c === chip ? 'true' : 'false');
        });
        items.forEach(function (item) {
          item.hidden = !!kind && item.getAttribute('data-kind') !== kind;
        });
      });
    });
  }

  function autoSubmitFilters() {
    document.querySelectorAll('select[data-autosubmit]').forEach(function (select) {
      select.addEventListener('change', function () {
        if (select.form) select.form.submit();
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    activityFilter();
    autoSubmitFilters();
    if (typeof Chart === 'undefined') return;
    setDefaults();
    [trendChart, sparkline, gradesChart, presenceClassesChart, occupationChart, financeCharts, weekdaysChart]
      .forEach(function (fn) {
        try {
          fn();
        } catch (e) {
          if (window.console) console.error('[dashboard]', fn.name, e);
        }
      });
  });
})();
