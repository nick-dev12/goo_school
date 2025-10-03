// Calculs Automatiques JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeCalculationTools();
    initializeInvoiceTools();
    initializeReportTools();
    initializeTableActions();
    initializeTooltips();
    initializeAnimations();
    initializeBulkActions();
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

// Initialize Calculation Tools
function initializeCalculationTools() {
    // Calculate Revenus
    const calculateRevenusBtn = document.getElementById('calculateRevenus');
    if (calculateRevenusBtn) {
        calculateRevenusBtn.addEventListener('click', function () {
            calculateRevenus();
        });
    }

    // Calculate Taxes
    const calculateTaxesBtn = document.getElementById('calculateTaxes');
    if (calculateTaxesBtn) {
        calculateTaxesBtn.addEventListener('click', function () {
            calculateTaxes();
        });
    }

    // Calculate Salaries
    const calculateSalariesBtn = document.getElementById('calculateSalaries');
    if (calculateSalariesBtn) {
        calculateSalariesBtn.addEventListener('click', function () {
            calculateSalaries();
        });
    }

    // Run All Calculations
    const runAllCalculationsBtn = document.getElementById('runAllCalculations');
    if (runAllCalculationsBtn) {
        runAllCalculationsBtn.addEventListener('click', function () {
            runAllCalculations();
        });
    }
}

// Calculate Revenus
function calculateRevenus() {
    const button = document.getElementById('calculateRevenus');
    const period = document.getElementById('calculationPeriod').value;
    const tarifEleve = parseFloat(document.getElementById('tarifEleve').value);

    showLoading(button, 'Calcul en cours...');

    // Simulate calculation
    setTimeout(() => {
        const results = simulateRevenusCalculation(period, tarifEleve);
        showCalculationResults(results);
        hideLoading(button, 'Lancer le calcul');
        showNotification('Calcul des revenus terminé', 'success');
    }, 2000);
}

// Calculate Taxes
function calculateTaxes() {
    const button = document.getElementById('calculateTaxes');
    const tvaRate = parseFloat(document.getElementById('tvaRate').value);
    const chargesRate = parseFloat(document.getElementById('chargesRate').value);
    const baseAmount = parseFloat(document.getElementById('baseAmount').value);

    showLoading(button, 'Calcul en cours...');

    // Simulate calculation
    setTimeout(() => {
        const results = simulateTaxesCalculation(tvaRate, chargesRate, baseAmount);
        showCalculationResults(results);
        hideLoading(button, 'Calculer les taxes');
        showNotification('Calcul des taxes terminé', 'success');
    }, 1500);
}

// Calculate Salaries
function calculateSalaries() {
    const button = document.getElementById('calculateSalaries');
    const period = document.getElementById('salaryPeriod').value;
    const overtimeHours = parseFloat(document.getElementById('overtimeHours').value);
    const bonusAmount = parseFloat(document.getElementById('bonusAmount').value);

    showLoading(button, 'Calcul en cours...');

    // Simulate calculation
    setTimeout(() => {
        const results = simulateSalariesCalculation(period, overtimeHours, bonusAmount);
        showCalculationResults(results);
        hideLoading(button, 'Calculer les salaires');
        showNotification('Calcul des salaires terminé', 'success');
    }, 1800);
}

// Run All Calculations
function runAllCalculations() {
    const button = document.getElementById('runAllCalculations');
    showLoading(button, 'Calculs en cours...');

    // Simulate running all calculations
    setTimeout(() => {
        hideLoading(button, 'Lancer tous les calculs');
        showNotification('Tous les calculs ont été exécutés avec succès', 'success');

        // Update table with new results
        updateCalculationTable();
    }, 3000);
}

// Simulate Revenus Calculation
function simulateRevenusCalculation(period, tarifEleve) {
    const establishments = [
        { name: 'Maternelle Les Gazelles', students: 500 },
        { name: 'Lycée du Plateau', students: 520 },
        { name: 'École Primaire La Savane', students: 2350 }
    ];

    const results = establishments.map(est => ({
        name: est.name,
        students: est.students,
        baseAmount: est.students * tarifEleve,
        tva: (est.students * tarifEleve) * 0.18,
        charges: (est.students * tarifEleve) * 0.05,
        total: (est.students * tarifEleve) * 1.23
    }));

    return {
        type: 'revenus',
        period: period,
        results: results,
        total: results.reduce((sum, r) => sum + r.total, 0)
    };
}

// Simulate Taxes Calculation
function simulateTaxesCalculation(tvaRate, chargesRate, baseAmount) {
    const tva = (baseAmount * tvaRate) / 100;
    const charges = (baseAmount * chargesRate) / 100;
    const total = baseAmount + tva + charges;

    return {
        type: 'taxes',
        baseAmount: baseAmount,
        tva: tva,
        charges: charges,
        total: total
    };
}

// Simulate Salaries Calculation
function simulateSalariesCalculation(period, overtimeHours, bonusAmount) {
    const baseSalary = 2500000; // Base salary for all employees
    const overtimeRate = 5000; // Per hour
    const overtimeAmount = overtimeHours * overtimeRate;
    const total = baseSalary + overtimeAmount + bonusAmount;

    return {
        type: 'salaries',
        period: period,
        baseSalary: baseSalary,
        overtimeAmount: overtimeAmount,
        bonusAmount: bonusAmount,
        total: total
    };
}

// Show Calculation Results
function showCalculationResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'calculation-results';

    let content = '';
    if (results.type === 'revenus') {
        content = `
            <h4><i class="fas fa-check-circle"></i> Calcul des revenus terminé</h4>
            <p>Période: ${results.period}</p>
            <p>Total calculé: ${formatCurrency(results.total)} FCFA</p>
            <p>${results.results.length} établissements traités</p>
        `;
    } else if (results.type === 'taxes') {
        content = `
            <h4><i class="fas fa-check-circle"></i> Calcul des taxes terminé</h4>
            <p>Montant de base: ${formatCurrency(results.baseAmount)} FCFA</p>
            <p>TVA: ${formatCurrency(results.tva)} FCFA</p>
            <p>Charges: ${formatCurrency(results.charges)} FCFA</p>
            <p>Total: ${formatCurrency(results.total)} FCFA</p>
        `;
    } else if (results.type === 'salaries') {
        content = `
            <h4><i class="fas fa-check-circle"></i> Calcul des salaires terminé</h4>
            <p>Période: ${results.period}</p>
            <p>Salaire de base: ${formatCurrency(results.baseSalary)} FCFA</p>
            <p>Heures supplémentaires: ${formatCurrency(results.overtimeAmount)} FCFA</p>
            <p>Primes: ${formatCurrency(results.bonusAmount)} FCFA</p>
            <p>Total: ${formatCurrency(results.total)} FCFA</p>
        `;
    }

    resultDiv.innerHTML = content;

    // Insert after the calculation form
    const forms = document.querySelectorAll('.calculation-form, .invoice-form, .email-form, .report-form');
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

// Initialize Invoice Tools
function initializeInvoiceTools() {
    const generateInvoicesBtn = document.getElementById('generateInvoices');
    if (generateInvoicesBtn) {
        generateInvoicesBtn.addEventListener('click', function () {
            generateInvoices();
        });
    }

    const sendInvoicesBtn = document.getElementById('sendInvoices');
    if (sendInvoicesBtn) {
        sendInvoicesBtn.addEventListener('click', function () {
            sendInvoices();
        });
    }
}

// Generate Invoices
function generateInvoices() {
    const button = document.getElementById('generateInvoices');
    const template = document.getElementById('invoiceTemplate').value;
    const dueDate = document.getElementById('dueDate').value;

    showLoading(button, 'Génération en cours...');

    // Simulate invoice generation
    setTimeout(() => {
        hideLoading(button, 'Générer les factures');
        showNotification('Factures générées avec succès', 'success');
        updateInvoiceTable();
    }, 2000);
}

// Send Invoices
function sendInvoices() {
    const button = document.getElementById('sendInvoices');
    const template = document.getElementById('emailTemplate').value;
    const subject = document.getElementById('emailSubject').value;

    showLoading(button, 'Envoi en cours...');

    // Simulate sending
    setTimeout(() => {
        hideLoading(button, 'Envoyer les factures');
        showNotification('Factures envoyées avec succès', 'success');
    }, 2500);
}

// Initialize Report Tools
function initializeReportTools() {
    const generateMonthlyReportBtn = document.getElementById('generateMonthlyReport');
    if (generateMonthlyReportBtn) {
        generateMonthlyReportBtn.addEventListener('click', function () {
            generateMonthlyReport();
        });
    }

    const generatePerformanceReportBtn = document.getElementById('generatePerformanceReport');
    if (generatePerformanceReportBtn) {
        generatePerformanceReportBtn.addEventListener('click', function () {
            generatePerformanceReport();
        });
    }
}

// Generate Monthly Report
function generateMonthlyReport() {
    const button = document.getElementById('generateMonthlyReport');
    const period = document.getElementById('reportPeriod').value;

    showLoading(button, 'Génération en cours...');

    // Simulate report generation
    setTimeout(() => {
        hideLoading(button, 'Générer le rapport');
        showNotification('Rapport mensuel généré avec succès', 'success');
        updateReportTable();
    }, 3000);
}

// Generate Performance Report
function generatePerformanceReport() {
    const button = document.getElementById('generatePerformanceReport');
    const period = document.getElementById('analysisPeriod').value;

    showLoading(button, 'Analyse en cours...');

    // Simulate performance analysis
    setTimeout(() => {
        hideLoading(button, 'Analyser la performance');
        showNotification('Rapport de performance généré avec succès', 'success');
        updateReportTable();
    }, 2500);
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
        'Voir détails': () => showDetails(row),
        'Recalculer': () => recalculate(row),
        'Générer facture': () => generateInvoice(row),
        'Voir facture': () => viewInvoice(row),
        'Télécharger': () => downloadInvoice(row),
        'Renvoyer': () => resendInvoice(row),
        'Marquer payée': () => markAsPaid(row),
        'Voir rapport': () => viewReport(row),
        'Télécharger PDF': () => downloadPDF(row),
        'Partager': () => shareReport(row)
    };

    if (actions[action]) {
        actions[action]();
    } else {
        showNotification(`Action "${action}" non implémentée`, 'info');
    }
}

// Action Functions
function showDetails(row) {
    showNotification('Affichage des détails', 'info');
}

function recalculate(row) {
    showNotification('Recalcul en cours...', 'info');
    setTimeout(() => {
        showNotification('Recalcul terminé', 'success');
    }, 1500);
}

function generateInvoice(row) {
    showNotification('Génération de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture générée', 'success');
    }, 1000);
}

function viewInvoice(row) {
    showNotification('Ouverture de la facture', 'info');
}

function downloadInvoice(row) {
    showNotification('Téléchargement de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture téléchargée', 'success');
    }, 1000);
}

function resendInvoice(row) {
    showNotification('Renvoi de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture renvoyée', 'success');
    }, 1000);
}

function markAsPaid(row) {
    showNotification('Facture marquée comme payée', 'success');
    const statusBadge = row.querySelector('.status-badge');
    if (statusBadge) {
        statusBadge.className = 'status-badge paye';
        statusBadge.textContent = 'Payée';
    }
}

function viewReport(row) {
    showNotification('Ouverture du rapport', 'info');
}

function downloadPDF(row) {
    showNotification('Téléchargement du PDF...', 'info');
    setTimeout(() => {
        showNotification('PDF téléchargé', 'success');
    }, 1000);
}

function shareReport(row) {
    showNotification('Partage du rapport...', 'info');
    setTimeout(() => {
        showNotification('Rapport partagé', 'success');
    }, 1000);
}

// Initialize Bulk Actions
function initializeBulkActions() {
    // Add bulk action functionality if needed
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

// Show Loading
function showLoading(button, text) {
    button.disabled = true;
    button.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${text}`;
    button.classList.add('calculating');
}

// Hide Loading
function hideLoading(button, originalText) {
    button.disabled = false;
    button.innerHTML = `<i class="fas fa-play"></i> ${originalText}`;
    button.classList.remove('calculating');
    button.classList.add('success-animation');

    setTimeout(() => {
        button.classList.remove('success-animation');
    }, 500);
}

// Update Calculation Table
function updateCalculationTable() {
    // Simulate table update with new calculation results
    const rows = document.querySelectorAll('#calculs-mensuels .data-table tbody tr');
    rows.forEach(row => {
        const statusBadge = row.querySelector('.status-badge');
        if (statusBadge && statusBadge.textContent === 'En cours') {
            statusBadge.className = 'status-badge calcule';
            statusBadge.textContent = 'Calculé';
        }
    });
}

// Update Invoice Table
function updateInvoiceTable() {
    // Simulate adding new invoice to table
    const tbody = document.querySelector('#facturation .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <span class="invoice-number">FAC-2023-003</span>
            </td>
            <td>
                <div class="etablissement-info">
                    <div class="etablissement-avatar">
                        <i class="fas fa-school"></i>
                    </div>
                    <div>
                        <h4>Nouvel Établissement</h4>
                        <p>Abidjan, Côte d'Ivoire</p>
                    </div>
                </div>
            </td>
            <td>
                <span class="amount">2,500,000 FCFA</span>
            </td>
            <td>
                <span class="date">${new Date().toLocaleDateString('fr-FR')}</span>
            </td>
            <td>
                <span class="status-badge envoye">Envoyée</span>
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir facture">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Télécharger">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn-action" title="Renvoyer">
                        <i class="fas fa-redo"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(newRow);

        // Add event listeners to new buttons
        initializeTableActions();
    }
}

// Update Report Table
function updateReportTable() {
    // Simulate adding new report to table
    const tbody = document.querySelector('#rapports .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="report-info">
                    <h4>Nouveau Rapport - ${new Date().toLocaleDateString('fr-FR')}</h4>
                    <p>Rapport généré automatiquement</p>
                </div>
            </td>
            <td>
                <span class="report-type mensuel">Mensuel</span>
            </td>
            <td>
                <span class="period">${new Date().toLocaleDateString('fr-FR')}</span>
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
                    <button class="btn-action" title="Télécharger PDF">
                        <i class="fas fa-file-pdf"></i>
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

// Format Currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('fr-FR').format(amount);
}

// Export Functions
function exportCalculations(format = 'excel') {
    showNotification(`Export ${format.toUpperCase()} en cours...`, 'info');

    // Simulation d'export
    setTimeout(() => {
        showNotification(`Export ${format.toUpperCase()} terminé`, 'success');
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
    
    .calculating {
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
window.CalculsAutomatiques = {
    exportCalculations,
    refreshData,
    showNotification,
    handleAction,
    calculateRevenus,
    calculateTaxes,
    calculateSalaries,
    runAllCalculations
};
