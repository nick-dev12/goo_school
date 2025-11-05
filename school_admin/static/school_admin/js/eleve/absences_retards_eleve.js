/**
 * Script pour la page Absences & Retards
 * Gère uniquement les interactions (onglets de périodes et de mois)
 */

document.addEventListener('DOMContentLoaded', function () {
    initPeriodeTabs();
});

/**
 * Initialisation des onglets de périodes
 */
function initPeriodeTabs() {
    const periodeTabs = document.querySelectorAll('.periode-tab');
    const periodeSections = document.querySelectorAll('.periode-section');

    // Gérer le clic sur les onglets de périodes
    periodeTabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const periodeName = this.getAttribute('data-periode');

            // Désactiver tous les onglets et sections
            periodeTabs.forEach(t => t.classList.remove('active'));
            periodeSections.forEach(s => {
                s.classList.remove('active');
                s.style.animation = 'none';
            });

            // Activer l'onglet cliqué
            this.classList.add('active');

            // Activer la section correspondante avec animation
            setTimeout(() => {
                const activeSection = document.querySelector(`.periode-section[data-periode="${periodeName}"]`);
                if (activeSection) {
                    activeSection.classList.add('active');
                    activeSection.style.animation = 'fadeIn 0.5s ease forwards';
                }
            }, 50);
        });
    });
}

/**
 * Changer de mois dans une période
 */
function switchMois(periodeName, moisKey) {
    // Désactiver tous les onglets de mois pour cette période
    const moisTabs = document.querySelectorAll(`.mois-tab[data-periode="${periodeName}"]`);
    moisTabs.forEach(tab => tab.classList.remove('active'));
    
    // Activer l'onglet cliqué
    const clickedTab = document.querySelector(`.mois-tab[data-periode="${periodeName}"][data-mois="${moisKey}"]`);
    if (clickedTab) {
        clickedTab.classList.add('active');
    }
    
    // Masquer tous les contenus de mois pour cette période
    const moisContents = document.querySelectorAll(`.mois-content[data-periode="${periodeName}"]`);
    moisContents.forEach(content => {
        content.classList.remove('active');
        content.style.animation = 'none';
    });
    
    // Afficher le contenu du mois sélectionné avec animation
    setTimeout(() => {
        const activeContent = document.querySelector(`.mois-content[data-periode="${periodeName}"][data-mois="${moisKey}"]`);
        if (activeContent) {
            activeContent.classList.add('active');
            activeContent.style.animation = 'fadeIn 0.4s ease forwards';
        }
    }, 50);
}

