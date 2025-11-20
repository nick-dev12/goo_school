

document.addEventListener('DOMContentLoaded', function () {
    // Éléments du DOM
    const openNavBtn = document.getElementById('openNavMenu');
    const closeNavBtn = document.getElementById('closeNavMenu');
    const navOverlay = document.getElementById('navOverlay');
    const navigationSection = document.getElementById('navigationSection');

    // Ouvrir le menu de navigation (seulement si le bouton existe - pour compatibilité avec les anciens templates)
    if (openNavBtn) {
        openNavBtn.addEventListener('click', function () {
            navOverlay.classList.add('active');
            navigationSection.classList.add('active');
            document.body.style.overflow = 'hidden'; // Empêcher le défilement
        });
    }

    // Fermer le menu de navigation
    function closeNavigation() {
        if (navOverlay) navOverlay.classList.remove('active');
        if (navigationSection) navigationSection.classList.remove('active');
        document.body.style.overflow = ''; // Réactiver le défilement
    }

    // Ne gérer le menu que si aucun script spécifique ne le gère déjà
    if (!window.administrateurNavMenu && !window.directeurNavMenu && !window.commercialNavMenu && !window.comptableNavMenu) {
        if (closeNavBtn) {
            closeNavBtn.addEventListener('click', closeNavigation);
        }
        if (navOverlay) {
            navOverlay.addEventListener('click', closeNavigation);
        }
    }

    // Fermer le menu lors d'un clic sur un lien de navigation
    // Seulement si le menu n'est pas géré par un autre script (comme bottom_nav)
    const navLinks = document.querySelectorAll('.nav-link-card');
    navLinks.forEach(link => {
        link.addEventListener('click', function () {
            // Vérifier si le menu est géré par un script spécifique (bottom_nav)
            // Si c'est le cas, utiliser le contrôleur spécifique pour fermer
            if (window.administrateurNavMenu) {
                setTimeout(() => window.administrateurNavMenu.close(), 100);
            } else if (window.directeurNavMenu) {
                setTimeout(() => window.directeurNavMenu.close(), 100);
            } else if (window.commercialNavMenu) {
                setTimeout(() => window.commercialNavMenu.close(), 100);
            } else if (window.comptableNavMenu) {
                setTimeout(() => window.comptableNavMenu.close(), 100);
            } else {
                // Petite temporisation pour permettre l'effet visuel avant la redirection
                setTimeout(closeNavigation, 100);
            }
        });
    });

    // Mettre en évidence le lien actif
    const currentPage = window.location.pathname.split('/').pop();
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPage) {
            link.classList.add('active');
        }
    });
});



// Toggle sidebar visibility on mobile
const menuToggle = document.getElementById('menu-toggle');
if (menuToggle) {
    menuToggle.addEventListener('click', function () {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.toggle('active');
        }
    });
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function (event) {
    if (window.innerWidth <= 992) {
        const sidebar = document.querySelector('.sidebar');
        const menuToggle = document.getElementById('menu-toggle');

        if (sidebar && menuToggle && !sidebar.contains(event.target) && event.target !== menuToggle) {
            sidebar.classList.remove('active');
        }
    }
});

// Highlight current menu item
document.addEventListener('DOMContentLoaded', function () {
    const currentPage = window.location.pathname.split('/').pop();
    const menuItems = document.querySelectorAll('.sidebar .menu-item');

    menuItems.forEach(function (item) {
        const href = item.getAttribute('href');
        if (href === currentPage) {
            item.classList.add('active');
        } else if (currentPage === '' && href === 'dashboard.php') {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
});
