/**
 * Gestion des Élèves - JavaScript
 * Fonctionnalités pour la page de gestion des élèves
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de gestion des élèves chargée');
    
    // Initialiser les interactions
    initializeNavigationCards();
    initializeMainNavCard();
    initializeActionItems();
    animateCardsOnLoad();
});

/**
 * Initialiser les interactions des cartes de navigation
 */
function initializeNavigationCards() {
    const navCards = document.querySelectorAll('.nav-link-card');
    
    navCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
            this.style.boxShadow = 'var(--shadow-md)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'var(--shadow-sm)';
        });
        
        card.addEventListener('click', function(e) {
            // Animation de clic
            this.style.transform = 'scale(0.98)';
            setTimeout(() => {
                this.style.transform = 'translateY(-3px)';
            }, 150);
        });
    });
}

/**
 * Animer les cartes au chargement - DÉSACTIVÉ
 */
function animateCardsOnLoad() {
    const statCards = document.querySelectorAll('.stat-card');
    const navCards = document.querySelectorAll('.nav-link-card');
    
    // Pas d'animation d'apparition pour les cartes de statistiques
    statCards.forEach((card) => {
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
    });
    
    // Pas d'animation d'apparition pour les cartes de navigation
    navCards.forEach((card) => {
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
    });
}

/**
 * Initialiser la carte de navigation principale
 */
function initializeMainNavCard() {
    const mainNavCard = document.querySelector('.main-nav-link');
    
    if (mainNavCard) {
        mainNavCard.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
            this.style.boxShadow = 'var(--shadow-lg)';
        });
        
        mainNavCard.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'var(--shadow-sm)';
        });
    }
}

/**
 * Initialiser les éléments d'action
 */
function initializeActionItems() {
    const actionItems = document.querySelectorAll('.action-item');
    
    actionItems.forEach((item) => {
        // Pas d'animation d'apparition
        item.style.opacity = '1';
        item.style.transform = 'translateX(0)';
        
        // Ajouter un effet de clic
        item.addEventListener('click', function() {
            console.log('Action cliquée:', this.querySelector('.action-text').textContent);
            // Ajouter ici la logique pour afficher les détails de l'action
        });
    });
}

/**
 * Afficher un message temporaire
 */
function showTemporaryMessage(message, type = 'info') {
    // Créer l'élément de message
    const messageEl = document.createElement('div');
    messageEl.className = `temp-message temp-message-${type}`;
    messageEl.textContent = message;
    
    // Styles du message
    const bgColor = type === 'info' ? '#3b82f6' : '#ef4444';
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${bgColor};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        font-weight: 500;
        animation: slideIn 0.3s ease;
    `;
    
    // Ajouter l'animation CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
    
    // Ajouter au DOM
    document.body.appendChild(messageEl);
    
    // Supprimer après 3 secondes
    setTimeout(() => {
        messageEl.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.parentNode.removeChild(messageEl);
            }
        }, 300);
    }, 3000);
}

/**
 * Initialiser les interactions des cartes de navigation
 */
function initializeNavigationCardInteractions() {
    const navCards = document.querySelectorAll('.nav-link-card');
    navCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
            this.style.boxShadow = 'var(--shadow-md)';
        });
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'var(--shadow-sm)';
        });
    });
}

/**
 * Initialiser les interactions des boutons d'actions rapides
 */
function initializeQuickActionButtons() {
    const quickActionBtns = document.querySelectorAll('.quick-action-btn');
    quickActionBtns.forEach(btn => {
        btn.addEventListener('click', function(event) {
            console.log('Action rapide cliquée:', this.querySelector('span').textContent);
            // Ajouter ici la logique spécifique à chaque action rapide
        });
    });
}

/**
 * Initialiser les interactions des éléments d'activité récente
 */
function initializeActivityItems() {
    const activityItems = document.querySelectorAll('.activity-item');
    activityItems.forEach(item => {
        item.addEventListener('click', function() {
            console.log('Activité récente cliquée:', this.querySelector('.activity-text').textContent);
            // Ajouter ici la logique pour afficher les détails de l'activité
        });
    });
}

/**
 * Initialiser les interactions des cartes de notification
 */
function initializeNotificationCards() {
    const notificationCards = document.querySelectorAll('.notification-card');
    notificationCards.forEach(card => {
        card.addEventListener('click', function() {
            console.log('Notification cliquée:', this.querySelector('h3').textContent);
            // Ajouter ici la logique pour gérer la notification
        });
    });
}
