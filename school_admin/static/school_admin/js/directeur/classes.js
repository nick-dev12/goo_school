// school_admin/static/school_admin/js/directeur/classes.js

document.addEventListener('DOMContentLoaded', function() {
    // Éléments du DOM
    const addClasseBtn = document.getElementById('addClasseBtn');
    const addClasseBtnEmpty = document.getElementById('addClasseBtnEmpty');
    const addClasseModal = document.getElementById('addClasseModal');
    const closeModal = document.getElementById('closeModal');
    const cancelAdd = document.getElementById('cancelAdd');
    const addClasseForm = document.getElementById('addClasseForm');

    // Fonction pour ouvrir le modal
    function openModal() {
        addClasseModal.classList.add('active');
        document.body.style.overflow = 'hidden';
        
        // Focus sur le premier champ
        const firstInput = addClasseForm.querySelector('input, select, textarea');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }
    }

    // Fonction pour fermer le modal
    function closeModalFunc() {
        addClasseModal.classList.remove('active');
        document.body.style.overflow = '';
        
        // Réinitialiser le formulaire
        addClasseForm.reset();
    }

    // Événements pour ouvrir le modal
    if (addClasseBtn) {
        addClasseBtn.addEventListener('click', openModal);
    }
    
    if (addClasseBtnEmpty) {
        addClasseBtnEmpty.addEventListener('click', openModal);
    }

    // Événements pour fermer le modal
    if (closeModal) {
        closeModal.addEventListener('click', closeModalFunc);
    }
    
    if (cancelAdd) {
        cancelAdd.addEventListener('click', closeModalFunc);
    }

    // Fermer le modal en cliquant sur l'overlay
    if (addClasseModal) {
        addClasseModal.addEventListener('click', function(e) {
            if (e.target === addClasseModal) {
                closeModalFunc();
            }
        });
    }

    // Fermer le modal avec la touche Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && addClasseModal.classList.contains('active')) {
            closeModalFunc();
        }
    });

    // Gestion du formulaire
    if (addClasseForm) {
        addClasseForm.addEventListener('submit', function(e) {
            // Afficher un indicateur de chargement
            const submitBtn = addClasseForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Ajout en cours...</span>';
                submitBtn.disabled = true;
            }
        });
    }


    // Animation des cartes au chargement
    const classeCards = document.querySelectorAll('.classe-card');
    classeCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Animation des statistiques
    const statNumbers = document.querySelectorAll('.stat-number');
    statNumbers.forEach(stat => {
        const finalValue = parseInt(stat.textContent);
        let currentValue = 0;
        const increment = Math.ceil(finalValue / 20);
        
        const timer = setInterval(() => {
            currentValue += increment;
            if (currentValue >= finalValue) {
                currentValue = finalValue;
                clearInterval(timer);
            }
            stat.textContent = currentValue;
        }, 50);
    });

    // Gestion des actions des cartes
    const actionButtons = document.querySelectorAll('.btn-action');
    actionButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            // Ajouter un effet de clic
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = '';
            }, 150);
        });
    });

    // Confirmation pour les actions de désactivation
    const toggleButtons = document.querySelectorAll('.btn-toggle');
    toggleButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const isActive = this.classList.contains('active');
            const action = isActive ? 'désactiver' : 'activer';
            const classeNom = this.closest('.classe-card').querySelector('.classe-nom').textContent;
            
            if (!confirm(`Êtes-vous sûr de vouloir ${action} la classe "${classeNom}" ?`)) {
                e.preventDefault();
            }
        });
    });
});
