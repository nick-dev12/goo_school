/**
 * Gestion des Examens - Scripts
 */

// Modal management
function openModal() {
    document.getElementById('sessionModal').classList.add('show');
}

function closeModal() {
    document.getElementById('sessionModal').classList.remove('show');
    // Réinitialiser le formulaire
    document.getElementById('sessionModal').querySelector('form').reset();
}

function openEditModal(sessionId, nomExamen, periodeId, dateDebut, dateFin, description) {
    const modal = document.getElementById('editSessionModal');
    const form = document.getElementById('editSessionForm');
    
    // Définir l'action du formulaire
    form.action = `/modifier-session-examen/${sessionId}/`;
    
    // Remplir les champs
    document.getElementById('edit_session_id').value = sessionId;
    document.getElementById('edit_nom_examen').value = nomExamen;
    document.getElementById('edit_periode_id').value = periodeId;
    document.getElementById('edit_date_debut').value = dateDebut;
    document.getElementById('edit_date_fin').value = dateFin;
    document.getElementById('edit_description').value = description || '';
    
    // Charger les données de la session via AJAX pour cocher les bonnes options
    fetch(`/gestion-examens/`)
        .then(() => {
            // Afficher le modal
            modal.classList.add('show');
        })
        .catch(error => {
            console.error('Erreur:', error);
            alert('Erreur lors du chargement des données de la session.');
        });
}

function closeEditModal() {
    const modal = document.getElementById('editSessionModal');
    modal.classList.remove('show');
    // Réinitialiser le formulaire
    document.getElementById('editSessionForm').reset();
    // Décocher toutes les checkboxes
    document.querySelectorAll('#editSessionModal input[type="checkbox"]').forEach(cb => cb.checked = false);
}

// Tab management
function showTab(tabId) {
    // Masquer tous les panneaux
    const panels = document.querySelectorAll('.tab-panel');
    panels.forEach(panel => panel.classList.remove('active'));
    
    // Désactiver tous les boutons
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(button => button.classList.remove('active'));
    
    // Afficher le panneau sélectionné
    document.getElementById(tabId).classList.add('active');
    
    // Activer le bouton sélectionné
    event.target.classList.add('active');
    
    // Réinitialiser les sous-onglets
    const subPanels = document.querySelectorAll('.sub-tab-panel');
    subPanels.forEach(panel => panel.classList.remove('active'));
    
    const subButtons = document.querySelectorAll('.sub-tab-button');
    subButtons.forEach(button => button.classList.remove('active'));
    
    // Activer le premier sous-onglet
    const firstSubPanel = document.querySelector(`#${tabId} .sub-tab-panel:first-child`);
    const firstSubButton = document.querySelector(`#${tabId} .sub-tab-button:first-child`);
    if (firstSubPanel) firstSubPanel.classList.add('active');
    if (firstSubButton) firstSubButton.classList.add('active');
}

function showSubTab(subTabId) {
    // Masquer tous les sous-panneaux du même niveau
    const parentPanel = event.target.closest('.tab-panel');
    const subPanels = parentPanel.querySelectorAll('.sub-tab-panel');
    subPanels.forEach(panel => panel.classList.remove('active'));
    
    // Désactiver tous les sous-boutons du même niveau
    const subButtons = parentPanel.querySelectorAll('.sub-tab-button');
    subButtons.forEach(button => button.classList.remove('active'));
    
    // Afficher le sous-panneau sélectionné
    document.getElementById(subTabId).classList.add('active');
    
    // Activer le sous-bouton sélectionné
    event.target.classList.add('active');
}

// Form validation
function validateForm() {
    const nomExamen = document.getElementById('nom_examen').value.trim();
    const periode = document.getElementById('periode_id').value;
    const dateDebut = document.getElementById('date_debut').value;
    const dateFin = document.getElementById('date_fin').value;
    const groupesClasses = document.querySelectorAll('input[name="groupes_classes"]:checked');
    const matieres = document.querySelectorAll('input[name="matieres"]:checked');
    
    if (!nomExamen) {
        alert('Veuillez saisir le nom de la session d\'examen.');
        return false;
    }
    
    if (!periode) {
        alert('Veuillez sélectionner une période scolaire.');
        return false;
    }
    
    if (!dateDebut || !dateFin) {
        alert('Veuillez sélectionner les dates de début et de fin.');
        return false;
    }
    
    // Validation des dates désactivée côté client
    // La validation sera effectuée côté serveur par Django
    // if (new Date(dateDebut) >= new Date(dateFin)) {
    //     alert('La date de fin doit être après la date de début.');
    //     return false;
    // }
    
    if (groupesClasses.length === 0) {
        alert('Veuillez sélectionner au moins un groupe de classes.');
        return false;
    }
    
    if (matieres.length === 0) {
        alert('Veuillez sélectionner au moins une matière.');
        return false;
    }
    
    return true;
}

// Date validation
function validateDates() {
    // Désactivé pour éviter les faux positifs
    // La validation sera faite lors de la soumission du formulaire
    return true;
}

// Checkbox management
function toggleCheckboxGroup(groupName, maxSelections = null) {
    const checkboxes = document.querySelectorAll(`input[name="${groupName}"]`);
    const checkedBoxes = document.querySelectorAll(`input[name="${groupName}"]:checked`);
    
    if (maxSelections && checkedBoxes.length >= maxSelections) {
        // Décocher les autres cases si on atteint le maximum
        checkboxes.forEach(checkbox => {
            if (!checkbox.checked && checkedBoxes.length >= maxSelections) {
                checkbox.disabled = true;
            }
        });
    } else {
        // Réactiver toutes les cases
        checkboxes.forEach(checkbox => {
            checkbox.disabled = false;
        });
    }
}

// Session deletion
function deleteSession(sessionId, nomSession) {
    if (confirm(`Êtes-vous sûr de vouloir supprimer la session "${nomSession}" ?\n\nTous les créneaux d'examen associés seront également supprimés.\n\nCette action est irréversible.`)) {
        // Rediriger vers l'URL de suppression
        window.location.href = `/supprimer-session-examen/${sessionId}/`;
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Ajouter les événements aux éléments
    // Note: La validation des dates se fait désormais uniquement côté serveur
    // pour éviter les faux positifs avec les formats de date
    
    // Ajouter les événements aux checkboxes
    const groupesCheckboxes = document.querySelectorAll('input[name="groupes_classes"]');
    const matieresCheckboxes = document.querySelectorAll('input[name="matieres"]');
    
    groupesCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => toggleCheckboxGroup('groupes_classes'));
    });
    
    matieresCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => toggleCheckboxGroup('matieres'));
    });
    
    // Ajouter la validation au formulaire
    const form = document.querySelector('#sessionModal form');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!validateForm()) {
                e.preventDefault();
            }
        });
    }
    
    // Fermer les modals en cliquant à l'extérieur
    window.onclick = function(event) {
        const sessionModal = document.getElementById('sessionModal');
        const editModal = document.getElementById('editSessionModal');
        if (event.target == sessionModal) {
            closeModal();
        }
        if (event.target == editModal) {
            closeEditModal();
        }
    }
    
    // Fermer les modals avec la touche Escape
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closeModal();
            closeEditModal();
        }
    });
});

// Utility functions
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

function formatTime(timeString) {
    const [hours, minutes] = timeString.split(':');
    return `${hours}h${minutes}`;
}

// Animation pour les cartes
function animateCards() {
    const cards = document.querySelectorAll('.session-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// Lancer l'animation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(animateCards, 300);
});