// Gestion des Dépenses - JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Initialize the page
    initializePage();

    // Setup event listeners
    setupEventListeners();

    // Load initial data
    loadExpensesData();
});

// Initialize page
function initializePage() {
    console.log('Initializing Expense Management page...');

    // Add fade-in animation
    document.body.classList.add('fade-in');

    // Initialize tooltips
    initializeTooltips();

    // Setup search functionality
    setupSearch();

    // Setup filters
    setupFilters();
}

// Setup event listeners
function setupEventListeners() {
    // Tab switching
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(button => {
        button.addEventListener('click', function () {
            const tabId = this.getAttribute('onclick').match(/'([^']+)'/)[1];
            switchTab(tabId);
        });
    });

    // Select all checkbox
    const selectAllCheckbox = document.getElementById('selectAllExpenses');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function () {
            toggleSelectAll(this.checked);
        });
    }

    // Individual row checkboxes
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    rowCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            updateSelectAllState();
        });
    });

    // Modal close buttons
    const closeButtons = document.querySelectorAll('.close');
    closeButtons.forEach(button => {
        button.addEventListener('click', function () {
            const modal = this.closest('.modal');
            closeModal(modal.id);
        });
    });

    // Click outside modal to close
    window.addEventListener('click', function (event) {
        if (event.target.classList.contains('modal')) {
            closeModal(event.target.id);
        }
    });
}

// Tab switching functionality
function switchTab(tabId) {
    // Remove active class from all tabs and panels
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));

    // Add active class to selected tab and panel
    const selectedTab = document.querySelector(`[onclick="switchTab('${tabId}')"]`);
    const selectedPanel = document.getElementById(tabId);

    if (selectedTab) selectedTab.classList.add('active');
    if (selectedPanel) selectedPanel.classList.add('active');

    // Load tab-specific data
    loadTabData(tabId);

    console.log(`Switched to tab: ${tabId}`);
}

// Load tab-specific data
function loadTabData(tabId) {
    switch (tabId) {
        case 'liste-depenses':
            loadExpensesList();
            break;
        case 'categories':
            loadCategoriesData();
            break;
        case 'budget':
            loadBudgetData();
            break;
        case 'rapports':
            loadReportsData();
            break;
    }
}

// Setup search functionality
function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            performSearch(this.value);
        });
    }
}

// Setup filters
function setupFilters() {
    const filters = ['categoryFilter', 'statusFilter', 'amountFilter', 'dateFilter'];

    filters.forEach(filterId => {
        const filter = document.getElementById(filterId);
        if (filter) {
            filter.addEventListener('change', function () {
                applyFilters();
            });
        }
    });
}

// Perform search
function performSearch(searchTerm) {
    const rows = document.querySelectorAll('.data-table tbody tr');
    const term = searchTerm.toLowerCase();

    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const shouldShow = text.includes(term);
        row.style.display = shouldShow ? '' : 'none';
    });

    console.log(`Search performed: "${searchTerm}"`);
}

// Apply filters
function applyFilters() {
    const categoryFilter = document.getElementById('categoryFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    const amountFilter = document.getElementById('amountFilter').value;
    const dateFilter = document.getElementById('dateFilter').value;

    const rows = document.querySelectorAll('.data-table tbody tr');

    rows.forEach(row => {
        let shouldShow = true;

        // Category filter
        if (categoryFilter) {
            const category = row.querySelector('.category');
            if (category && !category.classList.contains(categoryFilter)) {
                shouldShow = false;
            }
        }

        // Status filter
        if (statusFilter) {
            const status = row.querySelector('.status-badge');
            if (status && !status.classList.contains(statusFilter)) {
                shouldShow = false;
            }
        }

        // Amount filter
        if (amountFilter) {
            const amountText = row.querySelector('.amount').textContent;
            const amount = parseInt(amountText.replace(/[^\d]/g, ''));

            switch (amountFilter) {
                case '0-50000':
                    shouldShow = shouldShow && amount >= 0 && amount <= 50000;
                    break;
                case '50000-200000':
                    shouldShow = shouldShow && amount > 50000 && amount <= 200000;
                    break;
                case '200000-500000':
                    shouldShow = shouldShow && amount > 200000 && amount <= 500000;
                    break;
                case '500000+':
                    shouldShow = shouldShow && amount > 500000;
                    break;
            }
        }

        // Date filter
        if (dateFilter) {
            const dateText = row.querySelector('.date').textContent;
            // Simple date matching - in real app, you'd parse dates properly
            if (!dateText.includes(dateFilter.split('-')[2])) {
                shouldShow = false;
            }
        }

        row.style.display = shouldShow ? '' : 'none';
    });

    console.log('Filters applied');
}

// Clear search
function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.value = '';
        performSearch('');
    }

    // Reset filters
    const filters = ['categoryFilter', 'statusFilter', 'amountFilter', 'dateFilter'];
    filters.forEach(filterId => {
        const filter = document.getElementById(filterId);
        if (filter) {
            filter.value = '';
        }
    });

    applyFilters();
}

// Toggle select all
function toggleSelectAll(checked) {
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    rowCheckboxes.forEach(checkbox => {
        checkbox.checked = checked;
    });
}

// Update select all state
function updateSelectAllState() {
    const selectAllCheckbox = document.getElementById('selectAllExpenses');
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');

    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checkedBoxes.length === rowCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedBoxes.length > 0 && checkedBoxes.length < rowCheckboxes.length;
    }
}

// Load expenses data
function loadExpensesData() {
    console.log('Loading expenses data...');
    // Simulate data loading
    setTimeout(() => {
        console.log('Expenses data loaded');
    }, 500);
}

// Load expenses list
function loadExpensesList() {
    console.log('Loading expenses list...');
    // This would typically fetch data from the server
}

// Load categories data
function loadCategoriesData() {
    console.log('Loading categories data...');
    // This would typically fetch categories data from the server
}

// Load budget data
function loadBudgetData() {
    console.log('Loading budget data...');
    // This would typically fetch budget data from the server
}

// Load reports data
function loadReportsData() {
    console.log('Loading reports data...');
    // This would typically fetch reports data from the server
}

// Modal functions
function openAddExpenseModal() {
    const modal = document.getElementById('addExpenseModal');
    if (modal) {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

// Expense management functions
function saveExpense() {
    const form = document.querySelector('.expense-form');

    // Validate form
    if (validateExpenseForm()) {
        // Simulate saving
        showNotification('Dépense ajoutée avec succès!', 'success');
        closeModal('addExpenseModal');
        form.reset();

        // Refresh the list
        loadExpensesList();
    }
}

function validateExpenseForm() {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = 'var(--error)';
            isValid = false;
        } else {
            field.style.borderColor = 'var(--border-color)';
        }
    });

    return isValid;
}

function editExpense(expenseId) {
    // Get expense data
    const expenseData = getExpenseData(expenseId);

    // Populate modal
    const modal = document.getElementById('editExpenseModal');
    const form = modal.querySelector('.expense-form');

    form.querySelector('input[type="text"]').value = expenseData.description;
    form.querySelector('input[type="number"]').value = expenseData.amount;
    form.querySelector('select').value = expenseData.category;

    // Show modal
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function saveExpenseChanges() {
    const form = document.querySelector('.expense-form');

    // Validate form
    if (validateExpenseForm()) {
        // Simulate saving
        showNotification('Dépense modifiée avec succès!', 'success');
        closeModal('editExpenseModal');
        form.reset();

        // Refresh expenses data
        loadExpensesList();
    }
}

function viewExpenseDetails(expenseId) {
    // Get expense data
    const expenseData = getExpenseData(expenseId);

    // Show details (could be a modal or redirect)
    showNotification(`Détails de la dépense: ${expenseData.description}`, 'info');
    console.log('Viewing expense details:', expenseData);
}

function downloadInvoice(expenseId) {
    // Simulate invoice download
    showNotification('Téléchargement de la facture...', 'info');

    setTimeout(() => {
        showNotification('Facture téléchargée avec succès!', 'success');
    }, 1500);
}

// Category management functions
function editCategory(categoryId) {
    showNotification(`Modification de la catégorie ${categoryId}`, 'info');
    // This would open a modal for category editing
}

function viewCategoryDetails(categoryId) {
    showNotification(`Détails de la catégorie ${categoryId}`, 'info');
    // This would show category details
}

function openAddCategoryModal() {
    showNotification('Ouverture de la modal d\'ajout de catégorie...', 'info');
    // This would open a modal for adding categories
}

// Budget management functions
function openBudgetModal() {
    const modal = document.getElementById('budgetModal');
    if (modal) {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
}

function saveBudget() {
    const form = document.querySelector('.budget-form');

    // Validate form
    if (validateBudgetForm()) {
        // Simulate saving
        showNotification('Budget mis à jour avec succès!', 'success');
        closeModal('budgetModal');

        // Refresh budget data
        loadBudgetData();
    }
}

function validateBudgetForm() {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = 'var(--error)';
            isValid = false;
        } else {
            field.style.borderColor = 'var(--border-color)';
        }
    });

    return isValid;
}

// Report functions
function generateExpenseReport() {
    showNotification('Génération du rapport des dépenses...', 'info');

    // Simulate report generation
    setTimeout(() => {
        showNotification('Rapport des dépenses généré avec succès!', 'success');
    }, 2000);
}

function exportExpensesList() {
    showNotification('Export de la liste des dépenses...', 'info');

    // Simulate export
    setTimeout(() => {
        showNotification('Liste exportée avec succès!', 'success');
    }, 1500);
}

function bulkApprove() {
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');

    if (checkedBoxes.length === 0) {
        showNotification('Veuillez sélectionner au moins une dépense', 'warning');
        return;
    }

    showNotification(`Approbation de ${checkedBoxes.length} dépense(s)...`, 'info');

    // Simulate bulk approval
    setTimeout(() => {
        showNotification(`${checkedBoxes.length} dépense(s) approuvée(s) avec succès!`, 'success');
    }, 2000);
}

function analyzeTrends() {
    showNotification('Analyse des tendances en cours...', 'info');

    // Simulate analysis
    setTimeout(() => {
        showNotification('Analyse des tendances terminée!', 'success');
    }, 2000);
}

function compareBudget() {
    showNotification('Comparaison du budget en cours...', 'info');

    // Simulate comparison
    setTimeout(() => {
        showNotification('Comparaison du budget terminée!', 'success');
    }, 2000);
}

function exportData() {
    showNotification('Export des données en cours...', 'info');

    // Simulate export
    setTimeout(() => {
        showNotification('Données exportées avec succès!', 'success');
    }, 1500);
}

// Utility functions
function getExpenseData(expenseId) {
    // Mock data - in real app, this would fetch from server
    const expenseData = {
        1: { description: 'Achat matériel informatique', amount: 850000, category: 'equipement' },
        2: { description: 'Formation du personnel', amount: 320000, category: 'formation' },
        3: { description: 'Maintenance serveurs', amount: 150000, category: 'maintenance' },
        4: { description: 'Fournitures de bureau', amount: 45000, category: 'bureau' },
        5: { description: 'Campagne publicitaire', amount: 180000, category: 'marketing' }
    };

    return expenseData[expenseId] || { description: 'Inconnu', amount: 0, category: 'autre' };
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency: 'XOF',
        minimumFractionDigits: 0
    }).format(amount);
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fas fa-${getNotificationIcon(type)}"></i>
            <span>${message}</span>
        </div>
    `;

    // Add styles
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 16px 20px;
        box-shadow: var(--shadow-lg);
        z-index: 10000;
        max-width: 400px;
        transform: translateX(100%);
        transition: transform 0.3s ease;
        font-size: 14px;
        color: var(--text-primary);
    `;

    // Add type-specific styling
    const colors = {
        success: 'var(--success)',
        error: 'var(--error)',
        warning: 'var(--warning)',
        info: 'var(--info)'
    };

    notification.style.borderLeftColor = colors[type] || colors.info;
    notification.style.borderLeftWidth = '4px';

    // Add to page
    document.body.appendChild(notification);

    // Show notification
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);

    // Hide and remove notification
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 4000);
}

function getNotificationIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };

    return icons[type] || 'info-circle';
}

function initializeTooltips() {
    // Add tooltip functionality to action buttons
    const actionButtons = document.querySelectorAll('.btn-action');
    actionButtons.forEach(button => {
        button.addEventListener('mouseenter', function () {
            const title = this.getAttribute('title');
            if (title) {
                showTooltip(this, title);
            }
        });

        button.addEventListener('mouseleave', function () {
            hideTooltip();
        });
    });
}

function showTooltip(element, text) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = text;
    tooltip.style.cssText = `
        position: absolute;
        background: var(--text-primary);
        color: var(--bg-primary);
        padding: 6px 10px;
        border-radius: var(--radius-sm);
        font-size: 12px;
        font-weight: 500;
        z-index: 1000;
        pointer-events: none;
        white-space: nowrap;
    `;

    document.body.appendChild(tooltip);

    const rect = element.getBoundingClientRect();
    tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
    tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';
}

function hideTooltip() {
    const tooltip = document.querySelector('.tooltip');
    if (tooltip) {
        tooltip.remove();
    }
}

// Add fade-in animation
document.body.style.opacity = '0';
document.body.style.transition = 'opacity 0.3s ease';

window.addEventListener('load', function () {
    document.body.style.opacity = '1';
    document.body.classList.add('fade-in');
});

