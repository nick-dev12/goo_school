// Rapports Annuels JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeAnnualTools();
    initializeStrategicTools();
    initializeExecutiveTools();
    initializeTableActions();
    initializeTooltips();
    initializeAnimations();
    initializeModals();
});

// Initialize Tabs
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabButtons.forEach(button => {
        button.addEventListener('click', function () {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and panels
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabPanels.forEach(panel => panel.classList.remove('active'));

            // Add active class to clicked button and corresponding panel
            this.classList.add('active');
            document.getElementById(targetTab).classList.add('active');

            // Update URL hash
            window.location.hash = targetTab;

            // Trigger custom event
            document.dispatchEvent(new CustomEvent('tabChanged', {
                detail: { activeTab: targetTab }
            }));
        });
    });

    // Handle initial tab from URL hash
    const hash = window.location.hash.substring(1);
    if (hash && document.getElementById(hash)) {
        const targetButton = document.querySelector(`[data-tab="${hash}"]`);
        if (targetButton) {
            targetButton.click();
        }
    }
}

// Initialize Annual Tools
function initializeAnnualTools() {
    // Generate Annual Report
    const generateAnnualReportBtn = document.getElementById('generateAnnualReport');
    if (generateAnnualReportBtn) {
        generateAnnualReportBtn.addEventListener('click', function () {
            generateAnnualReport();
        });
    }

    // Generate Comparison
    const generateComparisonBtn = document.getElementById('generateComparison');
    if (generateComparisonBtn) {
        generateComparisonBtn.addEventListener('click', function () {
            generateComparison();
        });
    }

    // Generate Annual Report (header button)
    const generateAnnualReportHeaderBtn = document.getElementById('generateAnnualReport');
    if (generateAnnualReportHeaderBtn) {
        generateAnnualReportHeaderBtn.addEventListener('click', function () {
            generateAnnualReport();
        });
    }
}

// Generate Annual Report
function generateAnnualReport() {
    const button = document.getElementById('generateAnnualReport');
    const year = document.getElementById('reportYear').value;
    const type = document.getElementById('reportType').value;

    showLoading(button, 'Génération en cours...');

    // Simulate annual report generation
    setTimeout(() => {
        const results = simulateAnnualReportGeneration(year, type);
        showAnnualReportResults(results);
        hideLoading(button, 'Générer le bilan annuel');
        showNotification('Bilan annuel généré avec succès', 'success');
        updateAnnualReportsTable();
    }, 4000);
}

// Generate Comparison
function generateComparison() {
    const button = document.getElementById('generateComparison');
    const period = document.getElementById('comparisonPeriod').value;

    showLoading(button, 'Analyse en cours...');

    // Simulate comparison generation
    setTimeout(() => {
        const results = simulateComparisonGeneration(period);
        showComparisonResults(results);
        hideLoading(button, 'Analyser les tendances');
        showNotification('Analyse comparative terminée', 'success');
    }, 3500);
}

// Initialize Strategic Tools
function initializeStrategicTools() {
    // Analyze Strategic Trends
    const analyzeStrategicTrendsBtn = document.getElementById('analyzeStrategicTrends');
    if (analyzeStrategicTrendsBtn) {
        analyzeStrategicTrendsBtn.addEventListener('click', function () {
            analyzeStrategicTrends();
        });
    }

    // Evaluate Performance
    const evaluatePerformanceBtn = document.getElementById('evaluatePerformance');
    if (evaluatePerformanceBtn) {
        evaluatePerformanceBtn.addEventListener('click', function () {
            evaluatePerformance();
        });
    }
}

// Analyze Strategic Trends
function analyzeStrategicTrends() {
    const button = document.getElementById('analyzeStrategicTrends');
    const period = document.getElementById('analysisPeriod').value;

    showLoading(button, 'Analyse en cours...');

    // Simulate strategic trend analysis
    setTimeout(() => {
        const results = simulateStrategicTrendAnalysis(period);
        showStrategicAnalysisResults(results);
        hideLoading(button, 'Analyser les tendances');
        showNotification('Analyse stratégique terminée', 'success');
        updateStrategicAnalysisTable();
    }, 3200);
}

// Evaluate Performance
function evaluatePerformance() {
    const button = document.getElementById('evaluatePerformance');
    const period = document.getElementById('evaluationPeriod').value;

    showLoading(button, 'Évaluation en cours...');

    // Simulate performance evaluation
    setTimeout(() => {
        const results = simulatePerformanceEvaluation(period);
        showPerformanceResults(results);
        hideLoading(button, 'Évaluer la performance');
        showNotification('Évaluation de performance terminée', 'success');
        updateStrategicAnalysisTable();
    }, 2800);
}

// Initialize Executive Tools
function initializeExecutiveTools() {
    // Create Executive Report
    const createExecutiveReportBtn = document.getElementById('createExecutiveReport');
    if (createExecutiveReportBtn) {
        createExecutiveReportBtn.addEventListener('click', function () {
            createExecutiveReport();
        });
    }

    // Create Presentation
    const createPresentationBtn = document.getElementById('createPresentation');
    if (createPresentationBtn) {
        createPresentationBtn.addEventListener('click', function () {
            createPresentation();
        });
    }
}

// Create Executive Report
function createExecutiveReport() {
    const button = document.getElementById('createExecutiveReport');
    const year = document.getElementById('executiveYear').value;
    const type = document.getElementById('executiveType').value;

    showLoading(button, 'Création en cours...');

    // Simulate executive report creation
    setTimeout(() => {
        const results = simulateExecutiveReportCreation(year, type);
        showExecutiveReportResults(results);
        hideLoading(button, 'Créer le rapport exécutif');
        showNotification('Rapport exécutif créé avec succès', 'success');
        updateExecutiveReportsTable();
    }, 2500);
}

// Create Presentation
function createPresentation() {
    const button = document.getElementById('createPresentation');
    const type = document.getElementById('presentationType').value;
    const duration = document.getElementById('presentationDuration').value;

    showLoading(button, 'Création en cours...');

    // Simulate presentation creation
    setTimeout(() => {
        const results = simulatePresentationCreation(type, duration);
        showPresentationResults(results);
        hideLoading(button, 'Créer la présentation');
        showNotification('Présentation créée avec succès', 'success');
        updateExecutiveReportsTable();
    }, 2000);
}

// Initialize Table Actions
function initializeTableActions() {
    const actionButtons = document.querySelectorAll('.btn-action');

    actionButtons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.stopPropagation();
            const action = this.getAttribute('title');
            const row = this.closest('tr');

            handleAction(action, row);
        });
    });
}

// Handle Action
function handleAction(action, row) {
    const actions = {
        'Voir bilan': () => viewReport(row),
        'Télécharger PDF': () => downloadPDF(row),
        'Partager': () => shareReport(row),
        'Dupliquer': () => duplicateReport(row),
        'Voir analyse': () => viewAnalysis(row),
        'Télécharger': () => downloadAnalysis(row),
        'Voir rapport': () => viewExecutiveReport(row),
        'Présenter': () => presentReport(row),
        'Voir progression': () => viewProgress(row),
        'Annuler': () => cancelGeneration(row)
    };

    if (actions[action]) {
        actions[action]();
    } else {
        showNotification(`Action "${action}" non implémentée`, 'info');
    }
}

// Action Functions
function viewReport(row) {
    showNotification('Ouverture du bilan...', 'info');
    setTimeout(() => {
        showReportModal(row);
    }, 500);
}

function viewAnalysis(row) {
    showNotification('Ouverture de l\'analyse...', 'info');
    setTimeout(() => {
        showAnalysisModal(row);
    }, 500);
}

function viewExecutiveReport(row) {
    showNotification('Ouverture du rapport exécutif...', 'info');
    setTimeout(() => {
        showExecutiveModal(row);
    }, 500);
}

function presentReport(row) {
    showNotification('Préparation de la présentation...', 'info');
    setTimeout(() => {
        showPresentationModal(row);
    }, 500);
}

function downloadPDF(row) {
    showNotification('Téléchargement du PDF...', 'info');
    setTimeout(() => {
        showNotification('PDF téléchargé avec succès', 'success');
    }, 1000);
}

function shareReport(row) {
    showNotification('Partage du rapport...', 'info');
    setTimeout(() => {
        showNotification('Rapport partagé avec succès', 'success');
    }, 1000);
}

function duplicateReport(row) {
    showNotification('Duplication du rapport...', 'info');
    setTimeout(() => {
        showNotification('Rapport dupliqué avec succès', 'success');
        updateAnnualReportsTable();
    }, 800);
}

function downloadAnalysis(row) {
    showNotification('Téléchargement de l\'analyse...', 'info');
    setTimeout(() => {
        showNotification('Analyse téléchargée avec succès', 'success');
    }, 1000);
}

function viewProgress(row) {
    showNotification('Affichage de la progression...', 'info');
    setTimeout(() => {
        showProgressModal(row);
    }, 500);
}

function cancelGeneration(row) {
    if (confirm('Êtes-vous sûr de vouloir annuler la génération ?')) {
        showNotification('Génération annulée', 'info');
        const statusBadge = row.querySelector('.status-badge');
        if (statusBadge) {
            statusBadge.className = 'status-badge annule';
            statusBadge.textContent = 'Annulé';
        }
    }
}

// Simulate Functions
function simulateAnnualReportGeneration(year, type) {
    return {
        year: year,
        type: type,
        status: 'generated',
        size: '8.2 MB',
        date: new Date().toLocaleDateString('fr-FR')
    };
}

function simulateComparisonGeneration(period) {
    return {
        period: period,
        type: 'comparison',
        status: 'completed',
        insights: [
            'Croissance de 28.5% par rapport à l\'année précédente',
            'Meilleure performance: Expansion géographique',
            'Taux de satisfaction en hausse de 15%',
            'Nouveaux marchés: +3 établissements'
        ]
    };
}

function simulateStrategicTrendAnalysis(period) {
    return {
        period: period,
        type: 'strategic',
        status: 'completed',
        trends: [
            'Tendance positive sur 5 ans',
            'Diversification des services réussie',
            'Innovation technologique en progression',
            'Expansion géographique stratégique'
        ]
    };
}

function simulatePerformanceEvaluation(period) {
    return {
        period: period,
        type: 'performance',
        status: 'completed',
        scores: [
            { objective: 'Objectifs financiers', score: 95 },
            { objective: 'Objectifs opérationnels', score: 88 },
            { objective: 'Objectifs de croissance', score: 92 },
            { objective: 'Objectifs de qualité', score: 90 }
        ]
    };
}

function simulateExecutiveReportCreation(year, type) {
    return {
        year: year,
        type: type,
        status: 'created',
        sections: 'Toutes les sections incluses'
    };
}

function simulatePresentationCreation(type, duration) {
    return {
        type: type,
        duration: duration,
        status: 'created',
        slides: 'Présentation générée avec succès'
    };
}

// Show Results Functions
function showAnnualReportResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'annual-highlight';

    resultDiv.innerHTML = `
        <h3><i class="fas fa-check-circle"></i> Bilan annuel généré avec succès</h3>
        <p>Année: ${results.year} | Type: ${results.type} | Taille: ${results.size} | Date: ${results.date}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.annual-form, .comparison-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 8 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 8000);
    }
}

function showComparisonResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'info-message';

    let content = `
        <h4><i class="fas fa-chart-bar"></i> Analyse comparative terminée</h4>
        <p>Période: ${results.period} | Type: ${results.type}</p>
    `;

    if (results.insights) {
        content += '<ul>';
        results.insights.forEach(insight => {
            content += `<li>${insight}</li>`;
        });
        content += '</ul>';
    }

    resultDiv.innerHTML = content;

    // Insert after the form
    const forms = document.querySelectorAll('.comparison-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 10 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 10000);
    }
}

function showStrategicAnalysisResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'strategic-highlight';

    let content = `
        <h4><i class="fas fa-chart-line"></i> Analyse stratégique terminée</h4>
        <p>Période: ${results.period} | Type: ${results.type}</p>
    `;

    if (results.trends) {
        content += '<ul>';
        results.trends.forEach(trend => {
            content += `<li>${trend}</li>`;
        });
        content += '</ul>';
    }

    resultDiv.innerHTML = content;

    // Insert after the form
    const forms = document.querySelectorAll('.strategic-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 10 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 10000);
    }
}

function showPerformanceResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'success-message';

    let content = `
        <h4><i class="fas fa-bullseye"></i> Évaluation de performance terminée</h4>
        <p>Période: ${results.period} | Type: ${results.type}</p>
    `;

    if (results.scores) {
        content += '<ul>';
        results.scores.forEach(score => {
            content += `<li>${score.objective}: ${score.score}%</li>`;
        });
        content += '</ul>';
    }

    resultDiv.innerHTML = content;

    // Insert after the form
    const forms = document.querySelectorAll('.performance-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 8 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 8000);
    }
}

function showExecutiveReportResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'success-message';

    resultDiv.innerHTML = `
        <h4><i class="fas fa-user-tie"></i> Rapport exécutif créé</h4>
        <p>Année: ${results.year} | Type: ${results.type} | Sections: ${results.sections}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.executive-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 6 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 6000);
    }
}

function showPresentationResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'presentation-card';

    resultDiv.innerHTML = `
        <h3><i class="fas fa-presentation"></i> Présentation créée</h3>
        <p>Type: ${results.type} | Durée: ${results.duration} | ${results.slides}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.presentation-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 6 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 6000);
    }
}

// Update Tables
function updateAnnualReportsTable() {
    const tbody = document.querySelector('#bilan-annuel .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="year-info">
                    <h4>${new Date().getFullYear()}</h4>
                    <p>Bilan annuel généré automatiquement</p>
                </div>
            </td>
            <td>
                <span class="report-type complet">Complet</span>
            </td>
            <td>
                <span class="status-badge genere">Généré</span>
            </td>
            <td>
                <span class="date">${new Date().toLocaleDateString('fr-FR')}</span>
            </td>
            <td>
                <span class="file-size">8.2 MB</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir bilan">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Télécharger PDF">
                        <i class="fas fa-file-pdf"></i>
                    </button>
                    <button class="btn-action" title="Partager">
                        <i class="fas fa-share"></i>
                    </button>
                    <button class="btn-action" title="Dupliquer">
                        <i class="fas fa-copy"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(newRow);

        // Add event listeners to new buttons
        initializeTableActions();
    }
}

function updateStrategicAnalysisTable() {
    const tbody = document.querySelector('#analyse-strategique .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="analysis-info">
                    <h4>Nouvelle analyse stratégique - ${new Date().getFullYear()}</h4>
                    <p>Analyse générée automatiquement</p>
                </div>
            </td>
            <td>
                <span class="analysis-type strategique">Stratégique</span>
            </td>
            <td>
                <span class="period">${new Date().getFullYear()}</span>
            </td>
            <td>
                <span class="date">${new Date().toLocaleDateString('fr-FR')}</span>
            </td>
            <td>
                <span class="status-badge genere">Terminée</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir analyse">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Télécharger">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn-action" title="Partager">
                        <i class="fas fa-share"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(newRow);

        // Add event listeners to new buttons
        initializeTableActions();
    }
}

function updateExecutiveReportsTable() {
    const tbody = document.querySelector('#rapports-executifs .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="executive-info">
                    <h4>Nouveau rapport exécutif - ${new Date().getFullYear()}</h4>
                    <p>Rapport créé automatiquement</p>
                </div>
            </td>
            <td>
                <span class="executive-type direction">Direction</span>
            </td>
            <td>
                <span class="year">${new Date().getFullYear()}</span>
            </td>
            <td>
                <span class="date">${new Date().toLocaleDateString('fr-FR')}</span>
            </td>
            <td>
                <span class="status-badge genere">Généré</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir rapport">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Télécharger">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn-action" title="Partager">
                        <i class="fas fa-share"></i>
                    </button>
                    <button class="btn-action" title="Présenter">
                        <i class="fas fa-presentation"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(newRow);

        // Add event listeners to new buttons
        initializeTableActions();
    }
}

// Initialize Tooltips
function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[title]');

    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

// Show Tooltip
function showTooltip(event) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = event.target.getAttribute('title');
    tooltip.style.cssText = `
        position: absolute;
        background: #2d3748;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 12px;
        z-index: 1000;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.2s ease;
        max-width: 200px;
        word-wrap: break-word;
    `;

    document.body.appendChild(tooltip);

    const rect = event.target.getBoundingClientRect();
    tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
    tooltip.style.top = rect.top - tooltip.offsetWidth - 8 + 'px';

    // Adjust if tooltip goes off screen
    if (tooltip.offsetLeft < 0) {
        tooltip.style.left = '8px';
    }
    if (tooltip.offsetLeft + tooltip.offsetWidth > window.innerWidth) {
        tooltip.style.left = (window.innerWidth - tooltip.offsetWidth - 8) + 'px';
    }

    setTimeout(() => {
        tooltip.style.opacity = '1';
    }, 10);

    event.target._tooltip = tooltip;
}

// Hide Tooltip
function hideTooltip(event) {
    if (event.target._tooltip) {
        event.target._tooltip.remove();
        delete event.target._tooltip;
    }
}

// Initialize Animations
function initializeAnimations() {
    // Animate cards on load
    const cards = document.querySelectorAll('.summary-card, .tool-card, .table-container');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';

        setTimeout(() => {
            card.style.transition = 'all 0.6s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Add hover effects to table rows
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('mouseenter', function () {
            this.style.transform = 'translateX(4px)';
        });

        row.addEventListener('mouseleave', function () {
            this.style.transform = 'translateX(0)';
        });
    });
}

// Initialize Modals
function initializeModals() {
    // Create report preview modal
    const reportPreview = document.createElement('div');
    reportPreview.className = 'report-preview';
    reportPreview.innerHTML = `
        <div class="report-preview-content">
            <div class="report-preview-header">
                <h3>Aperçu du rapport</h3>
                <button class="report-preview-close">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="report-preview-body">
                <p>Contenu du rapport...</p>
            </div>
        </div>
    `;

    document.body.appendChild(reportPreview);

    // Close modal functionality
    const closeBtn = reportPreview.querySelector('.report-preview-close');
    closeBtn.addEventListener('click', () => {
        reportPreview.classList.remove('active');
    });

    // Close on background click
    reportPreview.addEventListener('click', (e) => {
        if (e.target === reportPreview) {
            reportPreview.classList.remove('active');
        }
    });
}

// Modal Functions
function showReportModal(row) {
    const modal = document.querySelector('.report-preview');
    if (modal) {
        modal.classList.add('active');
    }
}

function showAnalysisModal(row) {
    const modal = document.querySelector('.report-preview');
    if (modal) {
        const header = modal.querySelector('.report-preview-header h3');
        const body = modal.querySelector('.report-preview-body');

        header.textContent = 'Aperçu de l\'analyse stratégique';
        body.innerHTML = '<p>Contenu de l\'analyse stratégique...</p>';

        modal.classList.add('active');
    }
}

function showExecutiveModal(row) {
    const modal = document.querySelector('.report-preview');
    if (modal) {
        const header = modal.querySelector('.report-preview-header h3');
        const body = modal.querySelector('.report-preview-body');

        header.textContent = 'Aperçu du rapport exécutif';
        body.innerHTML = '<p>Contenu du rapport exécutif...</p>';

        modal.classList.add('active');
    }
}

function showPresentationModal(row) {
    const modal = document.querySelector('.report-preview');
    if (modal) {
        const header = modal.querySelector('.report-preview-header h3');
        const body = modal.querySelector('.report-preview-body');

        header.textContent = 'Présentation exécutive';
        body.innerHTML = '<p>Contenu de la présentation...</p>';

        modal.classList.add('active');
    }
}

function showProgressModal(row) {
    showNotification('Affichage de la progression...', 'info');
    // Simulate showing progress modal
}

// Show Loading
function showLoading(button, text) {
    button.disabled = true;
    button.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${text}`;
    button.classList.add('generating');
}

// Hide Loading
function hideLoading(button, originalText) {
    button.disabled = false;
    button.innerHTML = `<i class="fas fa-chart-pie"></i> ${originalText}`;
    button.classList.remove('generating');
    button.classList.add('success-animation');

    setTimeout(() => {
        button.classList.remove('success-animation');
    }, 500);
}

// Show Notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    const styles = {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '12px 20px',
        borderRadius: '8px',
        color: 'white',
        fontWeight: '600',
        zIndex: '10000',
        opacity: '0',
        transform: 'translateX(100%)',
        transition: 'all 0.3s ease',
        maxWidth: '300px',
        wordWrap: 'break-word'
    };

    // Colors according to type
    switch (type) {
        case 'success':
            styles.backgroundColor = '#38a169';
            break;
        case 'error':
            styles.backgroundColor = '#e53e3e';
            break;
        case 'warning':
            styles.backgroundColor = '#dd6b20';
            break;
        default:
            styles.backgroundColor = '#3182ce';
    }

    Object.assign(notification.style, styles);

    document.body.appendChild(notification);

    // Animation d'entrée
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    }, 10);

    // Suppression automatique
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Export Functions
function exportAllAnnualReports() {
    showNotification('Export de tous les rapports annuels...', 'info');

    // Simulation d'export
    setTimeout(() => {
        showNotification('Export terminé avec succès', 'success');
    }, 2000);
}

// Refresh Data
function refreshData() {
    showNotification('Actualisation des données...', 'info');

    // Animation de rafraîchissement
    const tableContainers = document.querySelectorAll('.table-container');
    tableContainers.forEach(container => {
        container.classList.add('loading');
    });

    setTimeout(() => {
        tableContainers.forEach(container => {
            container.classList.remove('loading');
        });
        showNotification('Données actualisées', 'success');
    }, 1000);
}

// Add CSS for animations and tooltips
const style = document.createElement('style');
style.textContent = `
    .tooltip {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    .generating {
        animation: pulse 1s infinite;
    }
    
    .success-animation {
        animation: checkmark 0.5s ease-in-out;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    @keyframes checkmark {
        0% { transform: scale(0); }
        50% { transform: scale(1.2); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(style);

// Export functions to global scope
window.RapportsAnnuels = {
    exportAllAnnualReports,
    refreshData,
    showNotification,
    handleAction,
    generateAnnualReport,
    generateComparison,
    analyzeStrategicTrends,
    evaluatePerformance,
    createExecutiveReport,
    createPresentation
};
