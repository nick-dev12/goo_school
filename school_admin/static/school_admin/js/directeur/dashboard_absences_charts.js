/**
 * Dashboard directeur — graphiques onglet Absences (Chart.js lazy)
 */
(function () {
  'use strict';

  var PALETTE = ['#3b82f6', '#ec4899', '#10b981', '#fbbf24', '#ef4444', '#8b5cf6'];
  var charts = [];

  function readChartData() {
    var el = document.getElementById('dbd-absences-chart-data');
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function destroyCharts() {
    charts.forEach(function (c) {
      if (c && typeof c.destroy === 'function') {
        c.destroy();
      }
    });
    charts = [];
    window.DBD_absencesChartsReady = false;
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function animateCounters(root) {
    if (prefersReducedMotion()) return;
    var nodes = (root || document).querySelectorAll('[data-dbd-count]');
    nodes.forEach(function (node, index) {
      var target = parseFloat(node.getAttribute('data-dbd-count') || '0', 10);
      if (isNaN(target)) return;
      var suffix = node.getAttribute('data-dbd-suffix') || '';
      var isFloat = String(node.getAttribute('data-dbd-count')).indexOf('.') !== -1;
      var start = 0;
      var duration = 600;
      var startTime = null;
      function step(ts) {
        if (!startTime) startTime = ts;
        var p = Math.min((ts - startTime) / duration, 1);
        var val = start + (target - start) * p;
        node.textContent = (isFloat ? val.toFixed(1) : Math.round(val)) + suffix;
        if (p < 1) {
          window.requestAnimationFrame(step);
        }
      }
      window.setTimeout(function () {
        window.requestAnimationFrame(step);
      }, index * 40);
    });
  }

  function addChart(config) {
    if (typeof Chart === 'undefined') return;
    var instance = new Chart(config.ctx, config.options);
    charts.push(instance);
  }

  window.DBD_initAbsencesCharts = function (opts) {
    opts = opts || {};
    if (window.DBD_absencesChartsReady && !opts.force) return;
    if (typeof Chart === 'undefined') return;

    var panel = document.getElementById('tab-absences');
    if (!panel || panel.hidden) return;

    destroyCharts();
    var data = readChartData();
    if (!data) return;

    Chart.defaults.font.family = "'Poppins', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#6b7280';
    var anim = prefersReducedMotion() ? false : { duration: 800 };

    var sexeEl = document.getElementById('dbd-chart-sexe-nj');
    if (sexeEl && data.sexe_nj) {
      addChart({
        ctx: sexeEl,
        options: {
          type: 'doughnut',
          data: {
            labels: data.sexe_nj.labels,
            datasets: [{
              data: data.sexe_nj.values,
              backgroundColor: ['#ec4899', '#3b82f6'],
              borderWidth: 2,
              borderColor: '#fff',
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, animation: anim, plugins: { legend: { position: 'bottom' } } },
        },
      });
    }

    var topEl = document.getElementById('dbd-chart-top-classes');
    if (topEl && data.top_classes && data.top_classes.labels.length) {
      addChart({
        ctx: topEl,
        options: {
          type: 'bar',
          data: {
            labels: data.top_classes.labels,
            datasets: [{
              label: 'Taux (%)',
              data: data.top_classes.values,
              backgroundColor: 'rgba(59,130,246,0.75)',
              borderColor: '#3b82f6',
              borderWidth: 1,
            }],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: anim,
            scales: { x: { beginAtZero: true, max: 100 } },
            plugins: { legend: { display: false } },
          },
        },
      });
    }

    var trEl = document.getElementById('dbd-chart-tranches');
    if (trEl && data.tranches_eleves) {
      addChart({
        ctx: trEl,
        options: {
          type: 'bar',
          data: {
            labels: data.tranches_eleves.labels,
            datasets: [{
              label: 'Élèves',
              data: data.tranches_eleves.values,
              backgroundColor: PALETTE,
              borderWidth: 0,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: anim,
            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
            plugins: { legend: { display: false } },
          },
        },
      });
    }

    var evEl = document.getElementById('dbd-chart-evolution');
    if (evEl && data.evolution_mensuelle) {
      addChart({
        ctx: evEl,
        options: {
          type: 'line',
          data: {
            labels: data.evolution_mensuelle.labels,
            datasets: [
              {
                label: 'Non justifiées',
                data: data.evolution_mensuelle.absences_nj,
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239,68,68,0.08)',
                tension: 0.35,
                fill: true,
              },
              {
                label: 'Justifiées',
                data: data.evolution_mensuelle.absences_justifiees,
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139,92,246,0.08)',
                tension: 0.35,
                fill: true,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: anim,
            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
          },
        },
      });
    }

    var stEl = document.getElementById('dbd-chart-statuts');
    if (stEl && data.statuts) {
      addChart({
        ctx: stEl,
        options: {
          type: 'doughnut',
          data: {
            labels: data.statuts.labels,
            datasets: [{
              data: data.statuts.values,
              backgroundColor: ['#10b981', '#ef4444', '#8b5cf6', '#fbbf24'],
              borderWidth: 2,
              borderColor: '#fff',
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, animation: anim, plugins: { legend: { position: 'bottom' } } },
        },
      });
    }

    var botEl = document.getElementById('dbd-chart-bottom-classes');
    if (botEl && data.bottom_classes && data.bottom_classes.labels.length) {
      addChart({
        ctx: botEl,
        options: {
          type: 'bar',
          data: {
            labels: data.bottom_classes.labels,
            datasets: [{
              label: 'Taux (%)',
              data: data.bottom_classes.values,
              backgroundColor: 'rgba(239,68,68,0.7)',
              borderColor: '#ef4444',
              borderWidth: 1,
            }],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: anim,
            scales: { x: { beginAtZero: true, max: 100 } },
            plugins: { legend: { display: false } },
          },
        },
      });
    }

    animateCounters(panel);
    window.DBD_absencesChartsReady = true;
  };

  window.DBD_destroyAbsencesCharts = destroyCharts;
})();
