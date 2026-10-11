/**
 * Factory Chart.js unique (dashboard directeur).
 */
(function () {
  'use strict';

  function reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function baseOptions(extra) {
    extra = extra || {};
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      animation: reducedMotion() ? false : { duration: 700 },
    }, extra);
  }

  function withLegend(chart, display) {
    if (!chart) return null;
    chart.options.plugins = chart.options.plugins || {};
    chart.options.plugins.legend = { display: !!display, position: 'bottom' };
    return chart;
  }

  function yScale(opts) {
    var scale = { beginAtZero: true };
    if (opts && opts.noMax) {
      return scale;
    }
    if (opts && opts.maxY !== undefined && opts.maxY !== null) {
      scale.max = opts.maxY;
    } else if (!opts || opts.maxY === undefined) {
      scale.max = 100;
    }
    return scale;
  }

  window.DBD_chartFactory = {
    bar: function (canvas, labels, values, opts) {
      if (typeof Chart === 'undefined' || !canvas) return null;
      opts = opts || {};
      var category = { beginAtZero: true };
      var valueScale = { beginAtZero: true };
      if (opts.maxY !== undefined && opts.maxY !== null) {
        valueScale.max = opts.maxY;
      }
      return withLegend(new Chart(canvas, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: opts.label || '',
            data: values,
            backgroundColor: opts.colors || ['#3b82f6', '#7c3aed', '#10b981', '#fbbf24', '#ef4444'],
            borderRadius: 6,
            maxBarThickness: 28,
          }],
        },
        options: baseOptions({
          indexAxis: opts.horizontal ? 'y' : 'x',
          plugins: { legend: { display: !!opts.label } },
          scales: opts.horizontal
            ? { x: valueScale, y: category }
            : { x: category, y: valueScale },
        }),
      }), !!opts.label);
    },
    line: function (canvas, labels, values, opts) {
      if (typeof Chart === 'undefined' || !canvas) return null;
      opts = opts || {};
      return withLegend(new Chart(canvas, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: opts.label || 'Taux (%)',
            data: values,
            borderColor: opts.color || '#3b82f6',
            backgroundColor: opts.fill || 'rgba(59,130,246,0.08)',
            tension: 0.35,
            fill: true,
            pointRadius: 2,
            pointHoverRadius: 4,
          }],
        },
        options: baseOptions({
          plugins: { legend: { display: !!opts.showLegend } },
          scales: { y: yScale(opts) },
        }),
      }), !!opts.showLegend);
    },
    lineMulti: function (canvas, labels, datasets, opts) {
      if (typeof Chart === 'undefined' || !canvas) return null;
      opts = opts || {};
      return new Chart(canvas, {
        type: 'line',
        data: {
          labels: labels,
          datasets: (datasets || []).map(function (ds) {
            return {
              label: ds.label || '',
              data: ds.values || [],
              borderColor: ds.color || '#3b82f6',
              backgroundColor: ds.fill || 'transparent',
              tension: 0.35,
              fill: !!ds.fill,
              pointRadius: 2,
            };
          }),
        },
        options: baseOptions({
          plugins: { legend: { display: true, position: 'bottom' } },
          scales: { y: yScale(opts) },
        }),
      });
    },
    doughnut: function (canvas, labels, values, opts) {
      if (typeof Chart === 'undefined' || !canvas) return null;
      opts = opts || {};
      return new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: opts.colors || ['#3b82f6', '#7c3aed', '#10b981', '#fbbf24', '#ef4444'],
            borderWidth: 0,
          }],
        },
        options: baseOptions({
          responsive: false,
          maintainAspectRatio: false,
          cutout: opts.cutout || '68%',
          rotation: opts.rotation != null ? opts.rotation : 0,
          plugins: { legend: { display: false } },
        }),
      });
    },
    effectifsNest: function (canvas, payload) {
      if (typeof Chart === 'undefined' || !canvas || !payload) return null;

      var gender = payload.gender || {};
      var innerLabels = [];
      var innerData = [];
      var innerColors = [];
      if (gender.female) {
        innerLabels.push('Filles');
        innerData.push(gender.female);
        innerColors.push('#ec4899');
      }
      if (gender.male) {
        innerLabels.push('Garçons');
        innerData.push(gender.male);
        innerColors.push('#2563eb');
      }
      if (gender.unknown) {
        innerLabels.push('Non renseigné');
        innerData.push(gender.unknown);
        innerColors.push('#9ca3af');
      }

      var hasCycles = !!(payload.labels && payload.labels.length && payload.values && payload.values.length);
      var hasGender = innerData.length > 0;
      if (!hasCycles && !hasGender) return null;

      function outerRadius(ctx) {
        var chart = ctx.chart;
        var area = chart.chartArea;
        if (!area) return 0;
        return Math.min(area.width, area.height) / 2;
      }

      function innerRadius(ctx) {
        return outerRadius(ctx) * 0.52;
      }

      var datasets = [];
      if (hasCycles) {
        datasets.push({
          label: 'Cycles',
          data: payload.values,
          backgroundColor: payload.colors || ['#3b82f6', '#7c3aed', '#10b981', '#f59e0b', '#ef4444'],
          borderWidth: 2,
          borderColor: '#ffffff',
          radius: outerRadius,
          cutout: '54%',
          order: 1,
        });
      }
      if (hasGender) {
        datasets.push({
          label: 'Genre',
          data: innerData,
          backgroundColor: innerColors,
          borderWidth: 2,
          borderColor: '#ffffff',
          radius: innerRadius,
          cutout: '42%',
          order: 2,
        });
      }

      var genderValues = innerData.slice();

      var genderLabelPlugin = {
        id: 'dbdGenderArcLabels',
        afterDatasetsDraw: function (chart) {
          if (!hasGender || chart.getDatasetMeta(1).hidden) return;
          var meta = chart.getDatasetMeta(hasCycles ? 1 : 0);
          if (!meta || !meta.data) return;
          var ctx = chart.ctx;
          ctx.save();
          ctx.fillStyle = '#ffffff';
          ctx.font = '600 12px system-ui, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          meta.data.forEach(function (arc, i) {
            var value = genderValues[i];
            if (!value) return;
            var pos = arc.tooltipPosition();
            ctx.fillText(String(value), pos.x, pos.y);
          });
          ctx.restore();
        },
      };

      return new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: hasCycles ? payload.labels : innerLabels,
          datasets: datasets,
        },
        options: baseOptions({
          layout: { padding: 4 },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var name = ctx.dataset.label === 'Genre'
                    ? innerLabels[ctx.dataIndex] || ctx.label
                    : (payload.labels && payload.labels[ctx.dataIndex]) || ctx.label;
                  return (name || '') + ' : ' + ctx.parsed;
                },
              },
            },
          },
        }),
        plugins: [genderLabelPlugin],
      });
    },
  };
})();
