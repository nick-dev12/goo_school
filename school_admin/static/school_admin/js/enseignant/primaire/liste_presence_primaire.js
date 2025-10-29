// Liste de présence - JavaScript

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page liste de présence chargée');
    
    // Gestion des boutons de statut
    const statutOptions = document.querySelectorAll('.statut-option');
    
    statutOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Si désactivé, ne rien faire
            if (this.hasAttribute('disabled')) {
                return;
            }
            
            // Obtenir le nom du groupe radio
            const radio = this.querySelector('input[type="radio"]');
            if (!radio) return;
            
            const radioName = radio.name;
            
            // Retirer la classe active de tous les boutons du même groupe
            const sameGroupOptions = document.querySelectorAll(`input[name="${radioName}"]`);
            sameGroupOptions.forEach(input => {
                input.closest('.statut-option').classList.remove('active');
            });
            
            // Ajouter la classe active au bouton cliqué
            this.classList.add('active');
            
            // Cocher le radio button
            radio.checked = true;
        });
    });
    
    // Animation au survol
    const tableRows = document.querySelectorAll('.presence-table tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.01)';
        });
        
        row.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
    
    // Compter les présents/absents en temps réel
    function updateStats() {
        const allRadios = document.querySelectorAll('input[type="radio"]:checked');
        let presents = 0;
        let absents = 0;
        let retards = 0;
        let absentsJustifies = 0;
        
        allRadios.forEach(radio => {
            switch(radio.value) {
                case 'present':
                    presents++;
                    break;
                case 'absent':
                    absents++;
                    break;
                case 'retard':
                    retards++;
                    break;
                case 'absent_justifie':
                    absentsJustifies++;
                    break;
            }
        });
        
        console.log(`Présents: ${presents}, Absents: ${absents}, Retards: ${retards}, Absents justifiés: ${absentsJustifies}`);
    }
    
    // Écouter les changements de statut
    const allRadios = document.querySelectorAll('input[type="radio"]');
    allRadios.forEach(radio => {
        radio.addEventListener('change', updateStats);
    });
    
    // Initial stats
    updateStats();
});

