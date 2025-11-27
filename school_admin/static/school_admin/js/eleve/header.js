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
        backButton.addEventListener('click', function (e) {
            e.preventDefault();

            // Utiliser history.back() pour revenir à la page précédente
            // Le navigateur gère automatiquement si aucune page précédente n'existe
            if (window.history.length > 1) {
                window.history.back();
            } else {
                // Fallback: si pas d'historique, rediriger vers le dashboard
                // On utilise une URL relative pour éviter les problèmes de configuration
                try {
                    window.location.href = document.referrer || '/eleve/dashboard/';
                } catch (error) {
                    // Si document.referrer n'est pas disponible, utiliser history.back() quand même
                    window.history.back();
                }
            }
        });

        // Ajouter un effet visuel au survol (géré par CSS, mais on peut ajouter des animations JS si nécessaire)
        backButton.addEventListener('mouseenter', function () {
            if (!backButton.disabled) {
                const icon = backButton.querySelector('i');
                if (icon) {
                    icon.style.transform = 'translateX(-3px)';
                }
            }
        });

        backButton.addEventListener('mouseleave', function () {
            const icon = backButton.querySelector('i');
            if (icon) {
                icon.style.transform = 'translateX(0)';
            }
        });
    }
});

