// Mise à Jour des Statuts de Factures - JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Animation des cartes de statistiques
    animateStatsCards();
    
    // Auto-refresh des statistiques toutes les 30 secondes
    setInterval(updateStats, 30000);
    
    // Gestion des confirmations
    setupConfirmations();
});

function animateStatsCards() {
    const statCards = document.querySelectorAll('.stat-card');
    
    statCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

function updateStats() {
    // Optionnel: Actualiser les statistiques via AJAX
    // Pour l'instant, on recharge la page
    console.log('Mise à jour des statistiques...');
}

function setupConfirmations() {
    const updateButton = document.querySelector('.action-form button[type="submit"]');
    
    if (updateButton) {
        updateButton.addEventListener('click', function(e) {
            if (!confirm('Êtes-vous sûr de vouloir mettre à jour tous les statuts de factures ?\n\nCette action va analyser toutes les dates d\'échéance et mettre à jour les statuts automatiquement.')) {
                e.preventDefault();
            }
        });
    }
}

// Fonction pour afficher les détails d'une facture
function showFactureDetails(factureId) {
    // Rediriger vers les détails de la facture
    window.open(`/school_admin/details_financiers_etablissement/${factureId}/`, '_blank');
}

// Fonction pour exporter les statistiques
function exportStats() {
    const stats = {
        en_attente: document.querySelector('.stat-card.en-attente h3').textContent,
        en_retard: document.querySelector('.stat-card.en-retard h3').textContent,
        impaye: document.querySelector('.stat-card.impaye h3').textContent,
        contentieux: document.querySelector('.stat-card.contentieux h3').textContent,
        paye: document.querySelector('.stat-card.paye h3').textContent
    };
    
    const csvContent = `Statut,Nombre\nEn Attente,${stats.en_attente}\nEn Retard,${stats.en_retard}\nImpayé,${stats.impaye}\nContentieux,${stats.contentieux}\nPayé,${stats.paye}`;
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `statuts_factures_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
}

// Fonction pour afficher les logs de mise à jour
function showUpdateLogs() {
    // Optionnel: Afficher les logs de la dernière mise à jour
    alert('Fonctionnalité de logs en cours de développement');
}

// Gestion des erreurs
window.addEventListener('error', function(e) {
    console.error('Erreur JavaScript:', e.error);
});

// Gestion des messages de succès/erreur
function showMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    messageDiv.innerHTML = `
        <div class="message-icon">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        </div>
        <div class="message-content">
            <div class="message-text">${message}</div>
        </div>
        <button type="button" class="message-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    document.body.appendChild(messageDiv);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (messageDiv.parentElement) {
            messageDiv.remove();
        }
    }, 5000);
}
