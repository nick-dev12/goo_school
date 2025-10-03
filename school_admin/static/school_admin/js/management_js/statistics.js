/**
 * Module de statistiques
 * 
 * Ce module gère l'affichage et la mise à jour des statistiques de l'équipe,
 * comme le nombre de membres par rôle.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const memberCards = document.querySelectorAll('.member-card');
    const statCards = document.querySelectorAll('.stat-card');
    const exportTeamBtn = document.getElementById('exportTeam');

    // Fonction pour mettre à jour les statistiques de l'équipe
    function updateStatistics() {
        // Liste des rôles à comptabiliser
        const roles = ['commercial', 'developer', 'accountant', 'support', 'manager'];

        // Pour chaque rôle, compter le nombre de membres et mettre à jour la carte de statistiques
        roles.forEach((role, index) => {
            // Compter les membres ayant ce rôle
            const count = document.querySelectorAll(`[data-role="${role}"]`).length;

            // Récupérer l'élément d'affichage de la valeur dans la carte de statistiques
            const statValue = statCards[index]?.querySelector('.stat-value');

            // Mettre à jour la valeur avec une animation
            if (statValue) {
                statValue.textContent = count;
                statValue.style.animation = 'pulse 0.5s ease';

                // Réinitialiser l'animation après son exécution
                setTimeout(() => {
                    statValue.style.animation = '';
                }, 500);
            }
        });
    }

    // Fonction pour calculer les statistiques détaillées de l'équipe
    function calculateDetailedStats() {
        // Objet pour stocker les statistiques
        const stats = {
            totalMembers: 0,
            byRole: {},
            byDepartment: {},
            byStatus: {}
        };

        // Récupérer toutes les cartes de membre (elles peuvent avoir changé)
        const currentMemberCards = document.querySelectorAll('.member-card');

        // Parcourir toutes les cartes de membre
        currentMemberCards.forEach(card => {
            // Incrémenter le nombre total de membres
            stats.totalMembers++;

            // Récupérer les attributs de la carte
            const role = card.getAttribute('data-role');
            const department = card.getAttribute('data-department');
            const status = card.getAttribute('data-status');

            // Compter par rôle
            if (role) {
                stats.byRole[role] = (stats.byRole[role] || 0) + 1;
            }

            // Compter par département
            if (department) {
                stats.byDepartment[department] = (stats.byDepartment[department] || 0) + 1;
            }

            // Compter par statut
            if (status) {
                stats.byStatus[status] = (stats.byStatus[status] || 0) + 1;
            }
        });

        return stats;
    }

    // Fonction pour afficher les statistiques détaillées dans la console
    function logDetailedStats() {
        const stats = calculateDetailedStats();
        console.log('Statistiques détaillées de l\'équipe:', stats);

        // Afficher un toast avec le nombre total de membres
        if (window.toastFunctions && window.toastFunctions.show) {
            window.toastFunctions.show(`Équipe: ${stats.totalMembers} membres au total`, 'info');
        }
    }

    // Mettre à jour les statistiques initiales
    updateStatistics();

    // Ajouter un écouteur d'événement pour le bouton d'exportation
    if (exportTeamBtn) {
        exportTeamBtn.addEventListener('click', function () {
            logDetailedStats();
        });
    }

    // Exposer les fonctions pour une utilisation externe
    window.statisticsFunctions = {
        update: updateStatistics,
        calculate: calculateDetailedStats,
        log: logDetailedStats
    };
});