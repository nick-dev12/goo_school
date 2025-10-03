/**
 * Module de filtrage et recherche
 * 
 * Ce module gère le filtrage et la recherche des membres d'équipe dans l'interface.
 * Il permet de filtrer les membres par nom, rôle, statut et département.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const searchInput = document.getElementById('searchInput');
    const roleFilter = document.getElementById('roleFilter');
    const statusFilter = document.getElementById('statusFilter');
    const departmentFilter = document.getElementById('departmentFilter');
    const memberCards = document.querySelectorAll('.member-card');

    // Fonction pour filtrer les membres d'équipe
    function filterMembers() {
        // Récupérer les valeurs des filtres
        const searchTerm = searchInput.value.toLowerCase();
        const selectedRole = roleFilter.value;
        const selectedStatus = statusFilter.value;
        const selectedDepartment = departmentFilter.value;

        // Parcourir toutes les cartes de membre
        memberCards.forEach(card => {
            // Récupérer les informations du membre
            const memberName = card.querySelector('.member-name').textContent.toLowerCase();
            const memberEmail = card.querySelector('.detail-item span').textContent.toLowerCase();
            const cardRole = card.getAttribute('data-role');
            const cardStatus = card.getAttribute('data-status');
            const cardDepartment = card.getAttribute('data-department');

            // Vérifier si le membre correspond aux critères de recherche et de filtrage
            const matchesSearch = memberName.includes(searchTerm) || memberEmail.includes(searchTerm);
            const matchesRole = !selectedRole || cardRole.toLowerCase() === selectedRole.toLowerCase();
            const matchesStatus = !selectedStatus || cardStatus === selectedStatus;
            const matchesDepartment = !selectedDepartment || cardDepartment.toLowerCase() === selectedDepartment.toLowerCase();

            // Afficher ou masquer la carte en fonction des critères
            if (matchesSearch && matchesRole && matchesStatus && matchesDepartment) {
                card.style.display = 'block';
                card.style.animation = 'fadeIn 0.3s ease forwards';
            } else {
                card.style.display = 'none';
            }
        });
    }

    // Fonction pour réinitialiser tous les filtres
    function resetFilters() {
        searchInput.value = '';
        roleFilter.value = '';
        statusFilter.value = '';
        departmentFilter.value = '';
        filterMembers();
    }

    // Configurer les écouteurs d'événements pour les filtres
    searchInput.addEventListener('input', filterMembers);
    roleFilter.addEventListener('change', filterMembers);
    statusFilter.addEventListener('change', filterMembers);
    departmentFilter.addEventListener('change', filterMembers);

    // Exposer les fonctions pour une utilisation externe
    window.filterFunctions = {
        filter: filterMembers,
        reset: resetFilters
    };
});

/**
 * Module de filtrage des activités globales
 * 
 * Ce module gère le filtrage des activités dans l'onglet "Activités globales"
 */
document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM pour les filtres d'activités
    const activityTypeFilter = document.getElementById('activityTypeFilter');
    const activityCommercialFilter = document.getElementById('activityCommercialFilter');
    const timelineItems = document.querySelectorAll('.timeline-item');

    // Fonction pour filtrer les activités
    function filterActivities() {
        // Récupérer les valeurs des filtres
        const selectedType = activityTypeFilter ? activityTypeFilter.value : '';
        const selectedCommercial = activityCommercialFilter ? activityCommercialFilter.value : '';

        // Parcourir toutes les activités
        timelineItems.forEach(item => {
            const activityType = item.getAttribute('data-type');
            const activityCommercial = item.getAttribute('data-commercial');

            // Vérifier si l'activité correspond aux critères de filtrage
            const matchesType = !selectedType || activityType === selectedType;
            const matchesCommercial = !selectedCommercial || activityCommercial === selectedCommercial;

            // Afficher ou masquer l'activité en fonction des critères
            if (matchesType && matchesCommercial) {
                item.style.display = 'flex';
                item.style.animation = 'fadeIn 0.3s ease forwards';
            } else {
                item.style.display = 'none';
            }
        });

        // Mettre à jour le compteur d'activités visibles
        updateActivityCount();
    }

    // Fonction pour mettre à jour le compteur d'activités
    function updateActivityCount() {
        const visibleActivities = document.querySelectorAll('.timeline-item[style*="flex"], .timeline-item:not([style*="none"])');
        const countBadge = document.querySelector('.count-badge');

        if (countBadge) {
            countBadge.textContent = visibleActivities.length;
        }
    }

    // Fonction pour réinitialiser les filtres d'activités
    function resetActivityFilters() {
        if (activityTypeFilter) activityTypeFilter.value = '';
        if (activityCommercialFilter) activityCommercialFilter.value = '';

        // Afficher toutes les activités
        timelineItems.forEach(item => {
            item.style.display = 'flex';
            item.style.animation = 'fadeIn 0.3s ease forwards';
        });

        updateActivityCount();
    }

    // Ajouter les event listeners pour les filtres d'activités
    if (activityTypeFilter) {
        activityTypeFilter.addEventListener('change', filterActivities);
    }

    if (activityCommercialFilter) {
        activityCommercialFilter.addEventListener('change', filterActivities);
    }

    // Fonction pour voir les détails d'une activité
    window.viewActivityDetails = function (type, etablissement) {
        // Ici vous pouvez implémenter la logique pour afficher les détails
        // Par exemple, ouvrir une modal ou rediriger vers une page de détails
        console.log('Voir détails:', type, etablissement);

        // Exemple d'alerte (à remplacer par votre logique)
        alert(`Détails de l'activité ${type} pour ${etablissement}`);
    };

    // Exposer les fonctions pour une utilisation externe
    window.activityFilterFunctions = {
        filter: filterActivities,
        reset: resetActivityFilters,
        updateCount: updateActivityCount
    };
});

/**
 * Module de gestion des onglets d'activités
 * 
 * Ce module gère les onglets principaux (Commerciaux/Comptables) et les sous-onglets
 */
document.addEventListener('DOMContentLoaded', function () {
    // Gestion des onglets principaux
    const mainTabs = document.querySelectorAll('.main-tab');
    const mainTabContents = document.querySelectorAll('.main-tab-content');

    mainTabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const targetTab = this.getAttribute('data-main-tab');

            // Désactiver tous les onglets principaux
            mainTabs.forEach(t => t.classList.remove('active'));
            mainTabContents.forEach(c => c.classList.remove('active'));

            // Activer l'onglet cliqué
            this.classList.add('active');
            document.getElementById(targetTab + '-tab').classList.add('active');

            // Réinitialiser les sous-onglets
            resetSubTabs();
        });
    });

    // Gestion des sous-onglets commerciaux
    const commercialSubTabs = document.querySelectorAll('[data-sub-tab]');
    const commercialActivities = document.getElementById('commercial-activities');

    commercialSubTabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const targetSubTab = this.getAttribute('data-sub-tab');

            // Désactiver tous les sous-onglets
            commercialSubTabs.forEach(t => t.classList.remove('active'));

            // Activer le sous-onglet cliqué
            this.classList.add('active');

            // Filtrer les activités selon le sous-onglet
            filterCommercialActivities(targetSubTab);
        });
    });

    // Fonction pour filtrer les activités commerciales
    function filterCommercialActivities(subTab) {
        const activities = document.querySelectorAll('#commercial-activities .timeline-item');

        activities.forEach(activity => {
            const activityType = activity.getAttribute('data-type');
            let shouldShow = false;

            switch (subTab) {
                case 'all-commercial':
                    shouldShow = true;
                    break;
                case 'prospects':
                    shouldShow = activityType === 'prospect';
                    break;
                case 'rendez-vous':
                    shouldShow = activityType === 'rendez_vous';
                    break;
                case 'comptes-rendus':
                    shouldShow = activityType === 'compte_rendu';
                    break;
                case 'notes':
                    shouldShow = activityType === 'note';
                    break;
            }

            if (shouldShow) {
                activity.style.display = 'flex';
                activity.style.animation = 'fadeIn 0.3s ease forwards';
            } else {
                activity.style.display = 'none';
            }
        });

        updateCommercialCount();
    }

    // Fonction pour réinitialiser les sous-onglets
    function resetSubTabs() {
        const activeSubTabs = document.querySelectorAll('.sub-tab.active');
        activeSubTabs.forEach(tab => {
            tab.classList.remove('active');
        });

        // Activer le premier sous-onglet
        const firstSubTab = document.querySelector('.sub-tab');
        if (firstSubTab) {
            firstSubTab.classList.add('active');
        }
    }

    // Fonction pour mettre à jour le compteur commercial
    function updateCommercialCount() {
        const visibleActivities = document.querySelectorAll('#commercial-activities .timeline-item[style*="flex"], #commercial-activities .timeline-item:not([style*="none"])');
        const countBadge = document.querySelector('#totalActivitiesCount');

        if (countBadge) {
            // Compter aussi les activités comptables
            const accountingActivities = document.querySelectorAll('#accounting-activities .timeline-item');
            const totalCount = visibleActivities.length + accountingActivities.length;
            countBadge.textContent = totalCount;
        }
    }

    // Fonction pour voir les détails comptables
    window.viewAccountingDetails = function (type, id) {
        console.log('Voir détails comptable:', type, id);
        alert(`Détails de l'activité comptable ${type} (ID: ${id})`);
    };

    // Exposer les fonctions pour une utilisation externe
    window.tabFunctions = {
        filterCommercial: filterCommercialActivities,
        resetSubTabs: resetSubTabs,
        updateCommercialCount: updateCommercialCount
    };
});