/**
 * Gestion AJAX pour la notation des élèves (Primaire)
 * - Enregistrement des notes sans rechargement
 * - Calcul des moyennes sans rechargement
 * - Notifications toast élégantes
 * - Conservation de l'onglet actif
 */

document.addEventListener('DOMContentLoaded', function() {
    // Fonction pour obtenir le formulaire de la matière active
    function getActiveForm() {
        const activeTab = document.querySelector('.matiere-tab-content.active');
        if (!activeTab) return null;
        return activeTab.querySelector('.notation-form');
    }
    
    // Récupérer le token CSRF
    function getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    // ==============================================
    // FONCTION : Afficher une notification toast
    // ==============================================
    function showToast(message, type = 'success') {
        // Créer le conteneur si nécessaire
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 99999;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(toastContainer);
        }

        // Créer le toast
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = type === 'success' ? '✓' : (type === 'error' ? '✗' : 'ℹ');
        const bgColor = type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : '#3b82f6');
        
        toast.style.cssText = `
            background: ${bgColor};
            color: white;
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 14px;
            font-weight: 500;
            min-width: 300px;
            max-width: 500px;
            animation: slideInRight 0.3s ease;
        `;
        
        toast.innerHTML = `
            <span style="font-size: 20px; font-weight: bold;">${icon}</span>
            <span>${message}</span>
        `;

        toastContainer.appendChild(toast);

        // Supprimer après 4 secondes
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // Ajouter les animations CSS
    if (!document.getElementById('toast-animations')) {
        const style = document.createElement('style');
        style.id = 'toast-animations';
        style.textContent = `
            @keyframes slideInRight {
                from {
                    transform: translateX(400px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            @keyframes slideOutRight {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(400px);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // ==============================================
    // FONCTION : Compter les évaluations sélectionnées
    // ==============================================
    function updateSelectionCount() {
        const checkboxes = document.querySelectorAll('.eval-checkbox:checked');
        const countElement = document.getElementById('count-selected');
        if (countElement) {
            countElement.textContent = checkboxes.length;
        }
    }

    // Écouter les changements de checkboxes
    document.querySelectorAll('.eval-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectionCount);
    });

    // ==============================================
    // GESTION : Enregistrement des notes (AJAX)
    // ==============================================
    document.addEventListener('click', function(e) {
        const button = e.target.closest('button[name="action"][value="enregistrer"]');
        if (!button) return;
        
        e.preventDefault();
        
        const form = getActiveForm();
        if (!form) {
            showToast('Formulaire introuvable', 'error');
            return;
        }
        
        // Récupérer les données du formulaire
        const formData = new FormData(form);
        formData.set('action', 'enregistrer');

        // Désactiver le bouton
        button.disabled = true;
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enregistrement...';

        // Construire l'URL complète
        const formAction = form.getAttribute('action');
        const url = formAction.startsWith('http') ? formAction : (window.location.pathname + formAction);
        
        // Envoyer via AJAX
        fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                throw new Error('Réponse inattendue du serveur');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Notes enregistrées avec succès !', 'success');
                
                // Mettre à jour visuellement les notes enregistrées
                const activeTab = document.querySelector('.matiere-tab-content.active');
                if (activeTab && data.notes_enregistrees) {
                    Object.entries(data.notes_enregistrees).forEach(([noteKey, noteValue]) => {
                        // noteKey format: "note_eleveID_evalID" ou "note_eleveID_examen_creneauID"
                        const input = activeTab.querySelector(`input[name="${noteKey}"]`);
                        if (input) {
                            // Convertir la virgule en point pour les inputs de type number
                            const valueToSet = input.type === 'number' ? noteValue.replace(',', '.') : noteValue;
                            input.value = valueToSet;
                            
                            // Marquer visuellement comme enregistré
                            const cell = input.closest('td');
                            if (cell) {
                                cell.classList.add('note-saved');
                            }
                        }
                    });
                }
            } else {
                const hasErrors = Array.isArray(data.errors) && data.errors.length > 0;
                const message = data.message || (hasErrors ? 'Erreur lors de l\'enregistrement' : 'Aucune note n\'a été modifiée.');
                showToast(message, hasErrors ? 'error' : 'info');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showToast('Erreur de connexion au serveur', 'error');
        })
        .finally(() => {
            // Réactiver le bouton
            button.disabled = false;
            button.innerHTML = originalHTML;
        });
    });

    // ==============================================
    // GESTION : Calcul des moyennes (AJAX)
    // ==============================================
    document.addEventListener('click', function(e) {
        const button = e.target.closest('button[name="action"][value="calculer"]');
        if (!button) return;
        
        e.preventDefault();
        e.stopPropagation();
        
        const form = getActiveForm();
        if (!form) {
            showToast('Formulaire introuvable', 'error');
            return;
        }
        
        // Vérifier qu'au moins une évaluation est sélectionnée
        const activeTab = document.querySelector('.matiere-tab-content.active');
        const selectedEvals = activeTab.querySelectorAll('.eval-checkbox:checked');
        if (selectedEvals.length === 0) {
            showToast('⚠️ Veuillez sélectionner au moins une évaluation', 'error');
            return;
        }

        // Récupérer les données du formulaire
        const formData = new FormData(form);
        formData.set('action', 'calculer');

        // Désactiver le bouton
        button.disabled = true;
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Calcul en cours...';

        // Construire l'URL complète
        const formAction = form.getAttribute('action');
        const url = formAction.startsWith('http') ? formAction : (window.location.pathname + formAction);
        
        // Envoyer via AJAX
        fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                throw new Error('Réponse inattendue du serveur');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Moyennes calculées avec succès !', 'success');
                
                // Mettre à jour les moyennes dans le tableau
                if (data.moyennes) {
                    Object.entries(data.moyennes).forEach(([eleveId, moyenne]) => {
                        const moyenneInput = activeTab.querySelector(`input[name="moyenne_${eleveId}"]`);
                        if (moyenneInput) {
                            moyenneInput.value = moyenne;
                        }
                    });
                }

                // Mettre à jour les compteurs de notes retenues
                if (data.notes_retenues) {
                    // ÉTAPE 1 : Réinitialiser UNIQUEMENT les évaluations normales (pas les examens) à "Non retenue"
                    const allRetenueStatuses = activeTab.querySelectorAll('.retenue-status');
                    allRetenueStatuses.forEach(status => {
                        const evalId = status.getAttribute('data-eval-id');
                        // Ne réinitialiser que si ce n'est PAS un examen (les examens ont un ID qui commence par 'examen_')
                        if (evalId && !evalId.startsWith('examen_')) {
                            status.innerHTML = '<i class="fas fa-minus-circle"></i> Non retenue';
                            status.className = 'retenue-status retenue-inactive';
                        }
                    });
                    
                    // ÉTAPE 2 : Mettre à jour toutes celles qui sont retenues (y compris les examens)
                    Object.entries(data.notes_retenues).forEach(([evalId, count]) => {
                        const retenueStatus = activeTab.querySelector(`.retenue-status[data-eval-id="${evalId}"]`);
                        if (retenueStatus && count > 0) {
                            retenueStatus.innerHTML = `<i class="fas fa-check-circle"></i> ${count} Retenue${count > 1 ? 's' : ''}`;
                            retenueStatus.className = 'retenue-status retenue-active';
                        }
                    });
                }
            } else {
                showToast(data.message || 'Erreur lors du calcul', 'error');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showToast('Erreur de connexion au serveur', 'error');
        })
        .finally(() => {
            // Réactiver le bouton
            button.disabled = false;
            button.innerHTML = originalHTML;
        });
    });

    // ==============================================
    // GESTION : Arrondir les moyennes (AJAX)
    // ==============================================
    document.addEventListener('click', function(e) {
        const button = e.target.closest('button[name="action"][value="arrondir"]');
        if (!button) return;
        
        e.preventDefault();
        e.stopPropagation();
        
        const form = getActiveForm();
        if (!form) {
            showToast('Formulaire introuvable', 'error');
            return;
        }
        
        const formData = new FormData(form);
        formData.set('action', 'arrondir');

        button.disabled = true;
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Arrondissement...';

        const activeTab = document.querySelector('.matiere-tab-content.active');
        
        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                throw new Error('Réponse inattendue du serveur');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Moyennes arrondies avec succès !', 'success');
                
                // Mettre à jour les moyennes arrondies
                if (data.moyennes) {
                    Object.entries(data.moyennes).forEach(([eleveId, moyenne]) => {
                        const moyenneInput = activeTab.querySelector(`input[name="moyenne_${eleveId}"]`);
                        if (moyenneInput) {
                            moyenneInput.value = moyenne;
                        }
                    });
                }
            } else {
                showToast(data.message || 'Erreur lors de l\'arrondissement', 'error');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showToast('Erreur de connexion au serveur', 'error');
        })
        .finally(() => {
            button.disabled = false;
            button.innerHTML = originalHTML;
        });
    });
});

