/**
 * Graphiques maquette premium — Chart.js via DBD_chartFactory.
 */
(function () {
  'use strict';

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function hasSeries(payload, key) {
    var series = key ? payload && payload[key] : payload;
    return !!(series && series.labels && series.labels.length);
  }

  window.DBD_initPremiumCharts = function () {
    if (!window.DBD_chartFactory) return;

    var trend = readJson('dbd-presence-trend-data');
    var situation = document.getElementById('dbd-chart-situation');
    if (situation && hasSeries(trend) && situation.dataset.chartReady !== '1') {
      try {
        window.DBD_chartFactory.line(situation, trend.labels, trend.values, {
          label: 'Présence (%)',
          maxY: 100,
        });
        situation.dataset.chartReady = '1';
      } catch (err) {
        console.error('situation', err);
      }
    }

    var cycles = readJson('dbd-executive-chart-data');
    var pie = document.getElementById('dbd-chart-gender-pie');
    if (pie && cycles && cycles.gender && pie.dataset.chartReady !== '1') {
      var gender = cycles.gender;
      var gLabels = [];
      var gValues = [];
      var gColors = [];
      if (gender.female) {
        gLabels.push(gender.female + ' filles');
        gValues.push(gender.female);
        gColors.push('#ec4899');
      }
      if (gender.male) {
        gLabels.push(gender.male + ' garçons');
        gValues.push(gender.male);
        gColors.push('#2563eb');
      }
      if (gender.unknown) {
        gLabels.push(gender.unknown + ' non renseigné');
        gValues.push(gender.unknown);
        gColors.push('#9ca3af');
      }
      if (gValues.length) {
        try {
          pie.width = 180;
          pie.height = 180;
          window.DBD_chartFactory.doughnut(pie, gLabels, gValues, {
            colors: gColors,
            cutout: '0%',
            rotation: 180,
          });
          pie.dataset.chartReady = '1';
        } catch (err) {
          console.error('gender pie', err);
        }
      }
    }

    var classes = readJson('dbd-presence-classes-data');
    var classCanvas = document.getElementById('dbd-chart-presence-classes');
    if (classCanvas && hasSeries(classes) && classCanvas.dataset.chartReady !== '1') {
      window.DBD_chartFactory.bar(classCanvas, classes.labels, classes.values, {
        horizontal: true,
        colors: classes.colors,
        maxY: 100,
      });
      classCanvas.dataset.chartReady = '1';
    }

    var grades = readJson('dbd-grades-chart-data');
    var gradesCanvas = document.getElementById('dbd-chart-grades');
    if (gradesCanvas && grades && gradesCanvas.dataset.chartReady !== '1') {
      var byCycle = grades.by_cycle;
      if (hasSeries(byCycle)) {
        window.DBD_chartFactory.bar(gradesCanvas, byCycle.labels, byCycle.values, {
          colors: ['#7c3aed', '#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
          maxY: 100,
          label: 'Réussite (%)',
        });
        gradesCanvas.dataset.chartReady = '1';
      } else if (hasSeries(grades)) {
        window.DBD_chartFactory.bar(gradesCanvas, grades.labels, grades.values, {
          colors: ['#ef4444', '#f59e0b', '#fbbf24', '#3b82f6', '#7c3aed', '#10b981'],
        });
        gradesCanvas.dataset.chartReady = '1';
      }
    }

    var finance = readJson('dbd-finance-chart-data');
    var payCanvas = document.getElementById('dbd-chart-finance-payments');
    if (payCanvas && finance && payCanvas.dataset.chartReady !== '1') {
      if (hasSeries(finance.payments)) {
        window.DBD_chartFactory.line(payCanvas, finance.payments.labels, finance.payments.values, {
          label: 'Encaissements',
          color: '#10b981',
          fill: 'rgba(16,185,129,0.10)',
          noMax: true,
        });
        payCanvas.dataset.chartReady = '1';
      } else if (hasSeries(finance.statuts)) {
        window.DBD_chartFactory.bar(payCanvas, finance.statuts.labels, finance.statuts.values, {
          colors: ['#10b981', '#f59e0b', '#ef4444'],
          label: 'Dossiers',
        });
        payCanvas.dataset.chartReady = '1';
      }
    }
  };

  function bootPremiumCharts() {
    if (typeof window.DBD_initPremiumCharts === 'function') {
      window.DBD_initPremiumCharts();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootPremiumCharts);
  } else {
    bootPremiumCharts();
  }
})();
