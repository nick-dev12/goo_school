// Historique de présence - JavaScript

// Ouvrir le modal de justification
function ouvrirModalJustification() {
    console.log('Ouverture modal de justification');
    
    const modal = document.getElementById('modal-justifier-absence');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

// Fermer le modal
function fermerModalJustification() {
    const modal = document.getElementById('modal-justifier-absence');
    modal.classList.remove('active');
    document.body.style.overflow = 'auto';
    
    // Réinitialiser le formulaire
    document.getElementById('form-justifier-absence').reset();
}

// Fermer le modal si clic en dehors
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('modal-justifier-absence');
    
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                fermerModalJustification();
            }
        });
    }
    
    // Animation des éléments de la timeline au chargement
    const timelineItems = document.querySelectorAll('.timeline-item');
    timelineItems.forEach((item, index) => {
        item.style.opacity = '0';
        item.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            item.style.transition = 'all 0.4s ease';
            item.style.opacity = '1';
            item.style.transform = 'translateX(0)';
        }, index * 80);
    });
    
    // Animation des stats
    const statBoxes = document.querySelectorAll('.stat-box');
    statBoxes.forEach((box, index) => {
        box.style.opacity = '0';
        box.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            box.style.transition = 'all 0.4s ease';
            box.style.opacity = '1';
            box.style.transform = 'translateY(0)';
        }, index * 100);
    });
});

// Fermer le modal avec Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        fermerModalJustification();
    }
});

// Validation du formulaire avant soumission
document.getElementById('form-justifier-absence')?.addEventListener('submit', function(e) {
    const presenceId = document.getElementById('presence_id').value;
    const typeJustificatif = document.getElementById('type_justificatif').value;
    
    if (!presenceId || !typeJustificatif) {
        e.preventDefault();
        alert('Veuillez remplir tous les champs obligatoires.');
        return false;
    }
    
    // Confirmation
    const dateAbsence = document.getElementById('presence_id').selectedOptions[0].text;
    const typeLibelle = document.getElementById('type_justificatif').selectedOptions[0].text;
    
    if (!confirm(`Confirmer la justification de l'absence du ${dateAbsence} avec le motif "${typeLibelle}" ?`)) {
        e.preventDefault();
        return false;
    }
});

