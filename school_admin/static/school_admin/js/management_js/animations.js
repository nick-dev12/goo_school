/**
 * Module d'animations
 * 
 * Ce module gère les animations et les effets visuels dans l'interface de gestion des équipes.
 * Il s'occupe des animations d'apparition des cartes, des effets de survol, etc.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const memberCards = document.querySelectorAll('.member-card');

    // Fonction pour ajouter les styles CSS nécessaires pour les animations
    function addAnimationStyles() {
        const style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }
            
            @keyframes slideIn {
                from { transform: translateX(-20px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            
            @keyframes fadeOut {
                from { opacity: 1; transform: translateY(0); }
                to { opacity: 0; transform: translateY(20px); }
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
                20%, 40%, 60%, 80% { transform: translateX(5px); }
            }
            
            .animate-fadeIn {
                animation: fadeIn 0.5s ease forwards;
            }
            
            .animate-pulse {
                animation: pulse 0.5s ease;
            }
            
            .animate-slideIn {
                animation: slideIn 0.3s ease forwards;
            }
            
            .animate-fadeOut {
                animation: fadeOut 0.5s ease forwards;
            }
            
            .animate-shake {
                animation: shake 0.5s ease;
            }
            
            .context-menu {
                background: var(--white);
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-lg);
                padding: 0.5rem 0;
                min-width: 180px;
                border: 1px solid var(--gray-200);
            }
            
            .context-menu-item {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.75rem 1rem;
                font-size: 0.9rem;
                color: var(--text-primary);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .context-menu-item:hover {
                background: var(--gray-50);
            }
            
            .context-menu-item-danger {
                color: var(--warning);
            }
            
            .context-menu-item-danger:hover {
                background: var(--warning-light);
            }
            
            .toast-error {
                border-left: 4px solid var(--warning);
            }
            
            .toast-warning {
                border-left: 4px solid #f9c74f;
            }
            
            .toast-info {
                border-left: 4px solid var(--admin-primary);
            }
            
            .toast-error .toast-icon {
                color: var(--warning);
            }
            
            .toast-warning .toast-icon {
                color: #f9c74f;
            }
            
            .toast-info .toast-icon {
                color: var(--admin-primary);
            }
        `;
        document.head.appendChild(style);
    }

    // Fonction pour initialiser les animations des cartes de membre
    function initializeCardAnimations() {
        // Ajouter une animation d'apparition progressive aux cartes existantes
        memberCards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'all 0.5s ease';

            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, index * 100); // Délai progressif pour un effet cascade
        });
    }

    // Fonction pour appliquer une animation à un élément
    function animateElement(element, animationType, duration = 500, callback) {
        // Supprimer toutes les classes d'animation existantes
        element.classList.remove(
            'animate-fadeIn',
            'animate-pulse',
            'animate-slideIn',
            'animate-fadeOut',
            'animate-shake'
        );

        // Appliquer la nouvelle animation
        element.classList.add(`animate-${animationType}`);

        // Configurer la durée de l'animation
        element.style.animationDuration = `${duration}ms`;

        // Exécuter le callback après l'animation si fourni
        if (callback) {
            setTimeout(callback, duration);
        }

        // Supprimer la classe d'animation après son exécution
        setTimeout(() => {
            element.classList.remove(`animate-${animationType}`);
        }, duration);
    }

    // Fonction pour animer l'apparition d'un élément
    function fadeIn(element, duration = 500, callback) {
        animateElement(element, 'fadeIn', duration, callback);
    }

    // Fonction pour animer la disparition d'un élément
    function fadeOut(element, duration = 500, callback) {
        animateElement(element, 'fadeOut', duration, callback);
    }

    // Fonction pour animer un effet de pulsation sur un élément
    function pulse(element, duration = 500, callback) {
        animateElement(element, 'pulse', duration, callback);
    }

    // Ajouter les styles CSS pour les animations
    addAnimationStyles();

    // Initialiser les animations des cartes
    initializeCardAnimations();

    // Exposer les fonctions pour une utilisation externe
    window.animationFunctions = {
        animate: animateElement,
        fadeIn: fadeIn,
        fadeOut: fadeOut,
        pulse: pulse
    };
});