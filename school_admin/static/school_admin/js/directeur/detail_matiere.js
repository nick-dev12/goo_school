/**
 * Script pour la page de détails de matière
 * Toute la validation est gérée côté Django
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de détails de matière chargée');
    
    // Initialiser le formulaire
    initializeFormValidation();
});

/**
 * Basculer l'affichage du formulaire de modification
 */
function toggleEditForm() {
    console.log('toggleEditForm appelé');
    const editFormContainer = document.getElementById('editFormContainer');
    const editButton = document.querySelector('.btn-add.btn-primary, .btn-add.btn-secondary');
    
    console.log('editFormContainer:', editFormContainer);
    console.log('editButton:', editButton);
    
    if (editFormContainer) {
        const isVisible = editFormContainer.style.display === 'block';
        console.log('isVisible:', isVisible);
        
        if (!isVisible) {
            console.log('Affichage du formulaire');
            // Afficher le formulaire avec position fixe
            editFormContainer.style.display = 'block';
            editFormContainer.style.position = 'fixed';
            editFormContainer.style.top = '50%';
            editFormContainer.style.left = '50%';
            editFormContainer.style.transform = 'translate(-50%, -50%)';
            editFormContainer.style.zIndex = '1000';
            editFormContainer.style.backgroundColor = 'white';
            editFormContainer.style.borderRadius = '12px';
            editFormContainer.style.boxShadow = '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)';
            editFormContainer.style.maxWidth = '600px';
            editFormContainer.style.width = '90%';
            editFormContainer.style.maxHeight = '90vh';
            editFormContainer.style.overflowY = 'auto';
            
            // Ajouter un overlay
            let overlay = document.getElementById('editFormOverlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'editFormOverlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100%';
                overlay.style.height = '100%';
                overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
                overlay.style.zIndex = '999';
                overlay.style.cursor = 'pointer';
                document.body.appendChild(overlay);
                
                // Fermer le formulaire en cliquant sur l'overlay
                overlay.addEventListener('click', function() {
                    toggleEditForm();
                });
            }
            
            // Changer le texte du bouton
            if (editButton) {
                editButton.innerHTML = '<i class="fas fa-times"></i><span>Annuler</span>';
                editButton.classList.remove('btn-primary');
                editButton.classList.add('btn-secondary');
            }
            
            // Focus sur le premier champ
            const firstInput = editFormContainer.querySelector('input, select');
            if (firstInput) {
                setTimeout(() => {
                    firstInput.focus();
                }, 300);
            }
        } else {
            console.log('Masquage du formulaire');
            // Masquer le formulaire
            editFormContainer.style.display = 'none';
            
            // Supprimer l'overlay
            const overlay = document.getElementById('editFormOverlay');
            if (overlay) {
                overlay.remove();
            }
            
            // Remettre le texte du bouton
            if (editButton) {
                editButton.innerHTML = '<i class="fas fa-edit"></i><span>Modifier</span>';
                editButton.classList.remove('btn-secondary');
                editButton.classList.add('btn-primary');
            }
        }
    } else {
        console.error('editFormContainer non trouvé');
    }
}

/**
 * Initialiser le formulaire (sans validation JavaScript)
 */
function initializeFormValidation() {
    console.log('Formulaire de modification initialisé (validation côté serveur uniquement)');
}

/**
 * Fonction globale pour confirmer la suppression
 */
window.confirmDelete = function() {
    if (confirm('Êtes-vous sûr de vouloir supprimer cette matière ? Cette action est irréversible.')) {
        // Rediriger vers l'URL de suppression
        const matiereId = window.location.pathname.split('/')[2];
        window.location.href = `/matieres/${matiereId}/supprimer/`;
    }
};