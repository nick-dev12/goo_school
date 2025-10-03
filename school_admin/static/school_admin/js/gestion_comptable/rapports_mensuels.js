// Rapports Mensuels JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeReportTools();
    initializeAnalysisTools();
    initializeCustomTools();
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

// Initialize Report Tools
function initializeReportTools() {
    // Generate Report
    const generateReportBtn = document.getElementById('generateReport');
    if (generateReportBtn) {
        generateReportBtn.addEventListener('click', function () {
            generateReport();
        });
    }

    // Generate Comparison
    const generateComparisonBtn = document.getElementById('generateComparison');
    if (generateComparisonBtn) {
        generateComparisonBtn.addEventListener('click', function () {
            generateComparison();
        });
    }

    // Generate Monthly Report (header button)
    const generateMonthlyReportBtn = document.getElementById('generateMonthlyReport');
    if (generateMonthlyReportBtn) {
        generateMonthlyReportBtn.addEventListener('click', function () {
            generateMonthlyReport();
        });
    }
}

// Generate Report
function generateReport() {
    const button = document.getElementById('generateReport');
    const period = document.getElementById('reportPeriod').value;
    const type = document.getElementById('reportType').value;

    showLoading(button, 'Génération en cours...');

    // Simulate report generation
    setTimeout(() => {
        const results = simulateReportGeneration(period, type);
        showReportResults(results);
        hideLoading(button, 'Générer le rapport');
        showNotification('Rapport généré avec succès', 'success');
        updateReportsTable();
    }, 3000);
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
    }, 2500);
}

// Generate Monthly Report
function generateMonthlyReport() {
    const button = document.getElementById('generateMonthlyReport');
    showLoading(button, 'Génération en cours...');

    // Simulate monthly report generation
    setTimeout(() => {
        hideLoading(button, 'Nouveau rapport');
        showNotification('Rapport mensuel généré avec succès', 'success');
        updateReportsTable();
    }, 2000);
}

// Initialize Analysis Tools
function initializeAnalysisTools() {
    // Analyze Trends
    const analyzeTrendsBtn = document.getElementById('analyzeTrends');
    if (analyzeTrendsBtn) {
        analyzeTrendsBtn.addEventListener('click', function () {
            analyzeTrends();
        });
    }

    // Compare Establishments
    const compareEstablishmentsBtn = document.getElementById('compareEstablishments');
    if (compareEstablishmentsBtn) {
        compareEstablishmentsBtn.addEventListener('click', function () {
            compareEstablishments();
        });
    }
}

// Analyze Trends
function analyzeTrends() {
    const button = document.getElementById('analyzeTrends');
    const period = document.getElementById('analysisPeriod').value;

    showLoading(button, 'Analyse en cours...');

    // Simulate trend analysis
    setTimeout(() => {
        const results = simulateTrendAnalysis(period);
        showAnalysisResults(results);
        hideLoading(button, 'Analyser les tendances');
        showNotification('Analyse des tendances terminée', 'success');
        updateAnalysisTable();
    }, 2800);
}

// Compare Establishments
function compareEstablishments() {
    const button = document.getElementById('compareEstablishments');

    showLoading(button, 'Comparaison en cours...');

    // Simulate establishment comparison
    setTimeout(() => {
        const results = simulateEstablishmentComparison();
        showComparisonResults(results);
        hideLoading(button, 'Comparer les établissements');
        showNotification('Comparaison des établissements terminée', 'success');
        updateAnalysisTable();
    }, 2200);
}

// Initialize Custom Tools
function initializeCustomTools() {
    // Create Custom Report
    const createCustomReportBtn = document.getElementById('createCustomReport');
    if (createCustomReportBtn) {
        createCustomReportBtn.addEventListener('click', function () {
            createCustomReport();
        });
    }

    // Use Template
    const useTemplateBtn = document.getElementById('useTemplate');
    if (useTemplateBtn) {
        useTemplateBtn.addEventListener('click', function () {
            useTemplate();
        });
    }
}

// Create Custom Report
function createCustomReport() {
    const button = document.getElementById('createCustomReport');
    const name = document.getElementById('reportName').value;
    const description = document.getElementById('reportDescription').value;
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const frequency = document.getElementById('generationFrequency').value;

    if (!name || !startDate || !endDate) {
        showNotification('Veuillez remplir tous les champs obligatoires', 'error');
        return;
    }

    showLoading(button, 'Création en cours...');

    // Simulate custom report creation
    setTimeout(() => {
        const results = simulateCustomReportCreation(name, description, startDate, endDate, frequency);
        showCustomReportResults(results);
        hideLoading(button, 'Créer le rapport');
        showNotification('Rapport personnalisé créé avec succès', 'success');
        updateCustomReportsTable();
    }, 2000);
}

// Use Template
function useTemplate() {
    const button = document.getElementById('useTemplate');
    const template = document.getElementById('reportTemplate').value;

    showLoading(button, 'Configuration en cours...');

    // Simulate template usage
    setTimeout(() => {
        const results = simulateTemplateUsage(template);
        showTemplateResults(results);
        hideLoading(button, 'Utiliser le modèle');
        showNotification('Modèle configuré avec succès', 'success');
    }, 1500);
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
        'Voir rapport': () => viewReport(row),
        'Télécharger PDF': () => downloadPDF(row),
        'Partager': () => shareReport(row),
        'Dupliquer': () => duplicateReport(row),
        'Voir analyse': () => viewAnalysis(row),
        'Télécharger': () => downloadAnalysis(row),
        'Modifier': () => editReport(row),
        'Supprimer': () => deleteReport(row),
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
    showNotification('Ouverture du rapport...', 'info');
    // Simulate opening report in modal
    setTimeout(() => {
        showReportModal(row);
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
        updateReportsTable();
    }, 800);
}

function viewAnalysis(row) {
    showNotification('Ouverture de l\'analyse...', 'info');
    setTimeout(() => {
        showAnalysisModal(row);
    }, 500);
}

function downloadAnalysis(row) {
    showNotification('Téléchargement de l\'analyse...', 'info');
    setTimeout(() => {
        showNotification('Analyse téléchargée avec succès', 'success');
    }, 1000);
}

function editReport(row) {
    showNotification('Modification du rapport...', 'info');
    setTimeout(() => {
        showEditModal(row);
    }, 500);
}

function deleteReport(row) {
    if (confirm('Êtes-vous sûr de vouloir supprimer ce rapport ?')) {
        showNotification('Suppression du rapport...', 'info');
        setTimeout(() => {
            row.remove();
            showNotification('Rapport supprimé avec succès', 'success');
        }, 1000);
    }
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
function simulateReportGeneration(period, type) {
    return {
        period: period,
        type: type,
        status: 'generated',
        size: '2.4 MB',
        date: new Date().toLocaleDateString('fr-FR')
    };
}

function simulateComparisonGeneration(period) {
    return {
        period: period,
        type: 'comparison',
        status: 'completed',
        insights: [
            'Croissance de 15.2% par rapport au mois précédent',
            'Meilleure performance: Lycée du Plateau',
            'Taux de paiement en hausse de 8%'
        ]
    };
}

function simulateTrendAnalysis(period) {
    return {
        period: period,
        type: 'trends',
        status: 'completed',
        trends: [
            'Tendance positive sur 6 mois',
            'Pic de croissance en décembre',
            'Stabilisation prévue pour janvier'
        ]
    };
}

function simulateEstablishmentComparison() {
    return {
        type: 'comparison',
        status: 'completed',
        rankings: [
            { name: 'Lycée du Plateau', score: 95 },
            { name: 'École Primaire La Savane', score: 88 },
            { name: 'Maternelle Les Gazelles', score: 82 }
        ]
    };
}

function simulateCustomReportCreation(name, description, startDate, endDate, frequency) {
    return {
        name: name,
        description: description,
        startDate: startDate,
        endDate: endDate,
        frequency: frequency,
        status: 'created'
    };
}

function simulateTemplateUsage(template) {
    return {
        template: template,
        status: 'configured',
        customization: 'applied'
    };
}

// Show Results Functions
function showReportResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'report-results';

    resultDiv.innerHTML = `
        <h4><i class="fas fa-check-circle"></i> Rapport généré avec succès</h4>
        <p>Période: ${results.period}</p>
        <p>Type: ${results.type}</p>
        <p>Taille: ${results.size}</p>
        <p>Date: ${results.date}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.report-form, .comparison-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 5 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 5000);
    }
}

function showComparisonResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'info-message';

    let content = `
        <h4><i class="fas fa-chart-pie"></i> Analyse comparative terminée</h4>
        <p>Période: ${results.period}</p>
        <p>Type: ${results.type}</p>
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

        // Remove after 8 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 8000);
    }
}

function showAnalysisResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'success-message';

    let content = `
        <h4><i class="fas fa-chart-line"></i> Analyse des tendances terminée</h4>
        <p>Période: ${results.period}</p>
        <p>Type: ${results.type}</p>
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
    const forms = document.querySelectorAll('.analysis-form');
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

function showCustomReportResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'success-message';

    resultDiv.innerHTML = `
        <h4><i class="fas fa-cog"></i> Rapport personnalisé créé</h4>
        <p>Nom: ${results.name}</p>
        <p>Description: ${results.description}</p>
        <p>Période: ${results.startDate} - ${results.endDate}</p>
        <p>Fréquence: ${results.frequency}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.custom-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 5 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 5000);
    }
}

function showTemplateResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'info-message';

    resultDiv.innerHTML = `
        <h4><i class="fas fa-template"></i> Modèle configuré</h4>
        <p>Modèle: ${results.template}</p>
        <p>Personnalisation: ${results.customization}</p>
    `;

    // Insert after the form
    const forms = document.querySelectorAll('.template-form');
    if (forms.length > 0) {
        forms[0].parentNode.insertBefore(resultDiv, forms[0].nextSibling);

        // Remove after 5 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 5000);
    }
}

// Update Tables
function updateReportsTable() {
    // Simulate adding new report to table
    const tbody = document.querySelector('#bilan-mensuel .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="period-info">
                    <h4>${new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })}</h4>
                    <p>Rapport généré automatiquement</p>
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
                <span class="file-size">2.4 MB</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir rapport">
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

function updateAnalysisTable() {
    // Simulate adding new analysis to table
    const tbody = document.querySelector('#analyse-financiere .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="analysis-info">
                    <h4>Nouvelle analyse - ${new Date().toLocaleDateString('fr-FR')}</h4>
                    <p>Analyse générée automatiquement</p>
                </div>
            </td>
            <td>
                <span class="analysis-type tendances">Tendances</span>
            </td>
            <td>
                <span class="period">${new Date().toLocaleDateString('fr-FR')}</span>
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

function updateCustomReportsTable() {
    // Simulate adding new custom report to table
    const tbody = document.querySelector('#rapports-personnalises .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="custom-info">
                    <h4>Nouveau rapport personnalisé</h4>
                    <p>Rapport créé automatiquement</p>
                </div>
            </td>
            <td>
                <span class="custom-type executif">Exécutif</span>
            </td>
            <td>
                <span class="frequency">Mensuel</span>
            </td>
            <td>
                <span class="date">${new Date().toLocaleDateString('fr-FR')}</span>
            </td>
            <td>
                <span class="status-badge actif">Actif</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir rapport">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Modifier">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn-action" title="Dupliquer">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button class="btn-action" title="Supprimer">
                        <i class="fas fa-trash"></i>
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

        header.textContent = 'Aperçu de l\'analyse';
        body.innerHTML = '<p>Contenu de l\'analyse...</p>';

        modal.classList.add('active');
    }
}

function showEditModal(row) {
    showNotification('Ouverture de l\'éditeur...', 'info');
    // Simulate opening edit modal
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
    button.innerHTML = `<i class="fas fa-plus"></i> ${originalText}`;
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
function exportAllReports() {
    showNotification('Export de tous les rapports...', 'info');

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
window.RapportsMensuels = {
    exportAllReports,
    refreshData,
    showNotification,
    handleAction,
    generateReport,
    generateComparison,
    analyzeTrends,
    compareEstablishments,
    createCustomReport,
    useTemplate
};
