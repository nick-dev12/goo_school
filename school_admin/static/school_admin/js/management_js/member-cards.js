/**
 * Module de création de cartes de membre
 * 
 * Ce module gère la création et l'affichage des cartes de membres d'équipe.
 * Il fournit des fonctionnalités pour créer dynamiquement des cartes de membre
 * et les ajouter à l'interface.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const teamGrid = document.getElementById('teamGrid');

    // Fonction pour obtenir le nom traduit d'un département
    function getDepartmentName(department) {
        const departments = {
            'sales': 'Ventes',
            'tech': 'Technique',
            'finance': 'Finance',
            'hr': 'Ressources humaines',
            'marketing': 'Marketing'
        };
        return departments[department] || department;
    }

    // Fonction pour créer une nouvelle carte de membre
    function createMemberCard(memberData) {
        // Créer les initiales du membre
        const initials = memberData.firstName.charAt(0) + memberData.lastName.charAt(0);

        // Créer l'élément de carte
        const memberCard = document.createElement('div');
        memberCard.className = 'member-card';
        memberCard.setAttribute('data-role', memberData.role);
        memberCard.setAttribute('data-status', 'active');
        memberCard.setAttribute('data-department', memberData.department);

        // Définir le contenu HTML de la carte
        memberCard.innerHTML = `
            <div class="member-header">
                <div class="member-avatar">${initials}</div>
                <div class="member-status active"></div>
            </div>
            <div class="member-info">
                <h3 class="member-name">${memberData.firstName} ${memberData.lastName}</h3>
                <div class="member-role ${memberData.role}">${memberData.jobTitle || memberData.role}</div>
                <div class="member-department">Département ${getDepartmentName(memberData.department)}</div>
            </div>
            <div class="member-details">
                <div class="detail-item">
                    <i class="fas fa-envelope"></i>
                    <span>${memberData.email}</span>
                </div>
                <div class="detail-item">
                    <i class="fas fa-phone"></i>
                    <span>${memberData.phone || 'Non renseigné'}</span>
                </div>
                <div class="detail-item">
                    <i class="fas fa-calendar"></i>
                    <span>Nouveau membre</span>
                </div>
            </div>
            <div class="member-actions">
                <button class="action-btn edit" title="Modifier"><i class="fas fa-edit"></i></button>
                <button class="action-btn message" title="Contacter"><i class="fas fa-envelope"></i></button>
                <button class="action-btn more" title="Plus d'options"><i class="fas fa-ellipsis-v"></i></button>
            </div>
        `;

        // Ajouter la carte à la grille
        teamGrid.appendChild(memberCard);

        // Ajouter une animation d'apparition
        setTimeout(() => {
            memberCard.style.animation = 'fadeIn 0.5s ease forwards';
        }, 100);

        // Mettre à jour les statistiques après l'ajout d'un membre
        if (window.statisticsFunctions && window.statisticsFunctions.update) {
            window.statisticsFunctions.update();
        }

        // Configurer les actions sur cette nouvelle carte
        if (window.memberActionFunctions && window.memberActionFunctions.setupActions) {
            // Attendre que le DOM soit mis à jour
            setTimeout(() => {
                window.memberActionFunctions.setupActions();
            }, 100);
        }

        return memberCard;
    }

    // Fonction pour supprimer une carte de membre
    function removeMemberCard(card) {
        if (card && card.parentNode) {
            // Ajouter une animation de disparition
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';

            // Supprimer l'élément après l'animation
            setTimeout(() => {
                card.parentNode.removeChild(card);
                // Mettre à jour les statistiques après la suppression
                if (window.statisticsFunctions && window.statisticsFunctions.update) {
                    window.statisticsFunctions.update();
                }
            }, 300);
        }
    }

    // Exposer les fonctions pour une utilisation externe
    window.memberCardFunctions = {
        create: createMemberCard,
        remove: removeMemberCard,
        getDepartmentName: getDepartmentName
    };
});