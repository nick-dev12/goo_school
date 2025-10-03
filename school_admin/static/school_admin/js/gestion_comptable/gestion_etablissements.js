// Gestion des Établissements JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeSearch();
    initializeFilters();
    initializeCheckboxes();
    initializeActions();
    initializeInvoiceTools();
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

// Initialize Search
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            const searchTerm = this.value.toLowerCase();
            filterTableRows(searchTerm);
        });
    }
}

// Initialize Filters
function initializeFilters() {
    const statusFilter = document.getElementById('statusFilter');
    const typeFilter = document.getElementById('typeFilter');

    if (statusFilter) {
        statusFilter.addEventListener('change', function () {
            applyFilters();
        });
    }

    if (typeFilter) {
        typeFilter.addEventListener('change', function () {
            applyFilters();
        });
    }
}

// Filter Table Rows
function filterTableRows(searchTerm) {
    const activeTab = document.querySelector('.tab-panel.active');
    if (!activeTab) return;

    const rows = activeTab.querySelectorAll('tbody tr');

    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const matchesSearch = text.includes(searchTerm);

        if (matchesSearch) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Apply Filters
function applyFilters() {
    const statusFilter = document.getElementById('statusFilter').value;
    const typeFilter = document.getElementById('typeFilter').value;
    const activeTab = document.querySelector('.tab-panel.active');

    if (!activeTab) return;

    const rows = activeTab.querySelectorAll('tbody tr');

    rows.forEach(row => {
        let showRow = true;

        // Status filter
        if (statusFilter) {
            const statusBadge = row.querySelector('.status-badge');
            if (statusBadge) {
                const status = statusBadge.className;
                const statusMap = {
                    'en_regle': 'en-regle',
                    'non_en_regle': 'en-retard',
                    'en_attente': 'en-attente'
                };

                if (statusMap[statusFilter] && !status.includes(statusMap[statusFilter])) {
                    showRow = false;
                }
            }
        }

        // Type filter
        if (typeFilter) {
            const typeBadge = row.querySelector('.type-badge');
            if (typeBadge) {
                const type = typeBadge.className;
                const typeMap = {
                    'prive': 'prive',
                    'public': 'public',
                    'semi_prive': 'semi_prive'
                };

                if (typeMap[typeFilter] && !type.includes(typeMap[typeFilter])) {
                    showRow = false;
                }
            }
        }

        row.style.display = showRow ? '' : 'none';
    });
}

// Initialize Checkboxes
function initializeCheckboxes() {
    // Select all checkboxes
    const selectAllCheckboxes = document.querySelectorAll('input[type="checkbox"][id^="selectAll"]');
    selectAllCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            const tableId = this.id.replace('selectAll', '').toLowerCase();
            const table = document.querySelector(`#${tableId} tbody`);
            if (table) {
                const rowCheckboxes = table.querySelectorAll('.row-checkbox');
                rowCheckboxes.forEach(cb => {
                    cb.checked = this.checked;
                });
            }
        });
    });

    // Individual row checkboxes
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    rowCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            updateSelectAllState();
        });
    });
}

// Update Select All State
function updateSelectAllState() {
    const activeTab = document.querySelector('.tab-panel.active');
    if (!activeTab) return;

    const selectAllCheckbox = activeTab.querySelector('input[type="checkbox"][id^="selectAll"]');
    const rowCheckboxes = activeTab.querySelectorAll('.row-checkbox');

    if (selectAllCheckbox && rowCheckboxes.length > 0) {
        const checkedCount = Array.from(rowCheckboxes).filter(cb => cb.checked).length;

        if (checkedCount === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
        } else if (checkedCount === rowCheckboxes.length) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
        } else {
            selectAllCheckbox.indeterminate = true;
        }
    }
}

// Initialize Actions


// Handle Action
function handleAction(action, row) {
    const actions = {
        'Voir détails': () => viewDetails(row),
        'Générer facture': () => generateInvoice(row),
        'Envoyer facture': () => sendInvoice(row),
        'Envoyer relance': () => sendReminder(row),
        'Contacter': () => contact(row),
        'Voir facture': () => viewInvoice(row),
        'Télécharger PDF': () => downloadPDF(row),
        'Envoyer': () => sendInvoice(row),
        'Marquer comme payée': () => markAsPaid(row),
        'Envoyer relance': () => sendReminder(row)
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

function generateInvoice(row) {
    showNotification('Génération de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture générée avec succès', 'success');
        updateInvoiceTable(row);
    }, 2000);
}

function sendInvoice(row) {
    showNotification('Envoi de la facture...', 'info');
    setTimeout(() => {
        showNotification('Facture envoyée avec succès', 'success');
    }, 1500);
}

function sendReminder(row) {
    showNotification('Envoi de la relance...', 'info');
    setTimeout(() => {
        showNotification('Relance envoyée avec succès', 'success');
    }, 1500);
}

function contact(row) {
    showNotification('Ouverture du contact...', 'info');
    setTimeout(() => {
        showContactModal(row);
    }, 500);
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

function markAsPaid(row) {
    if (confirm('Êtes-vous sûr de vouloir marquer cette facture comme payée ?')) {
        showNotification('Marquage comme payée...', 'info');
        setTimeout(() => {
            updateInvoiceStatus(row, 'paye');
            showNotification('Facture marquée comme payée', 'success');
        }, 1000);
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
}

// Generate Invoices
function generateInvoices() {
    const period = document.getElementById('billingPeriod').value;
    const type = document.getElementById('billingType').value;
    const filter = document.getElementById('etablissementFilter').value;

    showLoading('generateInvoices', 'Génération en cours...');

    // Simulate invoice generation
    setTimeout(() => {
        const results = simulateInvoiceGeneration(period, type, filter);
        showInvoiceResults(results);
        hideLoading('generateInvoices', 'Générer les factures');
        showNotification('Factures générées avec succès', 'success');
        updateInvoicesTable();
    }, 3000);
}

// Simulate Invoice Generation
function simulateInvoiceGeneration(period, type, filter) {
    return {
        period: period,
        type: type,
        filter: filter,
        count: Math.floor(Math.random() * 10) + 5,
        totalAmount: Math.floor(Math.random() * 5000000) + 1000000
    };
}

// Show Invoice Results
function showInvoiceResults(results) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'success-message';

    resultDiv.innerHTML = `
        <h4><i class="fas fa-check-circle"></i> Factures générées avec succès</h4>
        <p>Période: ${results.period} | Type: ${results.type} | Nombre: ${results.count} | Montant total: ${results.totalAmount.toLocaleString()} FCFA</p>
    `;

    // Insert after the form
    const form = document.querySelector('.invoice-form');
    if (form) {
        form.parentNode.insertBefore(resultDiv, form.nextSibling);

        // Remove after 8 seconds
        setTimeout(() => {
            if (resultDiv.parentNode) {
                resultDiv.parentNode.removeChild(resultDiv);
            }
        }, 8000);
    }
}

// Update Invoice Table
function updateInvoicesTable() {
    const tbody = document.querySelector('#factures .data-table tbody');
    if (tbody) {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td><input type="checkbox" class="row-checkbox"></td>
            <td>
                <div class="invoice-info">
                    <h4>FAC-2024-${String(Math.floor(Math.random() * 1000) + 1).padStart(3, '0')}</h4>
                    <p>${new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })}</p>
                </div>
            </td>
            <td>
                <div class="etablissement-info">
                    <h4>Nouvel Établissement</h4>
                    <p>Ville, Cameroun</p>
                </div>
            </td>
            <td><span class="amount">${(Math.random() * 1000000 + 500000).toLocaleString()} FCFA</span></td>
            <td><span class="amount paid">0 FCFA</span></td>
            <td><span class="amount remaining">${(Math.random() * 1000000 + 500000).toLocaleString()} FCFA</span></td>
            <td><span class="status-badge impaye">Impayée</span></td>
            <td><span class="date">${new Date().toLocaleDateString('fr-FR')}</span></td>
        `;
        tbody.appendChild(newRow);

        // Add event listeners to new buttons
        initializeActions();
    }
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

    // Update remaining amount if paid
    if (status === 'paye') {
        const paidAmount = row.querySelector('.amount.paid');
        const remainingAmount = row.querySelector('.amount.remaining');
        const totalAmount = row.querySelector('.amount:not(.paid):not(.remaining)');

        if (paidAmount && remainingAmount && totalAmount) {
            paidAmount.textContent = totalAmount.textContent;
            remainingAmount.textContent = '0 FCFA';
            remainingAmount.classList.remove('urgent');
        }
    }
}

// Global Functions
function selectAll() {
    const activeTab = document.querySelector('.tab-panel.active');
    if (activeTab) {
        const selectAllCheckbox = activeTab.querySelector('input[type="checkbox"][id^="selectAll"]');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.dispatchEvent(new Event('change'));
        }
    }
}

function clearSelection() {
    const activeTab = document.querySelector('.tab-panel.active');
    if (activeTab) {
        const selectAllCheckbox = activeTab.querySelector('input[type="checkbox"][id^="selectAll"]');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.dispatchEvent(new Event('change'));
        }
    }
}

function generateAllInvoices() {
    showNotification('Génération de toutes les factures...', 'info');
    setTimeout(() => {
        showNotification('Toutes les factures ont été générées', 'success');
        updateInvoicesTable();
    }, 3000);
}

function generateInvoicesForSelected() {
    const selectedRows = getSelectedRows();
    if (selectedRows.length === 0) {
        showNotification('Aucun établissement sélectionné', 'warning');
        return;
    }

    showNotification(`Génération des factures pour ${selectedRows.length} établissement(s)...`, 'info');
    setTimeout(() => {
        showNotification('Factures générées pour les établissements sélectionnés', 'success');
        updateInvoicesTable();
    }, 2000);
}

function generateSelectedInvoices() {
    generateInvoicesForSelected();
}

function sendSelectedInvoices() {
    const selectedRows = getSelectedRows();
    if (selectedRows.length === 0) {
        showNotification('Aucune facture sélectionnée', 'warning');
        return;
    }

    showNotification(`Envoi de ${selectedRows.length} facture(s)...`, 'info');
    setTimeout(() => {
        showNotification('Factures envoyées avec succès', 'success');
    }, 2000);
}

function sendReminders() {
    const selectedRows = getSelectedRows();
    if (selectedRows.length === 0) {
        showNotification('Aucun établissement sélectionné', 'warning');
        return;
    }

    showNotification(`Envoi de relances à ${selectedRows.length} établissement(s)...`, 'info');
    setTimeout(() => {
        showNotification('Relances envoyées avec succès', 'success');
    }, 2000);
}

function escalateToLegal() {
    const selectedRows = getSelectedRows();
    if (selectedRows.length === 0) {
        showNotification('Aucun établissement sélectionné', 'warning');
        return;
    }

    if (confirm(`Êtes-vous sûr de vouloir escalader ${selectedRows.length} établissement(s) vers le service juridique ?`)) {
        showNotification('Escalade vers le service juridique...', 'info');
        setTimeout(() => {
            showNotification('Escalade effectuée avec succès', 'success');
        }, 2000);
    }
}

function exportAllData() {
    showNotification('Export de toutes les données...', 'info');
    setTimeout(() => {
        showNotification('Export terminé avec succès', 'success');
    }, 2000);
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

// Get Selected Rows
function getSelectedRows() {
    const activeTab = document.querySelector('.tab-panel.active');
    if (!activeTab) return [];

    const checkboxes = activeTab.querySelectorAll('.row-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.closest('tr'));
}

// Modal Functions
function showDetailsModal(row) {
    showNotification('Ouverture des détails de l\'établissement...', 'info');
    // Simulate showing details modal
}

function showContactModal(row) {
    showNotification('Ouverture du contact...', 'info');
    // Simulate showing contact modal
}

function showInvoiceModal(row) {
    showNotification('Ouverture de la facture...', 'info');
    // Simulate showing invoice modal
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

// Show Loading
function showLoading(buttonId, text) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = true;
        button.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${text}`;
        button.classList.add('generating');
    }
}

// Hide Loading
function hideLoading(buttonId, originalText) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = false;
        button.innerHTML = `<i class="fas fa-file-invoice"></i> ${originalText}`;
        button.classList.remove('generating');
        button.classList.add('success-animation');

        setTimeout(() => {
            button.classList.remove('success-animation');
        }, 500);
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
window.GestionEtablissements = {
    selectAll,
    clearSelection,
    generateAllInvoices,
    generateInvoicesForSelected,
    generateSelectedInvoices,
    sendSelectedInvoices,
    sendReminders,
    escalateToLegal,
    exportAllData,
    refreshData,
    showNotification,
    handleAction,
    generateInvoices
};
