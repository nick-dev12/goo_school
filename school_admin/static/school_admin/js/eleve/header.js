// header.js - Gestion du menu de navigation pour l'espace élève

document.addEventListener('DOMContentLoaded', function () {
    const openNavButton = document.getElementById('openNavMenu');
    const closeNavButton = document.getElementById('closeNavMenu');
    const navigationSection = document.getElementById('navigationSection');
    const navOverlay = document.getElementById('navOverlay');

    if (navigationSection && navOverlay && closeNavButton) {
        function openNav() {
            navOverlay.classList.add('active');
            navigationSection.classList.add('active');
            document.body.style.overflow = 'hidden';
            document.dispatchEvent(new CustomEvent('eleveNavOpen'));
        }

        function closeNav() {
            navigationSection.classList.remove('active');
            navOverlay.classList.remove('active');
            document.body.style.overflow = '';
            document.dispatchEvent(new CustomEvent('eleveNavClose'));
        }

        if (openNavButton) {
            openNavButton.addEventListener('click', openNav);
        }

        closeNavButton.addEventListener('click', closeNav);

        navOverlay.addEventListener('click', function (event) {
            if (event.target === navOverlay) {
                closeNav();
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && navigationSection.classList.contains('active')) {
                closeNav();
            }
        });

        window.eleveNavMenu = {
            open: openNav,
            close: closeNav,
        };
    }
});

