/**
 * Bilan scolarité — onglets + graphiques Chart.js (UI v2)
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'directeur:bilan-scolarite';
  var TAB_SELECTOR = '.scb-tab-btn[data-scb-tab]';

  function persistSection(section) {
    if (!window.directeurTabStorage) return;
    window.directeurTabStorage.syncUrlAndStore(STORAGE_KEY, {
      section: section || 'synthese',
    });
  }

  function switchScbTab(tabId, btn, opts) {
    opts = opts || {};
    document.querySelectorAll('.scb-tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
      panel.hidden = true;
    });
    document.querySelectorAll(TAB_SELECTOR).forEach(function (b) {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    var panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add('active');
      panel.hidden = false;
    }
    var targetBtn = btn || document.querySelector(TAB_SELECTOR + '[data-scb-tab="' + tabId + '"]');
    if (targetBtn) {
      targetBtn.classList.add('active');
      targetBtn.setAttribute('aria-selected', 'true');
      if (!opts.skipPersist) {
        persistSection(targetBtn.getAttribute('data-section') || 'synthese');
      }
    }
    if (tabId === 'scb-panel-graphiques' && window.SCB_initCharts && !window.SCB_chartsReady) {
      window.SCB_initCharts();
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  }

  function restoreSectionFromStorage() {
    if (!window.directeurTabStorage) return false;
    var params = new URLSearchParams(window.location.search);
    if (!params.has('section')) {
      var stored = window.directeurTabStorage.readStore(STORAGE_KEY);
      if (stored.section) {
        params.set('section', stored.section);
        window.location.replace(window.location.pathname + '?' + params.toString());
        return true;
      }
    }
    window.directeurTabStorage.mergeUrlFromStore(STORAGE_KEY, ['section']);
    var section = params.get('section') || 'synthese';
    var targetBtn = document.querySelector(TAB_SELECTOR + '[data-section="' + CSS.escape(section) + '"]');
    if (targetBtn) {
      switchScbTab(targetBtn.getAttribute('data-scb-tab'), targetBtn, { skipPersist: true });
      persistSection(section);
    } else if (document.querySelector('.scb-tab-panel.active')) {
      var activePanel = document.querySelector('.scb-tab-panel.active');
      if (activePanel.id === 'scb-panel-graphiques' && window.SCB_initCharts && !window.SCB_chartsReady) {
        window.SCB_initCharts();
      }
    }
    return false;
  }

  function readChartData() {
    var el = document.getElementById('scb-chart-data');
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  window.SCB_initCharts = function () {
    if (window.SCB_chartsReady || typeof Chart === 'undefined') return;
    var data = readChartData();
    if (!data) return;

    var devise = data.devise || 'FCFA';
    Chart.defaults.font.family = "'Poppins', sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#6b7280';

    function moneyTooltip(label) {
      return function (context) {
        return label + ': ' + context.parsed.y.toLocaleString('fr-FR') + ' ' + devise;
      };
    }

    var el1 = document.getElementById('evolutionPaiementsChart');
    if (el1) {
      new Chart(el1, {
        type: 'line',
        data: {
          labels: data.mois.labels,
          datasets: [
            { label: 'Montant collecté', data: data.mois.montantsCollectes, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', tension: 0.4, fill: true },
            { label: 'Montant payé', data: data.mois.montantsPayes, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.4, fill: true },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: moneyTooltip('') } } }, scales: { y: { beginAtZero: true } } },
      });
    }

    var el2 = document.getElementById('modesPaiementChart');
    if (el2 && data.modes.labels.length) {
      new Chart(el2, {
        type: 'doughnut',
        data: { labels: data.modes.labels, datasets: [{ data: data.modes.montants, backgroundColor: data.modes.couleurs, borderWidth: 2, borderColor: '#fff' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } },
      });
    }

    var el3 = document.getElementById('montantsDusPayesChart');
    if (el3) {
      new Chart(el3, {
        type: 'bar',
        data: {
          labels: data.mois.labels,
          datasets: [
            { label: 'Montant dû', data: data.mois.montantsDus, backgroundColor: 'rgba(239,68,68,0.7)', borderColor: '#ef4444', borderWidth: 1 },
            { label: 'Montant payé', data: data.mois.montantsPayes, backgroundColor: 'rgba(16,185,129,0.7)', borderColor: '#10b981', borderWidth: 1 },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: { y: { beginAtZero: true } } },
      });
    }

    var el4 = document.getElementById('tauxRecouvrementChart');
    if (el4) {
      new Chart(el4, {
        type: 'line',
        data: { labels: data.mois.labels, datasets: [{ label: 'Taux (%)', data: data.mois.tauxRecouvrement, borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.1)', tension: 0.4, fill: true }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: 100 } } },
      });
    }

    var el5 = document.getElementById('elevesRetardChart');
    if (el5) {
      new Chart(el5, {
        type: 'bar',
        data: {
          labels: data.mois.labels,
          datasets: [
            { label: 'En retard', data: data.mois.elevesEnRetard, backgroundColor: 'rgba(251,191,36,0.7)', borderColor: '#fbbf24', borderWidth: 1 },
            { label: 'Impayés', data: data.mois.elevesImpayes, backgroundColor: 'rgba(239,68,68,0.7)', borderColor: '#ef4444', borderWidth: 1 },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } },
      });
    }

    var el6 = document.getElementById('statistiquesClassesChart');
    if (el6 && data.classes.labels.length) {
      new Chart(el6, {
        type: 'bar',
        data: {
          labels: data.classes.labels,
          datasets: [
            { label: 'Montant dû', data: data.classes.montantsDus, backgroundColor: 'rgba(139,92,246,0.7)', borderColor: '#8b5cf6', borderWidth: 1 },
            { label: 'Montant payé', data: data.classes.montantsPayes, backgroundColor: 'rgba(16,185,129,0.7)', borderColor: '#10b981', borderWidth: 1 },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
      });
    }

    window.SCB_chartsReady = true;
  };

  document.addEventListener('click', function (event) {
    var tabBtn = event.target.closest('.scb-tab-btn[data-scb-tab]');
    if (tabBtn) {
      switchScbTab(tabBtn.getAttribute('data-scb-tab'), tabBtn);
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (restoreSectionFromStorage()) {
      return;
    }
    var active = document.querySelector('.scb-tab-panel.active');
    if (active && active.id === 'scb-panel-graphiques' && window.SCB_initCharts && !window.SCB_chartsReady) {
      window.SCB_initCharts();
    }
    if (typeof window.layoutTabsOverflowNav === 'function') {
      window.layoutTabsOverflowNav();
    }
  });
})();
