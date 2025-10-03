document.addEventListener('DOMContentLoaded', function () {
    // Modal handling
    const modal = document.getElementById('teacher-modal');
    const addTeacherBtn = document.getElementById('btn-add-teacher');
    const closeModalBtns = document.querySelectorAll('.close-modal, .close-modal-btn');
    const editBtns = document.querySelectorAll('.edit-btn');

    function openModal() {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden'; // Empêcher le défilement
    }

    function closeModal() {
        modal.classList.remove('show');
        document.body.style.overflow = ''; // Réactiver le défilement
    }

    addTeacherBtn.addEventListener('click', function () {
        document.querySelector('.modal-title').textContent = 'Ajouter un enseignant';
        document.getElementById('teacher-form').reset();
        openModal();
    });

    closeModalBtns.forEach(btn => {
        btn.addEventListener('click', closeModal);
    });

    // Fermer le modal en cliquant en dehors
    window.addEventListener('click', function (event) {
        if (event.target === modal) {
            closeModal();
        }
    });

    // Ouvrir le modal en mode édition
    editBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            const row = btn.closest('tr');
            const teacherNameElement = row.querySelector('.teacher-name');
            const teacherEmailElement = row.querySelector('.teacher-email');

            if (!teacherNameElement || !teacherEmailElement) return;

            const teacherName = teacherNameElement.textContent;
            const teacherEmail = teacherEmailElement.textContent;

            // Diviser le nom en prénom et nom de famille
            const nameParts = teacherName.split(' ');
            const firstName = nameParts[0];
            const lastName = nameParts.slice(1).join(' ');

            document.querySelector('.modal-title').textContent = 'Modifier un enseignant';

            // Remplir le formulaire avec les données de l'enseignant
            document.getElementById('teacher-firstname').value = firstName;
            document.getElementById('teacher-lastname').value = lastName;
            document.getElementById('teacher-email').value = teacherEmail;
            document.getElementById('teacher-phone').value = row.cells[2].textContent;

            // Récupérer et cocher les matières enseignées
            const subjectTags = row.querySelectorAll('.subject-tag');
            const subjects = Array.from(subjectTags).map(tag => tag.textContent);

            // Réinitialiser les cases à cocher
            document.querySelectorAll('#teacher-form input[type="checkbox"]').forEach(checkbox => {
                checkbox.checked = false;
            });

            // Cocher les matières correspondantes
            subjects.forEach(subject => {
                const checkboxId = getCheckboxIdFromSubject(subject);
                if (checkboxId) {
                    document.getElementById(checkboxId).checked = true;
                }
            });

            // Récupérer le statut
            const statusElement = row.querySelector('.teacher-status');
            if (statusElement) {
                const status = statusElement.classList.contains('status-active') ? 'active' :
                    statusElement.classList.contains('status-inactive') ? 'inactive' : 'pending';
                document.getElementById('teacher-status').value = status;
            }

            openModal();
        });
    });

    // Fonction pour obtenir l'ID de la case à cocher à partir du nom de la matière
    function getCheckboxIdFromSubject(subject) {
        const subjectMap = {
            'Mathématiques': 'subject-math',
            'Français': 'subject-french',
            'Histoire-Géo': 'subject-history',
            'EMC': 'subject-history',
            'Anglais': 'subject-english',
            'SVT': 'subject-science',
            'Physique-Chimie': 'subject-science',
            'EPS': 'subject-sport',
            'Arts Plastiques': 'subject-art',
            'Musique': 'subject-music',
            'Latin': 'subject-french'
        };

        return subjectMap[subject];
    }

    // Supprimer un enseignant (avec confirmation)
    const deleteBtns = document.querySelectorAll('.delete-btn');
    deleteBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            const row = btn.closest('tr');
            const teacherName = row.querySelector('.teacher-name').textContent;

            if (confirm(`Êtes-vous sûr de vouloir supprimer l'enseignant ${teacherName} ?`)) {
                // Animation de suppression
                row.style.transition = 'all 0.3s ease';
                row.style.opacity = '0';
                row.style.transform = 'translateX(20px)';

                setTimeout(() => {
                    row.remove();
                    // Afficher une notification de succès
                    showNotification(`L'enseignant ${teacherName} a été supprimé avec succès.`, 'success');
                }, 300);
            }
        });
    });

    // Enregistrer l'enseignant
    const saveTeacherBtn = document.querySelector('.save-teacher-btn');
    saveTeacherBtn.addEventListener('click', function () {
        const form = document.getElementById('teacher-form');

        // Réinitialiser les messages d'erreur
        const errorGroups = document.querySelectorAll('.form-group.error');
        errorGroups.forEach(group => group.classList.remove('error'));

        if (form.checkValidity()) {
            // Simuler l'enregistrement
            const firstName = document.getElementById('teacher-firstname').value;
            const lastName = document.getElementById('teacher-lastname').value;
            const fullName = `${firstName} ${lastName}`;
            const isEdit = document.querySelector('.modal-title').textContent.includes('Modifier');

            // Fermer le modal
            closeModal();

            // Afficher une notification de succès
            const message = isEdit
                ? `L'enseignant ${fullName} a été modifié avec succès.`
                : `L'enseignant ${fullName} a été ajouté avec succès.`;

            showNotification(message, 'success');

            // Recharger la page après un court délai pour voir les changements
            // Dans une application réelle, vous mettriez à jour le DOM directement
            if (!isEdit) {
                setTimeout(() => {
                    location.reload();
                }, 1500);
            }
        } else {
            // Marquer les champs invalides
            const invalidFields = form.querySelectorAll(':invalid');
            invalidFields.forEach(field => {
                field.closest('.form-group').classList.add('error');
            });

            // Afficher une notification d'erreur
            showNotification('Veuillez remplir tous les champs obligatoires.', 'error');

            // Déclencher la validation native du formulaire
            form.reportValidity();
        }
    });

    // Fonction pour afficher des notifications
    function showNotification(message, type = 'info') {
        // Créer l'élément de notification
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;

        // Ajouter l'icône en fonction du type
        let icon = 'info-circle';
        if (type === 'success') icon = 'check-circle';
        if (type === 'error') icon = 'exclamation-triangle';

        notification.innerHTML = `
                <i class="fas fa-${icon}"></i>
                <span>${message}</span>
                <button class="close-notification"><i class="fas fa-times"></i></button>
            `;

        // Ajouter au DOM
        if (!document.querySelector('.notifications-container')) {
            const container = document.createElement('div');
            container.className = 'notifications-container';
            document.body.appendChild(container);
        }

        document.querySelector('.notifications-container').appendChild(notification);

        // Animer l'entrée
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        // Fermer automatiquement après 5 secondes
        setTimeout(() => {
            closeNotification(notification);
        }, 5000);

        // Ajouter un gestionnaire d'événements pour fermer manuellement
        notification.querySelector('.close-notification').addEventListener('click', function () {
            closeNotification(notification);
        });
    }

    function closeNotification(notification) {
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();

            // Supprimer le conteneur s'il est vide
            const container = document.querySelector('.notifications-container');
            if (container && !container.hasChildNodes()) {
                container.remove();
            }
        }, 300);
    }
});