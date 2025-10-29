// header.js - Gestion du menu de navigation pour l'espace élève

document.addEventListener('DOMContentLoaded', function() {
    // Éléments du DOM
    const openNavButton = document.getElementById('openNavMenu');
    const closeNavButton = document.getElementById('closeNavMenu');
    const navigationSection = document.getElementById('navigationSection');
    const navOverlay = document.getElementById('navOverlay');

    // Fonction pour ouvrir le menu
    function openNav() {
        navigationSection.classList.add('active');
        navOverlay.classList.add('active');
        document.body.style.overflow = 'hidden'; // Empêcher le scroll
    }

    // Fonction pour fermer le menu
    function closeNav() {
        navigationSection.classList.remove('active');
        navOverlay.classList.remove('active');
        document.body.style.overflow = ''; // Réactiver le scroll
    }

    // Event listeners
    if (openNavButton) {
        openNavButton.addEventListener('click', openNav);
    }

    if (closeNavButton) {
        closeNavButton.addEventListener('click', closeNav);
    }

    if (navOverlay) {
        navOverlay.addEventListener('click', closeNav);
    }

    // Fermer avec la touche ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && navigationSection.classList.contains('active')) {
            closeNav();
        }
    });
});

