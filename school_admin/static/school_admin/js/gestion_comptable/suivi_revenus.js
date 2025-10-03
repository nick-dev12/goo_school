// Suivi des Revenus JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeSearch();
    initializeFilters();
    initializeTableActions();
    initializeTooltips();
    initializeAnimations();
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
    const monthFilter = document.getElementById('monthFilter');
    const clearFiltersBtn = document.getElementById('clearFilters');
    const tableRows = document.querySelectorAll('.data-table tbody tr');

    function applyFilters() {
        const statusValue = statusFilter.value;
        const monthValue = monthFilter.value;

        tableRows.forEach(row => {
            let shouldShow = true;

            // Status filter
            if (statusValue) {
                const statusBadge = row.querySelector('.status-badge');
                if (statusBadge) {
                    const status = statusBadge.textContent.toLowerCase().trim();
                    const statusMap = {
                        'actif': 'en-cours',
                        'en_attente': 'en-attente',
                        'en_retard': 'en-retard',
                        'termine': 'termine'
                    };
                    shouldShow = shouldShow && status.includes(statusMap[statusValue] || statusValue);
                }
            }

            // Month filter (simplified - would need actual date data)
            if (monthValue) {
                const dateElement = row.querySelector('.date');
                if (dateElement) {
                    const dateText = dateElement.textContent.toLowerCase();
                    shouldShow = shouldShow && dateText.includes(monthValue);
                }
            }

            row.style.display = shouldShow ? '' : 'none';
        });

        updateEmptyState();
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', applyFilters);
    }

    if (monthFilter) {
        monthFilter.addEventListener('change', applyFilters);
    }

    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', function () {
            statusFilter.value = '';
            monthFilter.value = '';
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
        'Modifier': () => editItem(etablissement, row),
        'Envoyer rappel': () => sendReminder(etablissement),
        'Envoyer relance': () => sendFollowUp(etablissement),
        'Télécharger facture': () => downloadInvoice(etablissement),
        'Télécharger reçu': () => downloadReceipt(etablissement),
        'Télécharger quittance': () => downloadQuittance(etablissement)
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

function editItem(etablissement, row) {
    showNotification(`Modification de ${etablissement}`, 'info');
    // Here you would open an edit form
}

function sendReminder(etablissement) {
    showNotification(`Rappel envoyé à ${etablissement}`, 'success');
    // Here you would send an actual reminder
}

function sendFollowUp(etablissement) {
    showNotification(`Relance envoyée à ${etablissement}`, 'warning');
    // Here you would send a follow-up
}

function downloadInvoice(etablissement) {
    showNotification(`Téléchargement de la facture pour ${etablissement}`, 'info');
    // Here you would trigger file download
}

function downloadReceipt(etablissement) {
    showNotification(`Téléchargement du reçu pour ${etablissement}`, 'info');
    // Here you would trigger file download
}

function downloadQuittance(etablissement) {
    showNotification(`Téléchargement de la quittance pour ${etablissement}`, 'info');
    // Here you would trigger file download
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
    tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';

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
function exportData(format = 'excel') {
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

// Add CSS for search highlight
const style = document.createElement('style');
style.textContent = `
    .search-highlight {
        background-color: #fef5e7 !important;
        border-left: 4px solid #f6ad55 !important;
    }
    
    .tooltip {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
`;
document.head.appendChild(style);

// Export functions to global scope
window.SuiviRevenus = {
    exportData,
    refreshData,
    showNotification,
    handleAction
};
