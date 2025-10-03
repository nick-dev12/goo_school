/**
 * Script pour l'ajout d'établissement - Interface commerciale
 * Gestion des étapes, validation et soumission du formulaire
 */

class EtablissementForm {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 2;
        this.form = document.getElementById('etablissementForm');
        this.steps = document.querySelectorAll('.form-step');
        this.progressSteps = document.querySelectorAll('.step');
        this.nextBtn = document.getElementById('nextBtn');
        this.prevBtn = document.getElementById('prevBtn');
        this.submitBtn = document.getElementById('submitBtn');

        this.init();
    }

    init() {
        this.bindEvents();
        this.updateProgressSteps();
        this.updateFormActions();
    }

    bindEvents() {
        // Navigation entre les étapes
        this.nextBtn.addEventListener('click', () => this.nextStep());
        this.prevBtn.addEventListener('click', () => this.prevStep());

        // Soumission du formulaire
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        // Validation en temps réel
        this.bindValidationEvents();

    }

    bindValidationEvents() {
        const inputs = this.form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', () => this.validateField(input));
            input.addEventListener('input', () => this.clearFieldError(input));
        });
    }


    nextStep() {
        if (this.validateCurrentStep()) {
            if (this.currentStep < this.totalSteps) {
                this.currentStep++;
                this.showStep(this.currentStep);
                this.updateProgressSteps();
                this.updateFormActions();
                this.scrollToTop();
            }
        }
    }

    prevStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.showStep(this.currentStep);
            this.updateProgressSteps();
            this.updateFormActions();
            this.scrollToTop();
        }
    }

    showStep(stepNumber) {
        this.steps.forEach((step, index) => {
            step.classList.toggle('active', index + 1 === stepNumber);
        });
    }

    updateProgressSteps() {
        this.progressSteps.forEach((step, index) => {
            const stepNumber = index + 1;
            step.classList.remove('active', 'completed');

            if (stepNumber < this.currentStep) {
                step.classList.add('completed');
            } else if (stepNumber === this.currentStep) {
                step.classList.add('active');
            }
        });
    }

    updateFormActions() {
        // Bouton Précédent
        this.prevBtn.style.display = this.currentStep > 1 ? 'flex' : 'none';

        // Bouton Suivant/Valider
        if (this.currentStep < this.totalSteps) {
            this.nextBtn.style.display = 'flex';
            this.submitBtn.style.display = 'none';
        } else {
            this.nextBtn.style.display = 'none';
            this.submitBtn.style.display = 'flex';
        }
    }

    validateCurrentStep() {
        const currentStepElement = document.getElementById(`step${this.currentStep}`);
        const requiredFields = currentStepElement.querySelectorAll('[required]');
        let isValid = true;

        requiredFields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });

        if (!isValid) {
            this.showStepError('Veuillez remplir tous les champs obligatoires');
        }

        return isValid;
    }

    validateField(field) {
        const value = field.value.trim();
        const isRequired = field.hasAttribute('required');
        const fieldContainer = field.closest('.form-group');

        // Supprimer les erreurs existantes
        this.clearFieldError(field);

        if (isRequired && !value) {
            this.showFieldError(field, 'Ce champ est obligatoire');
            return false;
        }

        // Validation spécifique par type
        if (value) {
            if (field.type === 'number' && field.min && parseInt(value) < parseInt(field.min)) {
                this.showFieldError(field, `La valeur doit être supérieure à ${field.min}`);
                return false;
            }
        }

        return true;
    }

    showFieldError(field, message) {
        const fieldContainer = field.closest('.form-group');
        const errorElement = document.createElement('div');
        errorElement.className = 'field-error';
        errorElement.textContent = message;
        errorElement.style.color = 'var(--warning)';
        errorElement.style.fontSize = '0.8rem';
        errorElement.style.marginTop = '0.25rem';

        fieldContainer.appendChild(errorElement);
        field.style.borderColor = 'var(--warning)';
    }

    clearFieldError(field) {
        const fieldContainer = field.closest('.form-group');
        const errorElement = fieldContainer.querySelector('.field-error');
        if (errorElement) {
            errorElement.remove();
        }
        field.style.borderColor = '';
    }

    showStepError(message) {
        // Supprimer les erreurs existantes
        const existingError = document.querySelector('.step-error');
        if (existingError) {
            existingError.remove();
        }

        const errorElement = document.createElement('div');
        errorElement.className = 'step-error';
        errorElement.style.cssText = `
            background: var(--warning-light);
            color: var(--warning);
            padding: 1rem;
            border-radius: var(--radius);
            margin-bottom: 1rem;
            border-left: 4px solid var(--warning);
            font-weight: 500;
        `;
        errorElement.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;

        const currentStepElement = document.getElementById(`step${this.currentStep}`);
        currentStepElement.insertBefore(errorElement, currentStepElement.firstChild);

        // Supprimer l'erreur après 5 secondes
        setTimeout(() => {
            if (errorElement.parentNode) {
                errorElement.remove();
            }
        }, 5000);
    }


    handleSubmit(e) {
        // Validation avant soumission
        if (!this.validateCurrentStep()) {
            e.preventDefault();
            return;
        }

        // Afficher l'état de chargement
        this.submitBtn.classList.add('loading');
        this.submitBtn.disabled = true;

        // Laisser le formulaire se soumettre normalement via POST
        // Le serveur gérera la sauvegarde et la redirection
    }



    scrollToTop() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }

}

// Initialisation du formulaire quand le DOM est chargé
document.addEventListener('DOMContentLoaded', () => {
    new EtablissementForm();
});

// Gestion des erreurs globales
window.addEventListener('error', (e) => {
    console.error('Erreur JavaScript:', e.error);
});

// Gestion des erreurs de promesses non capturées
window.addEventListener('unhandledrejection', (e) => {
    console.error('Promesse rejetée:', e.reason);
    e.preventDefault();
});
