// Inscription Admin JavaScript - Version avec navigation par étapes

document.addEventListener('DOMContentLoaded', function () {
    let currentStep = 1;
    const totalSteps = 2;  // Le formulaire n'a que 2 étapes dans le HTML

    // Gestion de l'upload de fichier
    const photoInput = document.getElementById('photo');
    const fileNameDisplay = document.getElementById('file-name');

    if (photoInput && fileNameDisplay) {
        photoInput.addEventListener('change', function () {
            if (this.files && this.files[0]) {
                fileNameDisplay.textContent = this.files[0].name;
            } else {
                fileNameDisplay.textContent = 'Aucun fichier sélectionné';
            }
        });
    }

    // Gestion de l'affichage/masquage des mots de passe
    const togglePasswordButtons = document.querySelectorAll('.toggle-password');

    togglePasswordButtons.forEach(button => {
        button.addEventListener('click', function () {
            const passwordInput = this.previousElementSibling;

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
    });

    // Vérification de la force du mot de passe
    const passwordInput = document.getElementById('password');
    const strengthIndicator = document.querySelector('.strength-indicator');

    if (passwordInput && strengthIndicator) {
        passwordInput.addEventListener('input', function () {
            const password = this.value;
            let strength = 0;

            // Critères de force du mot de passe
            if (password.length >= 8) strength += 1;
            if (/[a-z]/.test(password)) strength += 1;
            if (/[A-Z]/.test(password)) strength += 1;
            if (/[0-9]/.test(password)) strength += 1;
            if (/[^a-zA-Z0-9]/.test(password)) strength += 1;

            // Mise à jour de l'indicateur visuel
            let percentage = (strength / 5) * 100;
            strengthIndicator.style.width = percentage + '%';

            // Couleur selon la force
            if (strength <= 1) {
                strengthIndicator.style.backgroundColor = '#ef4444'; // Rouge
            } else if (strength <= 3) {
                strengthIndicator.style.backgroundColor = '#f59e0b'; // Orange
            } else {
                strengthIndicator.style.backgroundColor = '#10b981'; // Vert
            }
        });
    }

    // Navigation entre les étapes
    const nextButton = document.getElementById('next-step');
    const prevButton = document.getElementById('prev-step');
    const submitButton = document.getElementById('submit-form');
    const steps = document.querySelectorAll('.step');
    const formSteps = document.querySelectorAll('.form-step');

    // Fonction pour mettre à jour l'affichage des étapes
    function updateSteps() {
        // Mettre à jour l'indicateur d'étapes
        steps.forEach((step, index) => {
            step.classList.remove('active', 'completed');
            if (index + 1 < currentStep) {
                step.classList.add('completed');
            } else if (index + 1 === currentStep) {
                step.classList.add('active');
            }
        });

        // Afficher/masquer les étapes du formulaire
        formSteps.forEach((step, index) => {
            step.classList.remove('active');
            if (index + 1 === currentStep) {
                step.classList.add('active');
            }
        });

        // Mettre à jour les boutons
        prevButton.style.display = currentStep > 1 ? 'flex' : 'none';
        nextButton.style.display = currentStep < totalSteps ? 'flex' : 'none';
        submitButton.style.display = currentStep === totalSteps ? 'flex' : 'none';
    }

    // Fonction pour valider l'étape actuelle
    function validateCurrentStep() {
        const currentFormStep = document.querySelector(`.form-step[data-step="${currentStep}"]`);
        const requiredFields = currentFormStep.querySelectorAll('[required]');
        let isValid = true;

        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                isValid = false;
                field.classList.add('invalid');
                field.style.borderColor = '#e11d48';
                setTimeout(() => {
                    field.style.borderColor = '';
                }, 2000);
            } else {
                field.classList.remove('invalid');
            }
        });

        // Validation spéciale pour l'étape 2 (informations professionnelles et mots de passe)
        if (currentStep === 2) {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm-password').value;

            if (password !== confirmPassword) {
                isValid = false;
                alert('Les mots de passe ne correspondent pas.');
                document.getElementById('confirm-password').focus();
            }

            if (password.length < 8) {
                isValid = false;
                alert('Le mot de passe doit contenir au moins 8 caractères.');
                document.getElementById('password').focus();
            }

            // Validation des champs professionnels
            const typeCompte = document.getElementById('type_compte').value;
            const departement = document.getElementById('departement').value;
            const fonction = document.getElementById('fonction').value;

            if (!typeCompte || !departement || !fonction) {
                isValid = false;
                alert('Veuillez remplir tous les champs professionnels obligatoires.');
            }
        }

        return isValid;
    }

    // Bouton suivant
    nextButton.addEventListener('click', function () {
        if (validateCurrentStep()) {
            currentStep++;
            updateSteps();
        }
    });

    // Bouton précédent
    prevButton.addEventListener('click', function () {
        currentStep--;
        updateSteps();
    });

    // Soumission du formulaire
    const registrationForm = document.getElementById('admin-registration-form');

    if (registrationForm) {
        registrationForm.addEventListener('submit', function (event) {
            if (!validateCurrentStep()) {
                event.preventDefault();
                return false;
            }
        });
    }

    // Ajout de la classe active aux champs lors du focus
    const formInputs = document.querySelectorAll('input, select');
    formInputs.forEach(input => {
        input.addEventListener('focus', function () {
            this.parentElement.classList.add('active');
        });

        input.addEventListener('blur', function () {
            this.parentElement.classList.remove('active');
        });
    });

    // Supprimer la classe has-error et le message d'erreur quand l'utilisateur commence à saisir
    const formGroups = document.querySelectorAll('.form-group');
    formGroups.forEach(group => {
        const inputs = group.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('input', function () {
                // Supprimer la classe has-error du parent
                const formGroup = this.closest('.form-group');
                if (formGroup && formGroup.classList.contains('has-error')) {
                    // Vérifier si le champ est maintenant valide
                    if (this.value.trim() !== '') {
                        formGroup.classList.remove('has-error');
                        // Supprimer le message d'erreur s'il existe
                        const errorMessage = formGroup.querySelector('.error-message');
                        if (errorMessage) {
                            errorMessage.remove();
                        }
                    }
                }
            });

            // Pour les champs de mot de passe, vérifier aussi la correspondance
            if (input.id === 'password' || input.id === 'confirm-password') {
                input.addEventListener('input', function () {
                    const passwordField = document.getElementById('password');
                    const confirmPasswordField = document.getElementById('confirm-password');
                    const passwordGroup = passwordField.closest('.form-group');
                    const confirmPasswordGroup = confirmPasswordField.closest('.form-group');

                    if (passwordField.value && confirmPasswordField.value) {
                        if (passwordField.value === confirmPasswordField.value && passwordField.value.length >= 8) {
                            passwordGroup.classList.remove('has-error');
                            confirmPasswordGroup.classList.remove('has-error');
                            const errorMessages = [passwordGroup, confirmPasswordGroup].map(g => g.querySelector('.error-message')).filter(m => m);
                            errorMessages.forEach(msg => msg.remove());
                        }
                    }
                });
            }
        });
    });

    // Initialisation
    updateSteps();
});