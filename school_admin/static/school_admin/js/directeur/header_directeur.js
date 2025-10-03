/**
 * Script pour la gestion du header et du menu de navigation - Espace Directeur
 * Version optimisée pour le design compact
 */

document.addEventListener('DOMContentLoaded', function () {
    // Éléments du DOM
    const openNavBtn = document.getElementById('openNavMenu');
    const closeNavBtn = document.getElementById('closeNavMenu');
    const navOverlay = document.getElementById('navOverlay');
    const navigationSection = document.getElementById('navigationSection');
    const mainContent = document.getElementById('mainContent');

    // Fonction pour ouvrir le menu de navigation
    function openNavigation() {
        // Afficher d'abord l'overlay pour l'animation fluide
        navOverlay.classList.add('active');
        // Puis activer le menu avec un léger délai pour une animation plus fluide
        setTimeout(() => {
            navigationSection.classList.add('active');
            document.body.style.overflow = 'hidden'; // Empêche le défilement du body
        }, 50);
    }

    // Fonction pour fermer le menu de navigation
    function closeNavigation() {
        navigationSection.classList.remove('active');
        // Attendre la fin de l'animation avant de cacher l'overlay
        setTimeout(() => {
            navOverlay.classList.remove('active');
            document.body.style.overflow = ''; // Rétablit le défilement du body
        }, 300);
    }

    // Gestionnaires d'événements
    if (openNavBtn) {
        openNavBtn.addEventListener('click', openNavigation);
    }

    if (closeNavBtn) {
        closeNavBtn.addEventListener('click', closeNavigation);
    }

    if (navOverlay) {
        navOverlay.addEventListener('click', closeNavigation);
    }

    // Fermeture du menu avec la touche Escape
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && navigationSection.classList.contains('active')) {
            closeNavigation();
        }
    });

    // Gestion du menu actif
    const currentPage = window.location.pathname.split('/').pop();
    const navLinks = document.querySelectorAll('.nav-link-card');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPage || (currentPage === '' && href === 'dashboard.php')) {
            link.classList.add('active');
        }
    });

    // Gestion responsive du header
    function handleResponsiveHeader() {
        const windowWidth = window.innerWidth;
        const headerUserInfo = document.querySelector('.header-user-info');

        if (windowWidth < 768 && headerUserInfo) {
            headerUserInfo.style.display = 'none';
        } else if (headerUserInfo) {
            headerUserInfo.style.display = 'block';
        }

        // Ajuster la hauteur du menu pour les appareils mobiles
        if (windowWidth < 576) {
            navigationSection.style.height = '100vh';
        } else {
            navigationSection.style.height = '90vh';
        }
    }

    // Appliquer au chargement et au redimensionnement
    handleResponsiveHeader();
    window.addEventListener('resize', handleResponsiveHeader);

    // Gérer les notifications
    const notificationBtns = document.querySelectorAll('.header-button');
    notificationBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            // Ici, on pourrait ajouter du code pour afficher un menu déroulant de notifications
            console.log('Notification button clicked');
        });
    });

    // Gérer le profil utilisateur
    const profileBtn = document.querySelector('.header-profile');
    if (profileBtn) {
        profileBtn.addEventListener('click', function () {
            // Ici, on pourrait ajouter du code pour afficher un menu déroulant du profil
            console.log('Profile button clicked');
        });
    }

    // Gestion de la recherche
    const searchInput = document.querySelector('.header-search input');
    if (searchInput) {
        searchInput.addEventListener('keypress', function (event) {
            if (event.key === 'Enter') {
                // Ici, on pourrait ajouter du code pour gérer la recherche
                console.log('Search query:', searchInput.value);
                event.preventDefault();
            }
        });
    }
});