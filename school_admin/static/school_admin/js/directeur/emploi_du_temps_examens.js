/**
 * Emploi du Temps des Examens - Scripts
 */

// Modal management
function openModal() {
    document.getElementById('creneauModal').classList.add('show');
}

function closeModal() {
    document.getElementById('creneauModal').classList.remove('show');
    // Réinitialiser le formulaire
    document.getElementById('creneauModal').querySelector('form').reset();
    // Réinitialiser les sélecteurs
    document.getElementById('matiere_id').innerHTML = '<option value="">Sélectionnez d\'abord un examen</option>';
    document.getElementById('matiere_id').disabled = true;
}

// Mettre à jour les matières disponibles selon la session sélectionnée
function updateMatieresForSession() {
    const sessionSelect = document.getElementById('session_examen_id');
    const matiereSelect = document.getElementById('matiere_id');
    const sessionId = sessionSelect.value;

    if (!sessionId) {
        matiereSelect.innerHTML = '<option value="">Sélectionnez d\'abord un examen</option>';
        matiereSelect.disabled = true;
        return;
    }

    // Récupérer les matières pour cette session
    const matieres = matieresParSession[sessionId];

    if (!matieres || matieres.length === 0) {
        matiereSelect.innerHTML = '<option value="">Aucune matière disponible</option>';
        matiereSelect.disabled = true;
        return;
    }

    // Remplir le select avec les matières disponibles
    matiereSelect.innerHTML = '<option value="">Sélectionnez une matière</option>';
    matieres.forEach(matiere => {
        const option = document.createElement('option');
        option.value = matiere.id;
        option.textContent = matiere.nom;
        matiereSelect.appendChild(option);
    });

    matiereSelect.disabled = false;
}

// Form validation
function validateForm() {
    const sessionExamen = document.getElementById('session_examen_id').value;
    const matiere = document.getElementById('matiere_id').value;
    const dateExamen = document.getElementById('date_examen').value;
    const heureDebut = document.getElementById('heure_debut').value;
    const heureFin = document.getElementById('heure_fin').value;
    
    if (!sessionExamen) {
        alert('Veuillez sélectionner une session d\'examen.');
        return false;
    }
    
    if (!matiere) {
        alert('Veuillez sélectionner une matière.');
        return false;
    }
    
    if (!dateExamen) {
        alert('Veuillez sélectionner une date.');
        return false;
    }
    
    if (!heureDebut || !heureFin) {
        alert('Veuillez sélectionner les heures de début et de fin.');
        return false;
    }
    
    if (heureDebut >= heureFin) {
        alert('L\'heure de fin doit être après l\'heure de début.');
        return false;
    }
    
    return true;
}

// Time validation
function validateTimes() {
    const heureDebut = document.getElementById('heure_debut').value;
    const heureFin = document.getElementById('heure_fin').value;
    
    if (heureDebut && heureFin) {
        if (heureDebut >= heureFin) {
            alert('L\'heure de fin doit être après l\'heure de début.');
            document.getElementById('heure_fin').value = '';
        }
    }
}

// Date validation
function validateDate() {
    const dateExamen = document.getElementById('date_examen').value;
    const today = new Date().toISOString().split('T')[0];
    
    if (dateExamen && dateExamen < today) {
        alert('La date de l\'examen ne peut pas être dans le passé.');
        document.getElementById('date_examen').value = '';
    }
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Ajouter les événements aux éléments
    const sessionSelect = document.getElementById('session_examen_id');
    const dateExamen = document.getElementById('date_examen');
    const heureDebut = document.getElementById('heure_debut');
    const heureFin = document.getElementById('heure_fin');
    
    if (sessionSelect) {
        sessionSelect.addEventListener('change', updateMatieresForSession);
    }
    
    if (dateExamen) {
        dateExamen.addEventListener('change', validateDate);
    }
    
    if (heureDebut) {
        heureDebut.addEventListener('change', validateTimes);
    }
    
    if (heureFin) {
        heureFin.addEventListener('change', validateTimes);
    }
    
    // Ajouter la validation au formulaire
    const form = document.querySelector('#creneauModal form');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!validateForm()) {
                e.preventDefault();
            }
        });
    }
    
    // Fermer le modal en cliquant à l'extérieur
    window.onclick = function(event) {
        const modal = document.getElementById('creneauModal');
        if (event.target == modal) {
            closeModal();
        }
    }
    
    // Fermer le modal avec la touche Escape
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closeModal();
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

// Animation pour les créneaux
function animateCreneaux() {
    const creneaux = document.querySelectorAll('.exam-block');
    creneaux.forEach((creneau, index) => {
        creneau.style.opacity = '0';
        creneau.style.transform = 'scale(0.9)';
        
        setTimeout(() => {
            creneau.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            creneau.style.opacity = '1';
            creneau.style.transform = 'scale(1)';
        }, index * 50);
    });
}

// Lancer l'animation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(animateCreneaux, 300);
});

// Fonction pour exporter l'emploi du temps en PDF (à implémenter)
function exportToPDF() {
    // Cette fonction pourrait être implémentée avec une bibliothèque comme jsPDF
    alert('Fonction d\'export PDF à implémenter');
}

// Fonction pour imprimer l'emploi du temps
function printTimetable() {
    window.print();
}

// Fonction pour filtrer par date
function filterByDate(date) {
    const daySchedules = document.querySelectorAll('.day-schedule');
    
    daySchedules.forEach(schedule => {
        const scheduleDate = schedule.querySelector('.day-header h2').textContent;
        if (date && !scheduleDate.toLowerCase().includes(date.toLowerCase())) {
            schedule.style.display = 'none';
        } else {
            schedule.style.display = 'block';
        }
    });
}

// Fonction pour rechercher dans l'emploi du temps
function searchInTimetable(searchTerm) {
    const examBlocks = document.querySelectorAll('.exam-block');
    
    examBlocks.forEach(block => {
        const text = block.textContent.toLowerCase();
        if (searchTerm && !text.includes(searchTerm.toLowerCase())) {
            block.style.opacity = '0.3';
        } else {
            block.style.opacity = '1';
        }
    });
}

// Fonction pour afficher/masquer les détails
function toggleDetails() {
    const details = document.querySelectorAll('.exam-supervisor, .exam-room');
    
    details.forEach(detail => {
        detail.style.display = detail.style.display === 'none' ? 'flex' : 'none';
    });
}

// Fonction pour changer la vue (jour/semaine/mois)
function changeView(viewType) {
    // Cette fonction pourrait être implémentée pour changer l'affichage
    alert(`Changement de vue vers: ${viewType}`);
}

// Fonction pour ajouter un créneau rapide
function quickAddCreneau() {
    // Cette fonction pourrait ouvrir un formulaire simplifié
    openModal();
}

// Fonction pour dupliquer un créneau
function duplicateCreneau(creneauId) {
    // Cette fonction pourrait dupliquer un créneau existant
    alert(`Duplication du créneau: ${creneauId}`);
}

// Fonction pour déplacer un créneau
function moveCreneau(creneauId, newDate, newTime) {
    // Cette fonction pourrait déplacer un créneau vers une nouvelle date/heure
    alert(`Déplacement du créneau: ${creneauId} vers ${newDate} ${newTime}`);
}

// Fonction pour supprimer un créneau
function deleteCreneau(creneauId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer ce créneau ?')) {
        // Cette fonction pourrait supprimer un créneau
        alert(`Suppression du créneau: ${creneauId}`);
    }
}

// Fonction pour marquer un créneau comme confirmé
function confirmCreneau(creneauId) {
    // Cette fonction pourrait marquer un créneau comme confirmé
    alert(`Confirmation du créneau: ${creneauId}`);
}

// Fonction pour annuler un créneau
function cancelCreneau(creneauId) {
    if (confirm('Êtes-vous sûr de vouloir annuler ce créneau ?')) {
        // Cette fonction pourrait annuler un créneau
        alert(`Annulation du créneau: ${creneauId}`);
    }
}

// Fonction pour générer un rapport
function generateReport() {
    // Cette fonction pourrait générer un rapport de l'emploi du temps
    alert('Génération du rapport...');
}

// Fonction pour envoyer des notifications
function sendNotifications() {
    // Cette fonction pourrait envoyer des notifications aux professeurs
    alert('Envoi des notifications...');
}

// Fonction pour vérifier les conflits
function checkConflicts() {
    // Cette fonction pourrait vérifier les conflits dans l'emploi du temps
    alert('Vérification des conflits...');
}

// Fonction pour optimiser l'emploi du temps
function optimizeTimetable() {
    // Cette fonction pourrait optimiser automatiquement l'emploi du temps
    alert('Optimisation de l\'emploi du temps...');
}