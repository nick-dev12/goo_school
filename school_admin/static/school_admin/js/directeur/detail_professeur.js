// ===================================
// SCRIPT POUR LA PAGE DE DÉTAIL PROFESSEUR
// ===================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de détail professeur chargée');
    
    // Animation d'apparition des cartes
    animateCards();
    
    // Gestion de l'impression
    setupPrintHandler();
    
    // Gestion des tooltips
    setupTooltips();
    
    // Animation du badge de statut
    animateStatusBadge();
});

/**
 * Animation d'apparition progressive des cartes
 */
function animateCards() {
    const cards = document.querySelectorAll('.detail-card');
    
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

/**
 * Configuration du gestionnaire d'impression
 */
function setupPrintHandler() {
    // Écouter l'événement avant impression
    window.addEventListener('beforeprint', function() {
        console.log('Impression en cours...');
        
        // Masquer les éléments non nécessaires
        const elementsToHide = document.querySelectorAll('.btn-action, .header-actions, .actions-footer');
        elementsToHide.forEach(element => {
            element.style.display = 'none';
        });
    });
    
    // Écouter l'événement après impression
    window.addEventListener('afterprint', function() {
        console.log('Impression terminée');
        
        // Réafficher les éléments
        const elementsToShow = document.querySelectorAll('.btn-action, .header-actions, .actions-footer');
        elementsToShow.forEach(element => {
            element.style.display = '';
        });
    });
}

/**
 * Configuration des tooltips pour les icônes
 */
function setupTooltips() {
    const icons = document.querySelectorAll('.info-label i');
    
    icons.forEach(icon => {
        icon.addEventListener('mouseenter', function(e) {
            const label = this.parentElement.querySelector('span');
            if (label) {
                // Créer un tooltip simple
                const tooltip = document.createElement('div');
                tooltip.className = 'custom-tooltip';
                tooltip.textContent = label.textContent;
                tooltip.style.cssText = `
                    position: absolute;
                    background: rgba(0, 0, 0, 0.8);
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    pointer-events: none;
                    z-index: 1000;
                    white-space: nowrap;
                `;
                
                document.body.appendChild(tooltip);
                
                const rect = this.getBoundingClientRect();
                tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
                tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
                
                this.tooltip = tooltip;
            }
        });
        
        icon.addEventListener('mouseleave', function() {
            if (this.tooltip) {
                this.tooltip.remove();
                delete this.tooltip;
            }
        });
    });
}

/**
 * Animation du badge de statut
 */
function animateStatusBadge() {
    const statusDot = document.querySelector('.status-dot');
    
    if (statusDot) {
        // Animation de pulsation
        setInterval(() => {
            statusDot.style.transform = 'scale(1.2)';
            setTimeout(() => {
                statusDot.style.transform = 'scale(1)';
            }, 500);
        }, 2000);
    }
}

/**
 * Animation au survol des cartes de classe
 */
const classeItems = document.querySelectorAll('.classe-item');

classeItems.forEach(item => {
    item.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-4px) scale(1.02)';
    });
    
    item.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0) scale(1)';
    });
});

/**
 * Gestion du bouton de retour avec animation
 */
const backButton = document.querySelector('.btn-back');

if (backButton) {
    backButton.addEventListener('click', function(e) {
        e.preventDefault();
        
        // Animation de sortie
        const mainContent = document.querySelector('.main-content-container');
        mainContent.style.transition = 'all 0.3s ease-out';
        mainContent.style.opacity = '0';
        mainContent.style.transform = 'translateX(-50px)';
        
        // Redirection après l'animation
        setTimeout(() => {
            window.location.href = this.href;
        }, 300);
    });
}

/**
 * Effet de survol sur les badges
 */
const badges = document.querySelectorAll('.badge-matiere, .badge-niveau, .badge-employee');

badges.forEach(badge => {
    badge.addEventListener('mouseenter', function() {
        this.style.transform = 'scale(1.05)';
        this.style.transition = 'transform 0.2s ease';
    });
    
    badge.addEventListener('mouseleave', function() {
        this.style.transform = 'scale(1)';
    });
});

/**
 * Animation des cartes au défilement
 */
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observer toutes les cartes
document.querySelectorAll('.detail-card').forEach(card => {
    observer.observe(card);
});

/**
 * Gestion du clic sur les liens email et téléphone
 */
const emailLinks = document.querySelectorAll('.link-email');
const phoneLinks = document.querySelectorAll('.link-phone');

emailLinks.forEach(link => {
    link.addEventListener('click', function(e) {
        console.log('Ouverture du client email:', this.textContent);
    });
});

phoneLinks.forEach(link => {
    link.addEventListener('click', function(e) {
        console.log('Appel téléphonique:', this.textContent);
    });
});

/**
 * Fonction pour copier les informations dans le presse-papiers
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Afficher un message de confirmation
        showNotification('Copié dans le presse-papiers!', 'success');
    }).catch(err => {
        console.error('Erreur lors de la copie:', err);
        showNotification('Erreur lors de la copie', 'error');
    });
}

/**
 * Afficher une notification temporaire
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    // Retirer la notification après 3 secondes
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// Ajouter les animations CSS pour les notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

/**
 * Log pour le débogage
 */
console.log('Scripts de la page de détail professeur initialisés avec succès');

