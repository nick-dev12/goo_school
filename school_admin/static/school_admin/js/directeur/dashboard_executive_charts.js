/**
 * Graphiques executive — utilise DBD_chartFactory.
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

  window.DBD_initExecutiveCharts = function () {
    if (!window.DBD_chartFactory) return;

    var cycles = readJson('dbd-executive-chart-data');
    var cycleCanvas = document.getElementById('dbd-chart-cycles');
    if (cycleCanvas && cycles && cycles.labels && cycles.labels.length && cycleCanvas.dataset.chartReady !== '1') {
      window.DBD_chartFactory.bar(cycleCanvas, cycles.labels, cycles.values, { horizontal: true, label: '' });
      cycleCanvas.dataset.chartReady = '1';
    }

    var trend = readJson('dbd-presence-trend-data');
    var trendCanvas = document.getElementById('dbd-chart-presence-trend');
    if (trendCanvas && trend && trend.labels && trend.labels.length && trendCanvas.dataset.chartReady !== '1') {
      window.DBD_chartFactory.line(trendCanvas, trend.labels, trend.values, { label: 'Présence (%)' });
      trendCanvas.dataset.chartReady = '1';
    }

    var grades = readJson('dbd-grades-chart-data');
    var gradesCanvas = document.getElementById('dbd-chart-grades');
    if (gradesCanvas && grades && grades.labels && grades.labels.length && gradesCanvas.dataset.chartReady !== '1') {
      window.DBD_chartFactory.bar(gradesCanvas, grades.labels, grades.values, {
        label: '',
        colors: ['#ef4444', '#f59e0b', '#fbbf24', '#3b82f6', '#7c3aed', '#10b981'],
      });
      gradesCanvas.dataset.chartReady = '1';
    }

    var finance = readJson('dbd-finance-chart-data');
    var statutsCanvas = document.getElementById('dbd-chart-finance-statuts');
    if (
      statutsCanvas
      && finance
      && finance.statuts
      && finance.statuts.labels
      && finance.statuts.labels.length
      && statutsCanvas.dataset.chartReady !== '1'
    ) {
      window.DBD_chartFactory.bar(statutsCanvas, finance.statuts.labels, finance.statuts.values, {
        label: '',
        colors: ['#10b981', '#fbbf24', '#ef4444'],
      });
      statutsCanvas.dataset.chartReady = '1';
    }
    var paymentsCanvas = document.getElementById('dbd-chart-finance-payments');
    if (
      paymentsCanvas
      && finance
      && finance.payments
      && finance.payments.labels
      && finance.payments.labels.length
      && paymentsCanvas.dataset.chartReady !== '1'
    ) {
      window.DBD_chartFactory.line(paymentsCanvas, finance.payments.labels, finance.payments.values, {
        label: 'Encaissements',
        color: '#10b981',
      });
      paymentsCanvas.dataset.chartReady = '1';
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.DBD_initExecutiveCharts === 'function') {
      window.DBD_initExecutiveCharts();
    }
  });
})();
