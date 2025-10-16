// Détail Élève - JavaScript

let presenceIdEnCours = null;

// Ouvrir le modal de modification de présence
function ouvrirModalModification(presenceId, statutActuel, date) {
    console.log(`Ouverture modal - Présence ID: ${presenceId}, Statut: ${statutActuel}`);
    
    presenceIdEnCours = presenceId;
    
    // Mettre à jour la date dans le modal
    document.getElementById('modal-date').textContent = date;
    
    // Cocher le radio button correspondant au statut actuel
    const radioButtons = document.querySelectorAll('input[name="statut"]');
    radioButtons.forEach(radio => {
        if (radio.value === statutActuel) {
            radio.checked = true;
            radio.closest('.statut-radio').querySelector('.radio-content').style.borderWidth = '3px';
        }
    });
    
    // Mettre à jour l'action du formulaire
    const form = document.getElementById('form-modifier-presence');
    form.action = `/enseignant/modifier-presence/${presenceId}/`;
    
    // Afficher le modal
    const modal = document.getElementById('modal-modifier-presence');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

// Fermer le modal
function fermerModal() {
    const modal = document.getElementById('modal-modifier-presence');
    modal.classList.remove('active');
    document.body.style.overflow = 'auto';
    presenceIdEnCours = null;
}

// Fermer le modal si clic en dehors
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('modal-modifier-presence');
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            fermerModal();
        }
    });
    
    // Gérer le changement de radio
    const radioLabels = document.querySelectorAll('.statut-radio');
    radioLabels.forEach(label => {
        label.addEventListener('click', function() {
            // Réinitialiser tous les bordures
            radioLabels.forEach(l => {
                l.querySelector('.radio-content').style.borderWidth = '2px';
            });
            
            // Épaissir la bordure du sélectionné
            const radio = this.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
                this.querySelector('.radio-content').style.borderWidth = '3px';
            }
        });
    });
    
    // Animation des cartes
    const cards = document.querySelectorAll('.moyenne-card, .stat-card, .presence-item');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 50);
    });
});

// Fermer le modal avec Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        fermerModal();
    }
});

