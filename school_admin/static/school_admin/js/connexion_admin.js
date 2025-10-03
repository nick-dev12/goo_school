// Connexion Admin JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Gestion de l'affichage/masquage du mot de passe
    const togglePasswordButton = document.querySelector('.toggle-password');
    const passwordInput = document.getElementById('password');

    if (togglePasswordButton && passwordInput) {
        togglePasswordButton.addEventListener('click', function () {
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                this.classList.remove('fa-eye');
                this.classList.add('fa-eye-slash');
            } else {
                passwordInput.type = 'password';
                this.classList.remove('fa-eye-slash');
                this.classList.add('fa-eye');
            }
        });
    }

    // Gestion de la soumission du formulaire
    const loginForm = document.getElementById('admin-login-form');

    if (loginForm) {
        loginForm.addEventListener('submit', function (event) {
            // Récupérer les valeurs des champs
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;

            // Validation simple des champs
            if (!username || !password) {
                event.preventDefault(); // Empêcher la soumission seulement si les champs sont vides
                alert('Veuillez remplir tous les champs.');
                return false;
            }

            // Afficher l'état de chargement
            const submitButton = this.querySelector('button[type="submit"]');
            const originalText = submitButton.innerHTML;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connexion...';
            submitButton.disabled = true;

            // Laisser le formulaire se soumettre normalement au serveur Django
            // (pas de event.preventDefault() ici)
        });
    }

    // Ajout de la classe active aux champs lors du focus
    const formInputs = document.querySelectorAll('input[type="text"], input[type="password"]');
    formInputs.forEach(input => {
        input.addEventListener('focus', function () {
            this.parentElement.classList.add('active');
        });

        input.addEventListener('blur', function () {
            this.parentElement.classList.remove('active');
        });
    });
});