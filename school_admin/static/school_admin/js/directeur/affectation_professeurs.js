/**
 * JavaScript pour la page d'affectation des professeurs
 * Utilisé uniquement pour les animations et interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page d\'affectation des professeurs chargée');
    
    // Initialiser les onglets de matière
    initializeMatiereTabs();
    
    // Initialiser les interactions des cartes
    initializeProfessorCards();
});

/**
 * Initialiser les onglets de matière
 */
function initializeMatiereTabs() {
    const tabButtons = document.querySelectorAll('.matiere-tab-btn');
    const professorCards = document.querySelectorAll('.professor-card');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const matiereId = this.getAttribute('data-matiere');
            
            // Mettre à jour l'état actif des onglets
            tabButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Filtrer les cartes de professeurs
            professorCards.forEach(card => {
                const cardMatiere = card.getAttribute('data-matiere');
                
                if (matiereId === 'all' || cardMatiere === matiereId) {
                    card.style.display = 'block';
                    card.style.animation = 'fadeIn 0.3s ease-in-out';
                } else {
                    card.style.display = 'none';
                }
            });
            
            // Mettre à jour le compteur
            updateFilteredCount();
        });
    });
}

/**
 * Initialiser les interactions des cartes de professeurs
 */
function initializeProfessorCards() {
    // Ajouter des effets de survol
    const professorCards = document.querySelectorAll('.professor-card');
    professorCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 8px 25px rgba(0, 0, 0, 0.15)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 4px 15px rgba(0, 0, 0, 0.1)';
        });
    });
}

/**
 * Toggle l'affichage du panneau d'affectations
 */
function toggleAffectations(professeurId) {
    const panel = document.getElementById(`affectationsPanel${professeurId}`);
    if (panel) {
        if (panel.style.display === 'none' || panel.style.display === '') {
            panel.style.display = 'block';
            panel.style.animation = 'slideDown 0.3s ease-in-out';
        } else {
            panel.style.animation = 'slideUp 0.3s ease-in-out';
            setTimeout(() => {
                panel.style.display = 'none';
            }, 300);
        }
    }
}

/**
 * Mettre à jour le compteur de professeurs filtrés
 */
function updateFilteredCount() {
    const activeTab = document.querySelector('.matiere-tab-btn.active');
    const matiereId = activeTab ? activeTab.getAttribute('data-matiere') : 'all';
    
    let visibleCount = 0;
    const professorCards = document.querySelectorAll('.professor-card');
    
    professorCards.forEach(card => {
        if (card.style.display !== 'none') {
            visibleCount++;
        }
    });
    
    // Mettre à jour le compteur dans l'onglet actif
    const countElement = activeTab.querySelector('.tab-count');
    if (countElement) {
        countElement.textContent = visibleCount;
    }
}

/**
 * Afficher un message temporaire
 */
function showTemporaryMessage(message, type = 'info') {
    // Créer l'élément de message
    const messageDiv = document.createElement('div');
    messageDiv.className = `temporary-message message-${type}`;
    messageDiv.textContent = message;
    
    // Styles pour le message
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        animation: slideInRight 0.3s ease-out;
        max-width: 300px;
        word-wrap: break-word;
    `;
    
    // Couleurs selon le type
    if (type === 'success') {
        messageDiv.style.backgroundColor = '#10b981';
    } else if (type === 'error') {
        messageDiv.style.backgroundColor = '#ef4444';
    } else if (type === 'warning') {
        messageDiv.style.backgroundColor = '#f59e0b';
    } else {
        messageDiv.style.backgroundColor = '#3b82f6';
    }
    
    // Ajouter au DOM
    document.body.appendChild(messageDiv);
    
    // Supprimer après 3 secondes
    setTimeout(() => {
        messageDiv.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 300);
    }, 3000);
}

/**
 * Animation de fade in
 */
const fadeInKeyframes = `
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
`;

/**
 * Animation de slide down
 */
const slideDownKeyframes = `
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
`;

/**
 * Animation de slide up
 */
const slideUpKeyframes = `
@keyframes slideUp {
    from { opacity: 1; transform: translateY(0); }
    to { opacity: 0; transform: translateY(-10px); }
}
`;

/**
 * Animation de slide in right
 */
const slideInRightKeyframes = `
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(100%); }
    to { opacity: 1; transform: translateX(0); }
}
`;

/**
 * Animation de slide out right
 */
const slideOutRightKeyframes = `
@keyframes slideOutRight {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(100%); }
}
`;

// Ajouter les animations CSS au document
const style = document.createElement('style');
style.textContent = fadeInKeyframes + slideDownKeyframes + slideUpKeyframes + slideInRightKeyframes + slideOutRightKeyframes;
document.head.appendChild(style);