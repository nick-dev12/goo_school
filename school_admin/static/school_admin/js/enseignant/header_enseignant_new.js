// Header Enseignant - Navigation

document.addEventListener('DOMContentLoaded', function() {
    const openNavBtn = document.getElementById('openNavMenu');
    const closeNavBtn = document.getElementById('closeNavMenu');
    const navSection = document.getElementById('navigationSection');
    const navOverlay = document.getElementById('navOverlay');

    if (closeNavBtn && navSection && navOverlay) {
        function openNav() {
            navSection.classList.add('active');
            navOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';
            document.dispatchEvent(new CustomEvent('enseignantNavOpen'));
        }

        function closeNav() {
            navSection.classList.remove('active');
            navOverlay.classList.remove('active');
            document.body.style.overflow = '';
            document.dispatchEvent(new CustomEvent('enseignantNavClose'));
        }

        if (openNavBtn) {
            openNavBtn.addEventListener('click', openNav);
        }

        closeNavBtn.addEventListener('click', closeNav);
        navOverlay.addEventListener('click', closeNav);

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && navSection.classList.contains('active')) {
                closeNav();
            }
        });

        window.enseignantNavMenu = {
            open: openNav,
            close: closeNav,
        };
    }

    // Animation des cartes au scroll
    const cards = document.querySelectorAll('.classe-card, .eleve-card, .quick-action-card');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, {
        threshold: 0.1
    });
    
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = `all 0.5s ease ${index * 0.05}s`;
        observer.observe(card);
    });

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
                    window.location.href = document.referrer || '/dashboard/enseignant/';
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

