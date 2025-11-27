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

    // Gestion du bouton d'installation PWA
    const pwaInstallBtn = document.getElementById('pwa-install-btn');
    let deferredPrompt = null;

    // Écouter l'événement beforeinstallprompt
    window.addEventListener('beforeinstallprompt', (e) => {
        // Empêcher l'affichage automatique du prompt
        e.preventDefault();
        // Stocker l'événement pour l'utiliser plus tard
        deferredPrompt = e;
        // Afficher le bouton d'installation
        if (pwaInstallBtn) {
            pwaInstallBtn.style.display = 'inline-flex';
        }
    });

    // Gérer le clic sur le bouton d'installation
    if (pwaInstallBtn) {
        pwaInstallBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (deferredPrompt) {
                // Afficher le prompt d'installation (doit être appelé directement depuis le gestionnaire de clic)
                deferredPrompt.prompt();
                
                // Attendre la réponse de l'utilisateur
                deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        console.log('[PWA] L\'utilisateur a accepté l\'installation');
                    } else {
                        console.log('[PWA] L\'utilisateur a refusé l\'installation');
                    }
                    
                    // Masquer le bouton après la réponse
                    if (pwaInstallBtn) {
                        pwaInstallBtn.style.display = 'none';
                    }
                    
                    // Réinitialiser
                    deferredPrompt = null;
                });
            }
        });
    }

    // Masquer le bouton si l'application est déjà installée
    if (window.matchMedia('(display-mode: standalone)').matches) {
        if (pwaInstallBtn) {
            pwaInstallBtn.style.display = 'none';
        }
    }

    // Écouter l'événement appinstalled
    window.addEventListener('appinstalled', () => {
        console.log('[PWA] Application installée avec succès');
        if (pwaInstallBtn) {
            pwaInstallBtn.style.display = 'none';
        }
        deferredPrompt = null;
    });

    // Gestion du bouton retour
    const backButton = document.getElementById('backButton');
    
    if (backButton) {
        // Gérer le clic sur le bouton retour
        backButton.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Utiliser history.back() pour revenir à la page précédente
            // Le navigateur gère automatiquement si aucune page précédente n'existe
            if (window.history.length > 1) {
                window.history.back();
            } else {
                // Fallback: si pas d'historique, rediriger vers le dashboard
                // On utilise une URL relative pour éviter les problèmes de configuration
                try {
                    window.location.href = document.referrer || '/directeur/dashboard/';
                } catch (error) {
                    // Si document.referrer n'est pas disponible, utiliser history.back() quand même
                    window.history.back();
                }
            }
        });

        // Ajouter un effet visuel au survol (géré par CSS, mais on peut ajouter des animations JS si nécessaire)
        backButton.addEventListener('mouseenter', function() {
            if (!backButton.disabled) {
                const icon = backButton.querySelector('i');
                if (icon) {
                    icon.style.transform = 'translateX(-3px)';
                }
            }
        });

        backButton.addEventListener('mouseleave', function() {
            const icon = backButton.querySelector('i');
            if (icon) {
                icon.style.transform = 'translateX(0)';
            }
        });
    }
});