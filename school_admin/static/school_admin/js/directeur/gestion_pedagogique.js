/**
 * Gestion Pédagogique - JavaScript
 * Fonctionnalités pour la page de gestion pédagogique
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de gestion pédagogique chargée');
    
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
        // Effet de survol amélioré
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
            this.style.boxShadow = 'var(--shadow-md)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'none';
        });
        
        // Animation au clic
        card.addEventListener('click', function(e) {
            // Si c'est un lien vers une page en développement
            if (this.getAttribute('href') === '#') {
                e.preventDefault();
                
                this.style.transform = 'translateY(-1px) scale(0.98)';
                setTimeout(() => {
                    this.style.transform = 'translateY(-3px) scale(1)';
                }, 150);
                
                // Afficher un message temporaire
                const title = this.querySelector('h3').textContent;
                showTemporaryMessage(`${title} - Fonctionnalité en cours de développement`, 'info');
            }
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
    const bgColor = type === 'info' ? 'var(--primary)' : 'var(--accent)';
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${bgColor};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: var(--radius);
        box-shadow: var(--shadow-lg);
        z-index: 1000;
        font-weight: 600;
        transform: translateX(100%);
        transition: transform 0.3s ease;
        max-width: 300px;
    `;
    
    // Ajouter au DOM
    document.body.appendChild(messageEl);
    
    // Animer l'entrée
    setTimeout(() => {
        messageEl.style.transform = 'translateX(0)';
    }, 100);
    
    // Supprimer après 3 secondes
    setTimeout(() => {
        messageEl.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.parentNode.removeChild(messageEl);
            }
        }, 300);
    }, 3000);
}

/**
 * Gérer les erreurs JavaScript
 */
window.addEventListener('error', function(e) {
    console.error('Erreur JavaScript:', e.error);
    showTemporaryMessage('Une erreur est survenue', 'error');
});

/**
 * Gérer les clics sur les boutons d'action
 */
document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-primary')) {
        const btn = e.target.closest('.btn-primary');
        const action = btn.textContent.trim();
        
        // Animation de clic
        btn.style.transform = 'scale(0.95)';
        setTimeout(() => {
            btn.style.transform = 'scale(1)';
        }, 150);
        
        // Log de l'action
        console.log('Action cliquée:', action);
    }
});