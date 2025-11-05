/**
 * Script pour la page Sanctions disciplinaires
 * Gère uniquement les interactions (onglets de périodes)
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
            const periodeId = this.getAttribute('data-periode');

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
                const activeSection = document.querySelector(`.periode-section[data-periode="${periodeId}"]`);
                if (activeSection) {
                    activeSection.classList.add('active');
                    activeSection.style.animation = 'fadeIn 0.5s ease forwards';
                }
            }, 50);
        });
    });
}

