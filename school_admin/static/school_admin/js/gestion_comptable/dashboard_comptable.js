// Dashboard Comptable JavaScript
document.addEventListener('DOMContentLoaded', function () {
    // Initialisation des fonctionnalités du dashboard
    initializeDashboard();
    initializeTooltips();
    initializeCharts();
    initializeFilters();
    initializeNotifications();
});

// Initialisation générale du dashboard
function initializeDashboard() {
    console.log('Dashboard comptable initialisé');

    // Animation d'entrée pour les cartes
    animateCards();

    // Mise à jour des données en temps réel (simulation)
    updateRealTimeData();
}

// Animation des cartes au chargement
function animateCards() {
    const cards = document.querySelectorAll('.card, .kpi-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';

        setTimeout(() => {
            card.style.transition = 'all 0.6s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// Mise à jour des données en temps réel (simulation)
function updateRealTimeData() {
    // Simulation de mise à jour des KPIs
    setInterval(() => {
        updateKPIs();
    }, 30000); // Mise à jour toutes les 30 secondes
}

// Mise à jour des KPIs
function updateKPIs() {
    const kpiCards = document.querySelectorAll('.kpi-card');
    kpiCards.forEach(card => {
        card.style.transform = 'scale(1.02)';
        setTimeout(() => {
            card.style.transform = 'scale(1)';
        }, 200);
    });
}

// Initialisation des tooltips
function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');

    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

// Affichage des tooltips
function showTooltip(event) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = event.target.getAttribute('data-tooltip');
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
    `;

    document.body.appendChild(tooltip);

    const rect = event.target.getBoundingClientRect();
    tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
    tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';

    setTimeout(() => {
        tooltip.style.opacity = '1';
    }, 10);

    event.target._tooltip = tooltip;
}

// Masquage des tooltips
function hideTooltip(event) {
    if (event.target._tooltip) {
        event.target._tooltip.remove();
        delete event.target._tooltip;
    }
}

// Initialisation des graphiques (simulation)
function initializeCharts() {
    // Simulation de graphiques avec des barres de progression
    const progressBars = document.querySelectorAll('.progress-fill');

    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';

        setTimeout(() => {
            bar.style.transition = 'width 1s ease-out';
            bar.style.width = width;
        }, 500);
    });
}

// Initialisation des filtres
function initializeFilters() {
    // Filtre pour les écoles
    const schoolFilter = document.getElementById('schoolFilter');
    if (schoolFilter) {
        schoolFilter.addEventListener('change', filterSchools);
    }

    // Filtre pour l'activité récente
    const activityFilter = document.getElementById('activityFilter');
    if (activityFilter) {
        activityFilter.addEventListener('change', filterActivity);
    }
}

// Filtrage des écoles
function filterSchools(event) {
    const filterValue = event.target.value.toLowerCase();
    const schoolItems = document.querySelectorAll('.school-item');

    schoolItems.forEach(item => {
        const schoolName = item.querySelector('h4').textContent.toLowerCase();
        if (schoolName.includes(filterValue) || filterValue === '') {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// Filtrage de l'activité récente
function filterActivity(event) {
    const filterValue = event.target.value;
    const activityItems = document.querySelectorAll('.activity-item');

    activityItems.forEach(item => {
        const activityType = item.querySelector('.activity-icon').classList.contains('green') ? 'entree' : 'sortie';

        if (filterValue === 'all' || activityType === filterValue) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

// Initialisation des notifications
function initializeNotifications() {
    // Notification pour les inscriptions en retard
    const delayedRegistrations = document.querySelector('.delayed-registrations');
    if (delayedRegistrations) {
        const actionBtn = delayedRegistrations.querySelector('.action-btn');
        if (actionBtn) {
            actionBtn.addEventListener('click', handleDelayedRegistrations);
        }
    }

    // Notification pour les paiements en attente
    const pendingPayments = document.querySelectorAll('.amount-due');
    pendingPayments.forEach(payment => {
        payment.addEventListener('click', handlePendingPayment);
    });
}

// Gestion des inscriptions en retard
function handleDelayedRegistrations() {
    showNotification('Traitement des inscriptions en retard...', 'info');

    // Simulation d'action
    setTimeout(() => {
        showNotification('Actions appliquées avec succès', 'success');
    }, 2000);
}

// Gestion des paiements en attente
function handlePendingPayment(event) {
    const amount = event.target.textContent;
    showNotification(`Traitement du paiement: ${amount}`, 'info');
}

// Affichage des notifications
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
        transition: 'all 0.3s ease'
    };

    // Couleurs selon le type
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

// Fonction d'export des données
function exportData(format = 'pdf') {
    showNotification(`Export ${format.toUpperCase()} en cours...`, 'info');

    // Simulation d'export
    setTimeout(() => {
        showNotification(`Export ${format.toUpperCase()} terminé`, 'success');
    }, 2000);
}

// Fonction de rafraîchissement des données
function refreshData() {
    showNotification('Actualisation des données...', 'info');

    // Animation de rafraîchissement
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.style.opacity = '0.7';
    });

    setTimeout(() => {
        cards.forEach(card => {
            card.style.opacity = '1';
        });
        showNotification('Données actualisées', 'success');
    }, 1000);
}

// Gestion des clics sur les cartes KPI
document.addEventListener('click', function (event) {
    const kpiCard = event.target.closest('.kpi-card');
    if (kpiCard) {
        const kpiType = kpiCard.querySelector('p').textContent.toLowerCase();
        showKPIDetails(kpiType);
    }
});

// Affichage des détails d'un KPI
function showKPIDetails(kpiType) {
    const details = {
        'écoles actives': 'Détails des écoles actives et leur statut',
        'total élèves': 'Répartition des élèves par établissement',
        'revenus totaux': 'Détail des revenus par source',
        'en attente': 'Liste des paiements en attente'
    };

    showNotification(details[kpiType] || 'Détails non disponibles', 'info');
}

// Gestion du responsive
function handleResize() {
    const mainGrid = document.querySelector('.main-grid');
    if (window.innerWidth < 1200) {
        mainGrid.style.gridTemplateColumns = '1fr';
    } else {
        mainGrid.style.gridTemplateColumns = '2fr 1fr';
    }
}

window.addEventListener('resize', handleResize);

// Initialisation au chargement
handleResize();

// Fonctions utilitaires
function formatCurrency(amount) {
    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency: 'XOF',
        minimumFractionDigits: 0
    }).format(amount);
}

function formatNumber(number) {
    return new Intl.NumberFormat('fr-FR').format(number);
}

// Export des fonctions pour utilisation externe
window.DashboardComptable = {
    exportData,
    refreshData,
    showNotification,
    formatCurrency,
    formatNumber
};
