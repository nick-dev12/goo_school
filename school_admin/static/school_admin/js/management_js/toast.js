/**
 * Module de notifications toast
 * 
 * Ce module gère l'affichage des notifications toast dans l'interface.
 * Il permet d'afficher des messages de succès, d'erreur, d'avertissement ou d'information.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const toast = document.getElementById('toastNotification');
    const closeToast = document.getElementById('closeToast');
    let toastTimeout = null;

    // Fonction pour afficher une notification toast
    function showToast(message, type = 'success', duration = 7000) {
        // Récupérer les éléments de la notification
        const toastMessage = toast.querySelector('.toast-message');
        const toastIcon = toast.querySelector('.toast-icon');
        const toastTitle = toast.querySelector('.toast-title');

        // Définir le message
        toastMessage.textContent = message;

        // Définir le type et l'icône
        toast.className = 'toast';
        switch (type) {
            case 'success':
                toast.classList.add('toast-success');
                toastIcon.className = 'fas fa-check-circle toast-icon';
                toastTitle.textContent = 'Succès';
                break;
            case 'error':
                toast.classList.add('toast-error');
                toastIcon.className = 'fas fa-exclamation-circle toast-icon';
                toastTitle.textContent = 'Erreur';
                break;
            case 'warning':
                toast.classList.add('toast-warning');
                toastIcon.className = 'fas fa-exclamation-triangle toast-icon';
                toastTitle.textContent = 'Attention';
                break;
            case 'info':
                toast.classList.add('toast-info');
                toastIcon.className = 'fas fa-info-circle toast-icon';
                toastTitle.textContent = 'Information';
                break;
        }

        // Afficher la notification
        toast.classList.add('show');

        // Annuler tout délai d'expiration existant
        if (toastTimeout) {
            clearTimeout(toastTimeout);
        }

        // Masquer automatiquement la notification après la durée spécifiée
        toastTimeout = setTimeout(() => {
            hideToast();
        }, duration);
    }

    // Fonction pour masquer la notification toast
    function hideToast() {
        toast.classList.remove('show');
    }

    // Fonction pour créer et afficher une notification toast personnalisée
    function createCustomToast(message, type = 'success', duration = 7000) {
        // Créer le conteneur de notifications s'il n'existe pas
        let container = document.querySelector('.notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'notifications-container';
            document.body.appendChild(container);
        }

        // Déterminer le titre et l'icône en fonction du type
        let title, iconClass;
        switch (type) {
            case 'success':
                title = 'Succès';
                iconClass = 'fas fa-check-circle';
                break;
            case 'error':
                title = 'Erreur';
                iconClass = 'fas fa-exclamation-circle';
                break;
            case 'warning':
                title = 'Attention';
                iconClass = 'fas fa-exclamation-triangle';
                break;
            case 'info':
                title = 'Information';
                iconClass = 'fas fa-info-circle';
                break;
        }

        // Créer l'élément de notification
        const customToast = document.createElement('div');
        customToast.className = `toast toast-${type}`;
        customToast.innerHTML = `
            <div class="toast-icon">
                <i class="${iconClass}"></i>
            </div>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Ajouter la notification au conteneur
        container.appendChild(customToast);

        // Afficher la notification avec un délai pour permettre l'animation
        setTimeout(() => {
            customToast.classList.add('show');
        }, 10);

        // Configurer le bouton de fermeture
        const closeBtn = customToast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => {
            customToast.classList.remove('show');
            setTimeout(() => {
                container.removeChild(customToast);
            }, 300);
        });

        // Masquer automatiquement la notification après la durée spécifiée
        setTimeout(() => {
            if (customToast.parentNode) {
                customToast.classList.remove('show');
                setTimeout(() => {
                    if (customToast.parentNode) {
                        container.removeChild(customToast);
                    }
                }, 300);
            }
        }, duration);

        return customToast;
    }

    // Configurer l'écouteur d'événement pour fermer la notification
    closeToast.addEventListener('click', hideToast);

    // Exposer les fonctions pour une utilisation externe
    window.toastFunctions = {
        show: showToast,
        hide: hideToast,
        createCustom: createCustomToast
    };
});