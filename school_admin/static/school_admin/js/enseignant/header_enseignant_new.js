// Header Enseignant - Navigation

document.addEventListener('DOMContentLoaded', function() {
    if (window.__enseignantHeaderEnhancementsReady) return;
    window.__enseignantHeaderEnhancementsReady = true;
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

