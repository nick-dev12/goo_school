// Gestion Financière du Personnel - JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Initialize the page
    initializePage();

    // Setup event listeners
    setupEventListeners();

    // Load initial data
    loadPersonnelData();
});

// Initialize page
function initializePage() {
    console.log('Initializing Personnel Financial Management page...');

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
    const selectAllCheckbox = document.getElementById('selectAllPersonnel');
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
        case 'liste-personnel':
            loadPersonnelList();
            break;
        case 'salaires':
            loadSalaryData();
            break;
        case 'rapports':
            loadReportData();
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
    const filters = ['departmentFilter', 'statusFilter', 'salaryFilter'];

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
    const departmentFilter = document.getElementById('departmentFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    const salaryFilter = document.getElementById('salaryFilter').value;

    const rows = document.querySelectorAll('.data-table tbody tr');

    rows.forEach(row => {
        let shouldShow = true;

        // Department filter
        if (departmentFilter) {
            const department = row.querySelector('.department');
            if (department && !department.classList.contains(departmentFilter)) {
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

        // Salary filter
        if (salaryFilter) {
            const salaryText = row.querySelector('.salary').textContent;
            const salary = parseInt(salaryText.replace(/[^\d]/g, ''));

            switch (salaryFilter) {
                case '0-500000':
                    shouldShow = shouldShow && salary >= 0 && salary <= 500000;
                    break;
                case '500000-1000000':
                    shouldShow = shouldShow && salary > 500000 && salary <= 1000000;
                    break;
                case '1000000+':
                    shouldShow = shouldShow && salary > 1000000;
                    break;
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
    const filters = ['departmentFilter', 'statusFilter', 'salaryFilter'];
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
    const selectAllCheckbox = document.getElementById('selectAllPersonnel');
    const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    const checkedBoxes = document.querySelectorAll('.row-checkbox:checked');

    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checkedBoxes.length === rowCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedBoxes.length > 0 && checkedBoxes.length < rowCheckboxes.length;
    }
}

// Load personnel data
function loadPersonnelData() {
    console.log('Loading personnel data...');
    // Simulate data loading
    setTimeout(() => {
        console.log('Personnel data loaded');
    }, 500);
}

// Load personnel list
function loadPersonnelList() {
    console.log('Loading personnel list...');
    // This would typically fetch data from the server
}

// Load salary data
function loadSalaryData() {
    console.log('Loading salary data...');
    // This would typically fetch salary data from the server
}

// Load report data
function loadReportData() {
    console.log('Loading report data...');
    // This would typically fetch report data from the server
}

// Modal functions
function openAddPersonnelModal() {
    const modal = document.getElementById('addPersonnelModal');
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

// Personnel management functions
function savePersonnel() {
    const form = document.querySelector('.personnel-form');
    const formData = new FormData(form);

    // Validate form
    if (validatePersonnelForm()) {
        // Simulate saving
        showNotification('Personnel ajouté avec succès!', 'success');
        closeModal('addPersonnelModal');
        form.reset();

        // Refresh the list
        loadPersonnelList();
    }
}

function validatePersonnelForm() {
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

// Salary management functions
function editSalary(personnelId) {
    // Get personnel data
    const personnelData = getPersonnelData(personnelId);

    // Populate modal
    const modal = document.getElementById('editSalaryModal');
    const form = modal.querySelector('.salary-form');

    form.querySelector('input[type="text"]').value = personnelData.name;
    form.querySelector('input[type="number"]').value = personnelData.currentSalary;

    // Show modal
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function saveSalaryChange() {
    const form = document.querySelector('.salary-form');

    // Validate form
    if (validateSalaryForm()) {
        // Simulate saving
        showNotification('Salaire modifié avec succès!', 'success');
        closeModal('editSalaryModal');
        form.reset();

        // Refresh salary data
        loadSalaryData();
    }
}

function validateSalaryForm() {
    const salaryInput = document.querySelector('.salary-form input[type="number"]');
    const dateInput = document.querySelector('.salary-form input[type="date"]');

    let isValid = true;

    if (!salaryInput.value || salaryInput.value <= 0) {
        salaryInput.style.borderColor = 'var(--error)';
        isValid = false;
    } else {
        salaryInput.style.borderColor = 'var(--border-color)';
    }

    if (!dateInput.value) {
        dateInput.style.borderColor = 'var(--error)';
        isValid = false;
    } else {
        dateInput.style.borderColor = 'var(--border-color)';
    }

    return isValid;
}

function viewPersonnelDetails(personnelId) {
    // Get personnel data
    const personnelData = getPersonnelData(personnelId);

    // Show details (could be a modal or redirect)
    showNotification(`Détails de ${personnelData.name}`, 'info');
    console.log('Viewing personnel details:', personnelData);
}

function viewSalaryHistory(personnelId) {
    // Get salary history
    const salaryHistory = getSalaryHistory(personnelId);

    // Show history (could be a modal or redirect)
    showNotification(`Historique des salaires`, 'info');
    console.log('Viewing salary history:', salaryHistory);
}

// Salary calculation
function calculateSalary() {
    const baseSalary = parseFloat(document.getElementById('baseSalary').value) || 0;
    const performanceBonus = parseFloat(document.getElementById('performanceBonus').value) || 0;
    const overtimeHours = parseFloat(document.getElementById('overtimeHours').value) || 0;

    // Calculate salary components
    const bonusAmount = (baseSalary * performanceBonus) / 100;
    const overtimeRate = baseSalary / 160; // Assuming 160 hours per month
    const overtimeAmount = overtimeHours * overtimeRate;

    const totalSalary = baseSalary + bonusAmount + overtimeAmount;

    // Display results
    showSalaryCalculationResults({
        baseSalary: baseSalary,
        bonusAmount: bonusAmount,
        overtimeAmount: overtimeAmount,
        totalSalary: totalSalary
    });
}

function showSalaryCalculationResults(results) {
    const message = `
        Salaire de base: ${formatCurrency(results.baseSalary)}
        Prime de performance: ${formatCurrency(results.bonusAmount)}
        Heures supplémentaires: ${formatCurrency(results.overtimeAmount)}
        TOTAL: ${formatCurrency(results.totalSalary)}
    `;

    showNotification(message, 'info');
}

// Report functions
function generateSalaryReport() {
    showNotification('Génération du rapport des salaires...', 'info');

    // Simulate report generation
    setTimeout(() => {
        showNotification('Rapport des salaires généré avec succès!', 'success');
    }, 2000);
}

function generatePersonnelReport() {
    showNotification('Génération du rapport du personnel...', 'info');

    // Simulate report generation
    setTimeout(() => {
        showNotification('Rapport du personnel généré avec succès!', 'success');
    }, 2000);
}

function processMonthlySalaries() {
    showNotification('Traitement des salaires mensuels...', 'info');

    // Simulate processing
    setTimeout(() => {
        showNotification('Salaires mensuels traités avec succès!', 'success');
    }, 3000);
}

function openSalaryAdjustmentModal() {
    showNotification('Ouverture de la modal d\'ajustement salarial...', 'info');
    // This would open a modal for salary adjustments
}

function exportPersonnelList() {
    showNotification('Export de la liste du personnel...', 'info');

    // Simulate export
    setTimeout(() => {
        showNotification('Liste exportée avec succès!', 'success');
    }, 1500);
}

function analyzeCosts() {
    showNotification('Analyse des coûts en cours...', 'info');

    // Simulate analysis
    setTimeout(() => {
        showNotification('Analyse des coûts terminée!', 'success');
    }, 2000);
}

function compareSalaries() {
    showNotification('Comparaison des salaires en cours...', 'info');

    // Simulate comparison
    setTimeout(() => {
        showNotification('Comparaison des salaires terminée!', 'success');
    }, 2000);
}

// Utility functions
function getPersonnelData(personnelId) {
    // Mock data - in real app, this would fetch from server
    const personnelData = {
        1: { name: 'Marie Nguema', currentSalary: 1200000 },
        2: { name: 'Jean Mballa', currentSalary: 850000 },
        3: { name: 'Fatou Diallo', currentSalary: 650000 },
        4: { name: 'Paul Nkeng', currentSalary: 950000 },
        5: { name: 'Grace Mvogo', currentSalary: 450000 }
    };

    return personnelData[personnelId] || { name: 'Inconnu', currentSalary: 0 };
}

function getSalaryHistory(personnelId) {
    // Mock data - in real app, this would fetch from server
    return [
        { date: '2024-01-01', salary: 1200000, reason: 'Augmentation annuelle' },
        { date: '2023-01-01', salary: 1100000, reason: 'Augmentation de performance' },
        { date: '2022-01-01', salary: 1000000, reason: 'Salaire initial' }
    ];
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
