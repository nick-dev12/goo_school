// Détails Financiers Établissement JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeActions();
    initializeCharts();
    initializeAnimations();
    initializeTooltips();
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

// Initialize Actions
function initializeActions() {
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
        'Voir détails': () => viewDetails(row),
        'Télécharger reçu': () => downloadReceipt(row),
        'Voir facture': () => viewInvoice(row),
        'Télécharger PDF': () => downloadPDF(row),
        'Envoyer': () => sendInvoice(row),
        'Marquer comme payée': () => markAsPaid(row),
        'Télécharger': () => downloadDocument(row),
        'Voir': () => viewDocument(row)
    };

    if (actions[action]) {
        actions[action]();
    } else {
        showNotification(`Action "${action}" non implémentée`, 'info');
    }
}

// Action Functions
function viewDetails(row) {
    showNotification('Ouverture des détails...', 'info');
    setTimeout(() => {
        showDetailsModal(row);
    }, 500);
}

function downloadReceipt(row) {
    showNotification('Téléchargement du reçu...', 'info');
    setTimeout(() => {
        showNotification('Reçu téléchargé avec succès', 'success');
    }, 1000);
}

function viewInvoice(row) {
    showNotification('Ouverture de la facture...', 'info');
    setTimeout(() => {
        showInvoiceModal(row);
    }, 500);
}

function downloadPDF(row) {
    showNotification('Téléchargement du PDF...', 'info');
    setTimeout(() => {
        showNotification('PDF téléchargé avec succès', 'success');
    }, 1000);
}

function sendInvoice(row) {
    showNotification('Envoi de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture envoyée avec succès', 'success');
    }, 1500);
}

function markAsPaid(row) {
    if (confirm('Êtes-vous sûr de vouloir marquer cette facture comme payée ?')) {
        showNotification('Marquage comme payée...', 'info');
        setTimeout(() => {
            updateInvoiceStatus(row, 'paye');
            showNotification('Facture marquée comme payée', 'success');
        }, 1000);
    }
}

function downloadDocument(row) {
    showNotification('Téléchargement du document...', 'info');
    setTimeout(() => {
        showNotification('Document téléchargé avec succès', 'success');
    }, 1000);
}

function viewDocument(row) {
    showNotification('Ouverture du document...', 'info');
    setTimeout(() => {
        showDocumentModal(row);
    }, 500);
}

// Initialize Charts
function initializeCharts() {
    const chartPeriod = document.getElementById('chartPeriod');
    if (chartPeriod) {
        chartPeriod.addEventListener('change', function () {
            updateChart(this.value);
        });
    }
}

// Update Chart
function updateChart(period) {
    showNotification(`Mise à jour du graphique pour ${period}...`, 'info');

    // Simulate chart update
    setTimeout(() => {
        showNotification('Graphique mis à jour', 'success');
    }, 1000);
}

// Global Functions
function goBack() {
    if (window.history.length > 1) {
        window.history.back();
    } else {
        window.location.href = '/comptable/gestion_etablissements/';
    }
}

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

function exportData() {
    showNotification('Export des données...', 'info');
    setTimeout(() => {
        showNotification('Données exportées avec succès', 'success');
    }, 2000);
}

function generateInvoice() {
    showNotification('Génération de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture générée avec succès', 'success');
        updateInvoicesTable();
    }, 2000);
}

function addPayment() {
    showNotification('Ouverture du formulaire de paiement...', 'info');
    setTimeout(() => {
        showPaymentModal();
    }, 500);
}

function generateNewInvoice() {
    showNotification('Génération d\'une nouvelle facture...', 'info');
    setTimeout(() => {
        showNotification('Nouvelle facture générée', 'success');
        updateInvoicesTable();
    }, 2000);
}

function generateReport() {
    showNotification('Génération du rapport...', 'info');
    setTimeout(() => {
        showNotification('Rapport généré avec succès', 'success');
    }, 2000);
}

function uploadDocument() {
    showNotification('Ouverture du formulaire de téléchargement...', 'info');
    setTimeout(() => {
        showUploadModal();
    }, 500);
}

// Update Invoice Status
function updateInvoiceStatus(row, status) {
    const statusBadge = row.querySelector('.status-badge');
    if (statusBadge) {
        statusBadge.className = `status-badge ${status}`;

        const statusTexts = {
            'paye': 'Payée',
            'partiel': 'Paiement partiel',
            'impaye': 'Impayée'
        };

        statusBadge.textContent = statusTexts[status] || status;
    }
}

// Update Invoices Table
function updateInvoicesTable() {
    const tbody = document.querySelector('#factures .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <div class="invoice-info">
                    <h4>FAC-2024-${String(Math.floor(Math.random() * 1000) + 1).padStart(3, '0')}</h4>
                    <p>${new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })}</p>
                </div>
            </td>
            <td><span class="period">${new Date().toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' })}</span></td>
            <td><span class="amount">${(Math.random() * 1000000 + 500000).toLocaleString()} FCFA</span></td>
            <td><span class="status-badge impaye">Impayée</span></td>
            <td><span class="date">${new Date().toLocaleDateString('fr-FR')}</span></td>
            <td><span class="date">${new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toLocaleDateString('fr-FR')}</span></td>
            <td>
                <div class="action-buttons">
                    <button class="btn-action" title="Voir facture">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-action" title="Télécharger PDF">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn-action" title="Envoyer">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.insertBefore(newRow, tbody.firstChild);

        // Add event listeners to new buttons
        initializeActions();
    }
}

// Modal Functions
function showDetailsModal(row) {
    showNotification('Ouverture des détails du paiement...', 'info');
    // Simulate showing details modal
}

function showInvoiceModal(row) {
    showNotification('Ouverture de la facture...', 'info');
    // Simulate showing invoice modal
}

function showDocumentModal(row) {
    showNotification('Ouverture du document...', 'info');
    // Simulate showing document modal
}

function showPaymentModal() {
    showNotification('Ouverture du formulaire de paiement...', 'info');
    // Simulate showing payment modal
}

function showUploadModal() {
    showNotification('Ouverture du formulaire de téléchargement...', 'info');
    // Simulate showing upload modal
}

// Initialize Animations
function initializeAnimations() {
    // Animate cards on load
    const cards = document.querySelectorAll('.overview-card, .chart-card, .document-card, .summary-card');
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

    // Add hover effects to document cards
    const documentCards = document.querySelectorAll('.document-card');
    documentCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-2px)';
        });

        card.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0)';
        });
    });
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

// Add CSS for animations and tooltips
const style = document.createElement('style');
style.textContent = `
    .tooltip {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    .success-animation {
        animation: successPulse 0.6s ease-in-out;
    }
    
    @keyframes successPulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(style);

// Export functions to global scope
window.DetailsFinanciersEtablissement = {
    goBack,
    refreshData,
    exportData,
    generateInvoice,
    addPayment,
    generateNewInvoice,
    generateReport,
    uploadDocument,
    showNotification,
    handleAction,
    updateChart
};
