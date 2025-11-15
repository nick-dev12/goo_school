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

    if (navigationSection && navOverlay && closeNavBtn) {
        function openNavigation() {
            navOverlay.classList.add('active');
            navigationSection.classList.add('active');
            document.body.style.overflow = 'hidden';
            document.dispatchEvent(new CustomEvent('directeurNavOpen'));
        }

        function closeNavigation() {
            navigationSection.classList.remove('active');
            navOverlay.classList.remove('active');
            document.body.style.overflow = '';
            document.dispatchEvent(new CustomEvent('directeurNavClose'));
        }

        if (openNavBtn) {
            openNavBtn.addEventListener('click', openNavigation);
        }

        closeNavBtn.addEventListener('click', closeNavigation);

        navOverlay.addEventListener('click', function (event) {
            if (event.target === navOverlay) {
                closeNavigation();
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && navigationSection.classList.contains('active')) {
                closeNavigation();
            }
        });

        window.directeurNavMenu = {
            open: openNavigation,
            close: closeNavigation,
        };
    }

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
        if (navigationSection) {
            if (windowWidth < 576) {
                navigationSection.style.height = '100vh';
            } else {
                navigationSection.style.height = '90vh';
            }
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