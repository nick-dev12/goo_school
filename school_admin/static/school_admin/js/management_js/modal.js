/**
 * Module de gestion des modales
 * 
 * Ce module gère l'affichage et la fermeture des fenêtres modales dans l'interface.
 * Il s'occupe principalement de la modale d'ajout de membre d'équipe.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Sélectionner les éléments DOM
    const addMemberBtn = document.getElementById('addMemberBtn');
    const addMemberModal = document.getElementById('addMemberModal');
    const closeModal = document.getElementById('closeModal');
    const cancelBtn = document.getElementById('cancelBtn');
    const addMemberForm = document.getElementById('addMemberForm');

    // Fonction pour ouvrir la modale
    function openModal() {
        addMemberModal.classList.add('show');
        document.body.style.overflow = 'hidden'; // Empêche le défilement de la page
    }

    // Fonction pour fermer la modale
    function closeModalFunc() {
        addMemberModal.classList.remove('show');
        document.body.style.overflow = ''; // Rétablit le défilement de la page
        addMemberForm.reset(); // Réinitialise le formulaire
    }

    // Ouvrir la modale lors du clic sur le bouton d'ajout de membre
    addMemberBtn.addEventListener('click', openModal);

    // Fermer la modale lors du clic sur le bouton de fermeture
    closeModal.addEventListener('click', closeModalFunc);

    // Fermer la modale lors du clic sur le bouton d'annulation
    cancelBtn.addEventListener('click', closeModalFunc);

    // Fermer la modale lors du clic en dehors de celle-ci
    addMemberModal.addEventListener('click', function (e) {
        if (e.target === addMemberModal) {
            closeModalFunc();
        }
    });

    // Gestion de la soumission du formulaire
    addMemberForm.addEventListener('submit', function (e) {
        // Ne pas empêcher la soumission du formulaire
        // Le formulaire sera soumis normalement via l'attribut action
    });

    // Exposer les fonctions pour une utilisation externe
    window.modalFunctions = {
        open: openModal,
        close: closeModalFunc
    };
});