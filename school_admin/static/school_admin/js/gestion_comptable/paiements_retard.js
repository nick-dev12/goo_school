// Paiements en Retard JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeSearch();
    initializeFilters();
    initializeTableActions();
    initializeCheckboxes();
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

// Initialize Search
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    const tableRows = document.querySelectorAll('.data-table tbody tr');

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            const searchTerm = this.value.toLowerCase().trim();

            tableRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const shouldShow = text.includes(searchTerm);

                row.style.display = shouldShow ? '' : 'none';

                if (shouldShow) {
                    row.classList.add('search-highlight');
                    setTimeout(() => {
                        row.classList.remove('search-highlight');
                    }, 1000);
                }
            });

            // Update empty state if no results
            updateEmptyState();
        });
    }
}

// Initialize Filters
function initializeFilters() {
    const statusFilter = document.getElementById('statusFilter');
    const delayFilter = document.getElementById('delayFilter');
    const amountFilter = document.getElementById('amountFilter');
    const clearFiltersBtn = document.getElementById('clearFilters');
    const tableRows = document.querySelectorAll('.data-table tbody tr');

    function applyFilters() {
        const statusValue = statusFilter.value;
        const delayValue = delayFilter.value;
        const amountValue = amountFilter.value;

        tableRows.forEach(row => {
            let shouldShow = true;

            // Status filter
            if (statusValue) {
                const statusBadge = row.querySelector('.status-badge');
                if (statusBadge) {
                    const status = statusBadge.textContent.toLowerCase().trim();
                    const statusMap = {
                        'en_retard': 'en-retard',
                        'relance_envoyee': 'relance-envoyée',
                        'mise_en_demeure': 'mise-en-demeure',
                        'contentieux': 'contentieux'
                    };
                    shouldShow = shouldShow && status.includes(statusMap[statusValue] || statusValue);
                }
            }

            // Delay filter
            if (delayValue) {
                const delayBadge = row.querySelector('.delay-badge');
                if (delayBadge) {
                    const delayText = delayBadge.textContent.toLowerCase();
                    const delayDays = parseInt(delayText.replace(/\D/g, ''));

                    switch (delayValue) {
                        case '1-7':
                            shouldShow = shouldShow && delayDays >= 1 && delayDays <= 7;
                            break;
                        case '8-15':
                            shouldShow = shouldShow && delayDays >= 8 && delayDays <= 15;
                            break;
                        case '16-30':
                            shouldShow = shouldShow && delayDays >= 16 && delayDays <= 30;
                            break;
                        case '30+':
                            shouldShow = shouldShow && delayDays > 30;
                            break;
                    }
                }
            }

            // Amount filter
            if (amountValue) {
                const amountElement = row.querySelector('.amount');
                if (amountElement) {
                    const amountText = amountElement.textContent.replace(/[^\d]/g, '');
                    const amount = parseInt(amountText);

                    switch (amountValue) {
                        case '0-1000000':
                            shouldShow = shouldShow && amount >= 0 && amount <= 1000000;
                            break;
                        case '1000000-5000000':
                            shouldShow = shouldShow && amount > 1000000 && amount <= 5000000;
                            break;
                        case '5000000+':
                            shouldShow = shouldShow && amount > 5000000;
                            break;
                    }
                }
            }

            row.style.display = shouldShow ? '' : 'none';
        });

        updateEmptyState();
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', applyFilters);
    }

    if (delayFilter) {
        delayFilter.addEventListener('change', applyFilters);
    }

    if (amountFilter) {
        amountFilter.addEventListener('change', applyFilters);
    }

    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', function () {
            statusFilter.value = '';
            delayFilter.value = '';
            amountFilter.value = '';
            document.getElementById('searchInput').value = '';

            tableRows.forEach(row => {
                row.style.display = '';
            });

            updateEmptyState();
        });
    }
}

// Initialize Table Actions
function initializeTableActions() {
    const actionButtons = document.querySelectorAll('.btn-action');

    actionButtons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.stopPropagation();
            const action = this.getAttribute('title');
            const row = this.closest('tr');
            const etablissement = row.querySelector('h4')?.textContent || 'cet élément';

            handleAction(action, etablissement, row);
        });
    });
}

// Handle Action
function handleAction(action, etablissement, row) {
    const actions = {
        'Voir détails': () => showDetails(etablissement, row),
        'Envoyer relance': () => sendReminder(etablissement),
        'Mise en demeure': () => sendLegalNotice(etablissement),
        'Appeler': () => callEstablishment(etablissement),
        'Voir contentieux': () => showLegalCase(etablissement),
        'Suspendre service': () => suspendService(etablissement),
        'Voir relance': () => viewReminder(etablissement),
        'Renvoyer': () => resendReminder(etablissement),
        'Suivre': () => followUp(etablissement),
        'Voir dossier': () => viewLegalFile(etablissement),
        'Mettre à jour': () => updateLegalFile(etablissement)
    };

    if (actions[action]) {
        actions[action]();
    } else {
        showNotification(`Action "${action}" non implémentée`, 'info');
    }
}

// Action Functions
function showDetails(etablissement, row) {
    showNotification(`Affichage des détails pour ${etablissement}`, 'info');
    // Here you would open a modal or navigate to details page
}

function sendReminder(etablissement) {
    showNotification(`Relance envoyée à ${etablissement}`, 'success');
    // Here you would send an actual reminder
    updateStatusBadge(row, 'relance-envoyee', 'Relance envoyée');
}

function sendLegalNotice(etablissement) {
    showNotification(`Mise en demeure envoyée à ${etablissement}`, 'warning');
    // Here you would send a legal notice
    updateStatusBadge(row, 'mise-en-demeure', 'Mise en demeure');
}

function callEstablishment(etablissement) {
    showNotification(`Appel en cours vers ${etablissement}`, 'info');
    // Here you would initiate a call
}

function showLegalCase(etablissement) {
    showNotification(`Affichage du contentieux pour ${etablissement}`, 'info');
    // Here you would show legal case details
}

function suspendService(etablissement) {
    if (confirm(`Êtes-vous sûr de vouloir suspendre le service pour ${etablissement} ?`)) {
        showNotification(`Service suspendu pour ${etablissement}`, 'error');
        // Here you would suspend the service
    }
}

function viewReminder(etablissement) {
    showNotification(`Affichage de la relance pour ${etablissement}`, 'info');
    // Here you would show reminder details
}

function resendReminder(etablissement) {
    showNotification(`Relance renvoyée à ${etablissement}`, 'success');
    // Here you would resend the reminder
}

function followUp(etablissement) {
    showNotification(`Suivi activé pour ${etablissement}`, 'info');
    // Here you would activate follow-up
}

function viewLegalFile(etablissement) {
    showNotification(`Affichage du dossier contentieux pour ${etablissement}`, 'info');
    // Here you would show legal file
}

function updateLegalFile(etablissement) {
    showNotification(`Mise à jour du dossier contentieux pour ${etablissement}`, 'info');
    // Here you would update legal file
}

// Initialize Checkboxes
function initializeCheckboxes() {
    const selectAllCheckbox = document.getElementById('selectAll');
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');

    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function () {
            rowCheckboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
            updateBulkActions();
        });
    }

    rowCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            updateSelectAllState();
            updateBulkActions();
        });
    });
}

// Update Select All State
function updateSelectAllState() {
    const selectAllCheckbox = document.getElementById('selectAll');
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;

    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checkedCount === rowCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < rowCheckboxes.length;
    }
}

// Initialize Bulk Actions
function initializeBulkActions() {
    // Add bulk action buttons dynamically
    const tableHeader = document.querySelector('.table-header .table-actions');
    if (tableHeader) {
        const bulkActionsDiv = document.createElement('div');
        bulkActionsDiv.className = 'bulk-actions';
        bulkActionsDiv.style.display = 'none';
        bulkActionsDiv.innerHTML = `
            <button class="btn-small primary" id="bulkReminder">
                <i class="fas fa-paper-plane"></i> Relance groupée
            </button>
            <button class="btn-small warning" id="bulkLegalNotice">
                <i class="fas fa-gavel"></i> Mise en demeure
            </button>
            <button class="btn-small danger" id="bulkSuspend">
                <i class="fas fa-ban"></i> Suspendre
            </button>
        `;
        tableHeader.appendChild(bulkActionsDiv);

        // Add event listeners
        document.getElementById('bulkReminder')?.addEventListener('click', bulkSendReminders);
        document.getElementById('bulkLegalNotice')?.addEventListener('click', bulkSendLegalNotices);
        document.getElementById('bulkSuspend')?.addEventListener('click', bulkSuspendServices);
    }
}

// Update Bulk Actions
function updateBulkActions() {
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');
    const bulkActions = document.querySelector('.bulk-actions');

    if (bulkActions) {
        bulkActions.style.display = checkedBoxes.length > 0 ? 'flex' : 'none';
    }
}

// Bulk Actions
function bulkSendReminders() {
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');
    const count = checkedBoxes.length;

    if (count > 0) {
        showNotification(`${count} relance(s) envoyée(s)`, 'success');
        checkedBoxes.forEach(checkbox => {
            const row = checkbox.closest('tr');
            updateStatusBadge(row, 'relance-envoyee', 'Relance envoyée');
        });
    }
}

function bulkSendLegalNotices() {
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');
    const count = checkedBoxes.length;

    if (count > 0) {
        if (confirm(`Êtes-vous sûr de vouloir envoyer ${count} mise(s) en demeure ?`)) {
            showNotification(`${count} mise(s) en demeure envoyée(s)`, 'warning');
            checkedBoxes.forEach(checkbox => {
                const row = checkbox.closest('tr');
                updateStatusBadge(row, 'mise-en-demeure', 'Mise en demeure');
            });
        }
    }
}

function bulkSuspendServices() {
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');
    const count = checkedBoxes.length;

    if (count > 0) {
        if (confirm(`Êtes-vous sûr de vouloir suspendre ${count} service(s) ?`)) {
            showNotification(`${count} service(s) suspendu(s)`, 'error');
            checkedBoxes.forEach(checkbox => {
                const row = checkbox.closest('tr');
                updateStatusBadge(row, 'contentieux', 'Contentieux');
            });
        }
    }
}

// Update Status Badge
function updateStatusBadge(row, newStatus, newText) {
    const statusBadge = row.querySelector('.status-badge');
    if (statusBadge) {
        statusBadge.className = `status-badge ${newStatus}`;
        statusBadge.textContent = newText;
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
    const cards = document.querySelectorAll('.summary-card, .table-container');
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

// Update Empty State
function updateEmptyState() {
    const activePanel = document.querySelector('.tab-panel.active');
    const visibleRows = activePanel.querySelectorAll('.data-table tbody tr:not([style*="display: none"])');

    if (visibleRows.length === 0) {
        showEmptyState(activePanel);
    } else {
        hideEmptyState(activePanel);
    }
}

// Show Empty State
function showEmptyState(panel) {
    let emptyState = panel.querySelector('.empty-state');

    if (!emptyState) {
        emptyState = document.createElement('div');
        emptyState.className = 'empty-state';
        emptyState.innerHTML = `
            <i class="fas fa-search"></i>
            <h3>Aucun résultat trouvé</h3>
            <p>Essayez de modifier vos critères de recherche ou de filtrage</p>
        `;

        const tableContainer = panel.querySelector('.table-container');
        if (tableContainer) {
            tableContainer.appendChild(emptyState);
        }
    }

    emptyState.style.display = 'block';
}

// Hide Empty State
function hideEmptyState(panel) {
    const emptyState = panel.querySelector('.empty-state');
    if (emptyState) {
        emptyState.style.display = 'none';
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

// Export Functions
function exportReport(format = 'excel') {
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
    const tableContainer = document.querySelector('.table-container');
    if (tableContainer) {
        tableContainer.classList.add('loading');
    }

    setTimeout(() => {
        if (tableContainer) {
            tableContainer.classList.remove('loading');
        }
        showNotification('Données actualisées', 'success');
    }, 1000);
}

// Add CSS for search highlight and bulk actions
const style = document.createElement('style');
style.textContent = `
    .search-highlight {
        background-color: #fef5e7 !important;
        border-left: 4px solid #f6ad55 !important;
    }
    
    .tooltip {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    .bulk-actions {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-left: 16px;
    }
`;
document.head.appendChild(style);

// Export functions to global scope
window.PaiementsRetard = {
    exportReport,
    refreshData,
    showNotification,
    handleAction,
    bulkSendReminders,
    bulkSendLegalNotices,
    bulkSuspendServices
};
