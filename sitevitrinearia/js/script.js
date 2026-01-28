// Configuration EmailJS
// ✅ Configuration avec vos identifiants EmailJS
const EMAILJS_CONFIG = {
    publicKey: 'snCOiYbrXCdP_U1Tf', // Votre clé publique EmailJS
    serviceID: 'service_zgrt1as', // Votre Service ID
    templateID: 'template_l5sb6bl', // Votre Template ID
    toEmail: 'ariaedu55@gmail.com' // Email de destination
};

// Vérifier si EmailJS est chargé
let emailjsLoaded = false;

// Attendre que EmailJS soit chargé
function waitForEmailJS(callback, maxAttempts = 50) {
    let attempts = 0;
    const checkInterval = setInterval(function () {
        attempts++;
        if (typeof emailjs !== 'undefined') {
            clearInterval(checkInterval);
            callback();
        } else if (attempts >= maxAttempts) {
            clearInterval(checkInterval);
            console.error('❌ EmailJS n\'a pas pu être chargé après plusieurs tentatives.');
        }
    }, 100);
}

// Initialisation EmailJS
function initEmailJS() {
    if (typeof emailjs === 'undefined') {
        console.error('❌ EmailJS n\'est pas chargé. Vérifiez que le script est inclus dans le HTML.');
        return false;
    }

    // Vérifier si la configuration est valide (vérifier qu'ils ne sont PAS les valeurs par défaut)
    if (EMAILJS_CONFIG.publicKey === 'YOUR_PUBLIC_KEY' ||
        EMAILJS_CONFIG.serviceID === 'YOUR_SERVICE_ID' ||
        EMAILJS_CONFIG.templateID === 'YOUR_TEMPLATE_ID') {
        console.error('⚠️ EmailJS n\'est pas configuré. Veuillez remplir les identifiants dans script.js');
        console.log('📝 Configuration actuelle:', EMAILJS_CONFIG);
        return false;
    }
    
    // Afficher la configuration pour vérification
    console.log('📝 Configuration EmailJS:', {
        serviceID: EMAILJS_CONFIG.serviceID,
        templateID: EMAILJS_CONFIG.templateID,
        toEmail: EMAILJS_CONFIG.toEmail
    });

    try {
        emailjs.init(EMAILJS_CONFIG.publicKey);
        emailjsLoaded = true;
        console.log('✅ EmailJS initialisé avec succès');
        console.log('📧 Email de destination:', EMAILJS_CONFIG.toEmail);
        return true;
    } catch (error) {
        console.error('❌ Erreur lors de l\'initialisation d\'EmailJS:', error);
        return false;
    }
}

// Gestion du formulaire de contact
document.addEventListener('DOMContentLoaded', function () {
    const contactForm = document.getElementById('contactForm');
    const formMessage = document.getElementById('formMessage');
    const submitBtn = document.getElementById('submitBtn');
    const submitText = document.getElementById('submitText');
    const submitIcon = document.getElementById('submitIcon');

    // Attendre que EmailJS soit chargé puis l'initialiser
    let emailjsReady = false;

    waitForEmailJS(function () {
        emailjsReady = initEmailJS();
    });

    if (contactForm) {
        contactForm.addEventListener('submit', function (e) {
            e.preventDefault(); // Empêcher la soumission par défaut

            // Vérifier si EmailJS est configuré
            if (!emailjsReady || !emailjsLoaded) {
                // Vérifier quelle est la cause du problème
                if (EMAILJS_CONFIG.publicKey === 'YOUR_PUBLIC_KEY' ||
                    EMAILJS_CONFIG.serviceID === 'YOUR_SERVICE_ID' ||
                    EMAILJS_CONFIG.templateID === 'YOUR_TEMPLATE_ID') {
                    showMessage(
                        '⚠️ EmailJS n\'est pas configuré. Veuillez configurer vos identifiants dans js/script.js (voir DEPANNAGE_EMAIL.md). En attendant, contactez-nous directement à ariaedu55@gmail.com',
                        'error'
                    );
                } else if (typeof emailjs === 'undefined') {
                    showMessage(
                        '⚠️ EmailJS n\'est pas chargé. Vérifiez votre connexion internet et que le script EmailJS est inclus dans le HTML. Contactez-nous directement à ariaedu55@gmail.com',
                        'error'
                    );
                } else {
                    showMessage(
                        '⚠️ Le service d\'envoi d\'email n\'est pas disponible. Veuillez contacter directement à ariaedu55@gmail.com',
                        'error'
                    );
                }
                resetSubmitButton();
                return;
            }

            // Désactiver le bouton pendant l'envoi
            submitBtn.disabled = true;
            submitText.textContent = 'Envoi en cours...';
            submitIcon.textContent = '⏳';

            // Masquer les messages précédents
            hideMessage();

            // Récupérer les valeurs du formulaire
            const formData = {
                nom: document.getElementById('nom').value.trim(),
                email: document.getElementById('email').value.trim(),
                telephone: document.getElementById('telephone').value.trim(),
                etablissement: document.getElementById('etablissement').value.trim(),
                type_etablissement: document.getElementById('type_etablissement').value.trim(),
                message: document.getElementById('message').value.trim()
            };

            // Validation côté client
            if (!formData.nom || !formData.email || !formData.telephone || !formData.type_etablissement || !formData.message) {
                showMessage('Veuillez remplir tous les champs obligatoires.', 'error');
                resetSubmitButton();
                return;
            }

            // Validation du numéro de téléphone (format basique)
            const phoneRegex = /^[\d\s\+\-\(\)]{8,}$/;
            if (!phoneRegex.test(formData.telephone)) {
                showMessage('Veuillez entrer un numéro de téléphone valide (minimum 8 chiffres).', 'error');
                resetSubmitButton();
                return;
            }

            // Validation de l'email
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(formData.email)) {
                showMessage('Veuillez entrer une adresse email valide.', 'error');
                resetSubmitButton();
                return;
            }

            // Préparer les paramètres pour EmailJS
            // IMPORTANT: Les noms des variables doivent correspondre EXACTEMENT à ceux dans votre template EmailJS
            const templateParams = {
                from_name: formData.nom,
                from_email: formData.email,
                telephone: formData.telephone,
                etablissement: formData.etablissement || 'Non spécifié',
                type_etablissement: formData.type_etablissement,
                message: formData.message,
                to_email: EMAILJS_CONFIG.toEmail,
                reply_to: formData.email // Pour pouvoir répondre directement
            };

            // Afficher les paramètres dans la console pour débogage
            console.log('📤 Envoi d\'email en cours...');
            console.log('📋 Paramètres envoyés:', templateParams);
            console.log('🔧 Configuration:', {
                serviceID: EMAILJS_CONFIG.serviceID,
                templateID: EMAILJS_CONFIG.templateID
            });

            // Envoyer l'email via EmailJS
            emailjs.send(EMAILJS_CONFIG.serviceID, EMAILJS_CONFIG.templateID, templateParams)
                .then(function (response) {
                    console.log('✅ Email envoyé avec succès!');
                    console.log('📊 Réponse complète:', response);
                    console.log('📧 Status:', response.status);
                    console.log('📝 Text:', response.text);
                    
                    showMessage('✅ Message envoyé avec succès ! Nous vous répondrons dans les plus brefs délais. Vérifiez votre boîte de réception (et les spams) à ariaedu55@gmail.com', 'success');
                    contactForm.reset(); // Réinitialiser le formulaire
                    resetSubmitButton();
                })
                .catch(function (error) {
                    console.error('❌ Erreur lors de l\'envoi:');
                    console.error('📊 Erreur complète:', error);
                    console.error('📧 Status:', error.status);
                    console.error('📝 Text:', error.text);
                    console.error('📋 Paramètres envoyés:', templateParams);

                    // Messages d'erreur plus détaillés selon le type d'erreur
                    let errorMessage = '❌ Une erreur est survenue lors de l\'envoi. ';

                    if (error.status === 400) {
                        errorMessage += 'Erreur 400: Vérifiez que votre template EmailJS utilise les bonnes variables. Variables attendues: from_name, from_email, telephone, etablissement, type_etablissement, message, to_email, reply_to';
                        console.error('💡 Vérifiez que votre template EmailJS contient ces variables: {{from_name}}, {{from_email}}, {{telephone}}, {{etablissement}}, {{type_etablissement}}, {{message}}, {{to_email}}, {{reply_to}}');
                    } else if (error.status === 401) {
                        errorMessage += 'Erreur 401: Vérifiez votre clé publique EmailJS.';
                    } else if (error.status === 403) {
                        errorMessage += 'Erreur 403: Accès refusé. Vérifiez vos identifiants EmailJS et que votre service est actif.';
                    } else if (error.status === 404) {
                        errorMessage += 'Erreur 404: Service ou template introuvable. Vérifiez vos Service ID et Template ID.';
                    } else if (error.status === 429) {
                        errorMessage += 'Erreur 429: Trop de requêtes. Veuillez réessayer dans quelques minutes.';
                    } else {
                        errorMessage += 'Veuillez réessayer plus tard ou nous contacter directement à ariaedu55@gmail.com';
                    }

                    showMessage(errorMessage, 'error');
                    resetSubmitButton();
                });
        });
    }

    // Fonction pour afficher les messages
    function showMessage(message, type) {
        if (!formMessage) return;

        formMessage.textContent = message;
        formMessage.className = 'form-message form-message-' + type;
        formMessage.style.display = 'block';

        // Faire défiler vers le message
        formMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Masquer automatiquement après 5 secondes pour les messages de succès
        if (type === 'success') {
            setTimeout(function () {
                hideMessage();
            }, 5000);
        }
    }

    // Fonction pour masquer les messages
    function hideMessage() {
        if (!formMessage) return;
        formMessage.style.display = 'none';
        formMessage.textContent = '';
        formMessage.className = 'form-message';
    }

    // Fonction pour réinitialiser le bouton de soumission
    function resetSubmitButton() {
        if (!submitBtn || !submitText || !submitIcon) return;
        submitBtn.disabled = false;
        submitText.textContent = 'Envoyer le message';
        submitIcon.textContent = '→';
    }

    // Gestion du menu mobile (si nécessaire)
    const menuToggle = document.getElementById('menuToggle');
    const navMenu = document.getElementById('navMenu');

    if (menuToggle && navMenu) {
        menuToggle.addEventListener('click', function () {
            navMenu.classList.toggle('active');
        });

        // Fermer le menu lors du clic sur un lien
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function () {
                navMenu.classList.remove('active');
            });
        });
    }

    // Gestion des modals (si nécessaire)
    const modalButtons = document.querySelectorAll('[data-modal]');
    const modals = document.querySelectorAll('.modal-fullscreen');
    const closeButtons = document.querySelectorAll('.modal-close');

    modalButtons.forEach(button => {
        button.addEventListener('click', function () {
            const modalId = this.getAttribute('data-modal');
            const modal = document.getElementById('modal-' + modalId);
            if (modal) {
                modal.classList.add('active');
                document.body.style.overflow = 'hidden';
            }
        });
    });

    closeButtons.forEach(button => {
        button.addEventListener('click', function () {
            modals.forEach(modal => {
                modal.classList.remove('active');
            });
            document.body.style.overflow = '';
        });
    });

    // Fermer les modals en cliquant en dehors
    modals.forEach(modal => {
        modal.addEventListener('click', function (e) {
            if (e.target === this) {
                this.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
});
