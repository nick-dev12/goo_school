/**
 * Module de gestion des onglets
 * 
 * Ce module gère la navigation par onglets dans l'interface de gestion des équipes.
 * Il permet de basculer entre les différentes sections (équipe, rôles, activités, système).
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    // Configurer les écouteurs d'événements pour les onglets
    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            // Retirer la classe active de tous les onglets
            tabs.forEach(t => t.classList.remove('active'));

            // Ajouter la classe active à l'onglet cliqué
            this.classList.add('active');

            // Masquer tous les contenus d'onglet
            tabContents.forEach(content => content.classList.remove('active'));

            // Afficher le contenu de l'onglet sélectionné
            const tabId = this.getAttribute('data-tab') + '-tab';
            const targetContent = document.getElementById(tabId);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });

    // Fonction pour activer un onglet spécifique par son ID
    window.activateTab = function (tabId) {
        const tab = document.querySelector(`.tab[data-tab="${tabId}"]`);
        if (tab) {
            tab.click();
        }
    };
});