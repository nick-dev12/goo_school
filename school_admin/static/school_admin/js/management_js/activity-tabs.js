/**
 * Module de gestion des onglets d'activités
 * 
 * Ce module gère les onglets principaux (Commerciaux/Comptables) et les sous-onglets
 */
document.addEventListener('DOMContentLoaded', function () {
    console.log('Module onglets d\'activités chargé');

    // Attendre un peu pour s'assurer que tous les éléments sont chargés
    setTimeout(function () {
        initializeActivityTabs();
    }, 500);
});

function initializeActivityTabs() {
    console.log('Initialisation des onglets d\'activités');

    // Vérifier si l'onglet activités existe
    const activitiesTab = document.getElementById('activities-tab');
    if (!activitiesTab) {
        console.warn('Onglet activités non trouvé');
        return;
    }

    // Initialiser les onglets d'activités
    setupActivityTabs();

    // Observer les changements d'onglet principal pour réinitialiser si nécessaire
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                if (activitiesTab.classList.contains('active')) {
                    console.log('Onglet activités activé, réinitialisation des sous-onglets');
                    // Réinitialiser les sous-onglets quand l'onglet activités devient actif
                    resetSubTabs();
                }
            }
        });
    });

    observer.observe(activitiesTab, { attributes: true });
}

function setupActivityTabs() {
    // Gestion des onglets principaux
    const mainTabs = document.querySelectorAll('.main-tab');
    const mainTabContents = document.querySelectorAll('.main-tab-content');

    console.log('Onglets principaux trouvés:', mainTabs.length);
    console.log('Contenus d\'onglets trouvés:', mainTabContents.length);

    if (mainTabs.length === 0) {
        console.warn('Aucun onglet principal trouvé');
        return;
    }

    // Ajouter les event listeners seulement si les éléments existent
    if (mainTabs.length > 0) {
        mainTabs.forEach(tab => {
            // Vérifier si l'event listener n'est pas déjà ajouté
            if (!tab.hasAttribute('data-listener-added')) {
                tab.addEventListener('click', function (e) {
                    e.preventDefault();
                    console.log('Clic sur onglet principal:', this.getAttribute('data-main-tab'));
                    const targetTab = this.getAttribute('data-main-tab');

                    // Désactiver tous les onglets principaux
                    mainTabs.forEach(t => t.classList.remove('active'));
                    mainTabContents.forEach(c => c.classList.remove('active'));

                    // Activer l'onglet cliqué
                    this.classList.add('active');
                    const targetElement = document.getElementById(targetTab + '-tab');
                    if (targetElement) {
                        targetElement.classList.add('active');
                        console.log('Onglet activé:', targetTab + '-tab');
                    } else {
                        console.error('Élément non trouvé:', targetTab + '-tab');
                    }

                    // Réinitialiser les sous-onglets
                    resetSubTabs();
                });
                tab.setAttribute('data-listener-added', 'true');
            }
        });
    }

    // Gestion des sous-onglets commerciaux
    const commercialSubTabs = document.querySelectorAll('[data-sub-tab]');

    console.log('Sous-onglets commerciaux trouvés:', commercialSubTabs.length);

    if (commercialSubTabs.length > 0) {
        commercialSubTabs.forEach(tab => {
            // Vérifier si l'event listener n'est pas déjà ajouté
            if (!tab.hasAttribute('data-listener-added')) {
                tab.addEventListener('click', function (e) {
                    e.preventDefault();
                    console.log('Clic sur sous-onglet:', this.getAttribute('data-sub-tab'));
                    const targetSubTab = this.getAttribute('data-sub-tab');

                    // Désactiver tous les sous-onglets du même niveau
                    const parentContainer = this.closest('.sub-tabs');
                    if (parentContainer) {
                        const siblingTabs = parentContainer.querySelectorAll('.sub-tab');
                        siblingTabs.forEach(t => t.classList.remove('active'));
                    }

                    // Activer le sous-onglet cliqué
                    this.classList.add('active');

                    // Filtrer les activités selon le sous-onglet
                    filterCommercialActivities(targetSubTab);
                });
                tab.setAttribute('data-listener-added', 'true');
            }
        });
    }
}

// Fonction pour filtrer les activités commerciales
function filterCommercialActivities(subTab) {
    console.log('Filtrage des activités commerciales:', subTab);
    const activities = document.querySelectorAll('#commercial-activities .timeline-item');

    console.log('Activités commerciales trouvées:', activities.length);

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
    console.log('Réinitialisation des sous-onglets');
    const activeSubTabs = document.querySelectorAll('.sub-tab.active');
    activeSubTabs.forEach(tab => {
        tab.classList.remove('active');
    });

    // Activer le premier sous-onglet de chaque conteneur
    const subTabContainers = document.querySelectorAll('.sub-tabs');
    subTabContainers.forEach(container => {
        const firstSubTab = container.querySelector('.sub-tab');
        if (firstSubTab) {
            firstSubTab.classList.add('active');
        }
    });
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
        console.log('Compteur mis à jour:', totalCount);
    }
}

// Fonction pour voir les détails comptables
window.viewAccountingDetails = function (type, id) {
    console.log('Voir détails comptable:', type, id);
    alert(`Détails de l'activité comptable ${type} (ID: ${id})`);
};

// Exposer les fonctions pour une utilisation externe
window.activityTabFunctions = {
    filterCommercial: filterCommercialActivities,
    resetSubTabs: resetSubTabs,
    updateCommercialCount: updateCommercialCount
};
