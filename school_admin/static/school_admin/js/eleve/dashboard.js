// dashboard.js - Gestion des interactions du dashboard élève

document.addEventListener('DOMContentLoaded', function() {
    // Gérer le checkbox des devoirs
    const homeworkCheckboxes = document.querySelectorAll('.homework-checkbox');
    
    homeworkCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const homeworkItem = this.closest('.homework-item');
            
            if (this.checked) {
                homeworkItem.classList.add('completed');
                // Ici vous pouvez ajouter une requête AJAX pour enregistrer l'état
                console.log('Devoir marqué comme terminé');
            } else {
                homeworkItem.classList.remove('completed');
                console.log('Devoir marqué comme non terminé');
            }
        });
    });

    // Animation des cartes au survol
    const infoCards = document.querySelectorAll('.info-card, .schedule-card, .homework-card, .grades-card, .attendance-card');
    
    infoCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
});

