

document.addEventListener('DOMContentLoaded', function () {
    // Éléments du DOM
    const openNavBtn = document.getElementById('openNavMenu');
    const closeNavBtn = document.getElementById('closeNavMenu');
    const navOverlay = document.getElementById('navOverlay');
    const navigationSection = document.getElementById('navigationSection');

    // Ouvrir le menu de navigation
    openNavBtn.addEventListener('click', function () {
        navOverlay.classList.add('active');
        navigationSection.classList.add('active');
        document.body.style.overflow = 'hidden'; // Empêcher le défilement
    });

    // Fermer le menu de navigation
    function closeNavigation() {
        navOverlay.classList.remove('active');
        navigationSection.classList.remove('active');
        document.body.style.overflow = ''; // Réactiver le défilement
    }

    closeNavBtn.addEventListener('click', closeNavigation);
    navOverlay.addEventListener('click', closeNavigation);

    // Fermer le menu lors d'un clic sur un lien de navigation
    const navLinks = document.querySelectorAll('.nav-link-card');
    navLinks.forEach(link => {
        link.addEventListener('click', function () {
            // Petite temporisation pour permettre l'effet visuel avant la redirection
            setTimeout(closeNavigation, 100);
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
document.getElementById('menu-toggle').addEventListener('click', function () {
    document.querySelector('.sidebar').classList.toggle('active');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function (event) {
    if (window.innerWidth <= 992) {
        const sidebar = document.querySelector('.sidebar');
        const menuToggle = document.getElementById('menu-toggle');

        if (!sidebar.contains(event.target) && event.target !== menuToggle) {
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
