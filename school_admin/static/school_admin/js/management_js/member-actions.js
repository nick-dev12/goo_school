/**
 * Module d'actions sur les membres
 * 
 * Ce module gère les actions disponibles sur les cartes de membres d'équipe,
 * comme l'édition, l'envoi de messages, et les options avancées via un menu contextuel.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const memberCards = document.querySelectorAll('.member-card');
    const actionBtns = document.querySelectorAll('.action-btn');

    // Fonction pour configurer les actions sur les boutons
    function setupMemberActions() {
        actionBtns.forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();

                const memberCard = this.closest('.member-card');
                const memberName = memberCard.querySelector('.member-name').textContent;

                if (this.classList.contains('edit')) {
                    // Action d'édition
                    window.toastFunctions.show(`Modification du profil de ${memberName}`, 'info');
                    // Dans une vraie application, cela ouvrirait un modal d'édition
                } else if (this.classList.contains('message')) {
                    // Action d'envoi de message
                    window.toastFunctions.show(`Envoi d'un message à ${memberName}`, 'info');
                    // Dans une vraie application, cela ouvrirait une interface de messagerie
                } else if (this.classList.contains('more')) {
                    // Afficher le menu contextuel
                    showContextMenu(this, memberName);
                }
            });
        });
    }

    // Fonction pour afficher un menu contextuel
    function showContextMenu(btn, memberName) {
        // Supprimer tout menu contextuel existant
        const existingMenu = document.querySelector('.context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        // Créer un nouveau menu contextuel
        const contextMenu = document.createElement('div');
        contextMenu.className = 'context-menu';
        contextMenu.innerHTML = `
            <div class="context-menu-item" data-action="view">
                <i class="fas fa-eye"></i> Voir le profil
            </div>
            <div class="context-menu-item" data-action="permissions">
                <i class="fas fa-key"></i> Gérer les permissions
            </div>
            <div class="context-menu-item" data-action="deactivate">
                <i class="fas fa-user-slash"></i> Désactiver
            </div>
            <div class="context-menu-item context-menu-item-danger" data-action="delete">
                <i class="fas fa-trash"></i> Supprimer
            </div>
        `;

        // Positionner le menu
        const rect = btn.getBoundingClientRect();
        contextMenu.style.position = 'fixed';
        contextMenu.style.top = rect.bottom + 5 + 'px';
        contextMenu.style.left = rect.left + 'px';
        contextMenu.style.zIndex = '1002';

        document.body.appendChild(contextMenu);

        // Ajouter des écouteurs d'événements aux éléments du menu
        contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
            item.addEventListener('click', function () {
                const action = this.getAttribute('data-action');
                handleContextMenuAction(action, memberName);
                contextMenu.remove();
            });
        });

        // Fermer le menu lors d'un clic en dehors
        document.addEventListener('click', function (e) {
            if (!contextMenu.contains(e.target)) {
                contextMenu.remove();
            }
        }, { once: true });
    }

    // Fonction pour gérer les actions du menu contextuel
    function handleContextMenuAction(action, memberName) {
        switch (action) {
            case 'view':
                window.toastFunctions.show(`Affichage du profil de ${memberName}`, 'info');
                break;
            case 'permissions':
                window.toastFunctions.show(`Gestion des permissions de ${memberName}`, 'info');
                break;
            case 'deactivate':
                if (confirm(`Êtes-vous sûr de vouloir désactiver ${memberName} ?`)) {
                    window.toastFunctions.show(`${memberName} a été désactivé`, 'warning');
                }
                break;
            case 'delete':
                if (confirm(`Êtes-vous sûr de vouloir supprimer ${memberName} de l'équipe ?`)) {
                    window.toastFunctions.show(`${memberName} a été supprimé de l'équipe`, 'error');
                }
                break;
        }
    }

    // Initialiser les actions sur les membres
    setupMemberActions();

    // Exposer les fonctions pour une utilisation externe
    window.memberActionFunctions = {
        setupActions: setupMemberActions,
        showContextMenu: showContextMenu,
        handleAction: handleContextMenuAction
    };
});