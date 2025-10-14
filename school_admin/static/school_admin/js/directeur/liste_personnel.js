/**
 * Liste Personnel - JavaScript
 * Fonctionnalités pour la page de gestion du personnel avec onglets
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de gestion du personnel chargée');
    
    // Initialiser les interactions
    initializeTabs();
    updateTabCounts();
    initializePersonnelCards();
    initializeMatiereFilter();
});

/**
 * Initialiser le système d'onglets
 */
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');
            
            // Retirer la classe active de tous les boutons
            tabButtons.forEach(btn => btn.classList.remove('active'));
            
            // Retirer la classe active de tous les panneaux
            tabPanes.forEach(pane => pane.classList.remove('active'));
            
            // Ajouter la classe active au bouton cliqué
            this.classList.add('active');
            
            // Afficher le panneau correspondant
            const targetPane = document.getElementById(`${targetTab}-pane`);
            if (targetPane) {
                targetPane.classList.add('active');
            }
            
            // Mettre à jour les compteurs
            updateTabCounts();
        });
    });
}

/**
 * Mettre à jour les compteurs des onglets
 */
function updateTabCounts() {
    const counts = {
        professeurs: 0,
        secretaires: 0,
        censeurs: 0,
        surveillants: 0,
        intendants: 0
    };
    
    // Compter les cartes dans chaque onglet
    Object.keys(counts).forEach(tab => {
        const grid = document.getElementById(`${tab}-grid`);
        if (grid) {
            const cards = grid.querySelectorAll('.personnel-card');
            counts[tab] = cards.length;
            
            // Mettre à jour l'affichage du compteur
            const countElement = document.getElementById(`${tab}-count`);
            if (countElement) {
                countElement.textContent = counts[tab];
            }
        }
    });
}

/**
 * Initialiser les interactions des cartes du personnel
 */
function initializePersonnelCards() {
    const personnelCards = document.querySelectorAll('.personnel-card');
    
    personnelCards.forEach(card => {
        // Effet de survol
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
            this.style.borderColor = '#3b82f6';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 1px 2px 0 rgba(0, 0, 0, 0.05)';
            this.style.borderColor = '#e5e7eb';
        });
    });
    
    // Initialiser les boutons d'action
    initializeActionButtons();
}

/**
 * Initialiser les boutons d'action
 */
function initializeActionButtons() {
    const toggleButtons = document.querySelectorAll('.btn-toggle');
    
    toggleButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const url = this.getAttribute('href');
            const isActive = this.classList.contains('active');
            
            // Confirmer l'action
            const action = isActive ? 'désactiver' : 'activer';
            const confirmed = confirm(`Êtes-vous sûr de vouloir ${action} ce membre du personnel ?`);
            
            if (confirmed) {
                // Effectuer la requête
                fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'Content-Type': 'application/json',
                    },
                })
                .then(response => {
                    if (response.ok) {
                        // Recharger la page pour voir les changements
                        window.location.reload();
                    } else {
                        showTemporaryMessage('Erreur lors de la modification du statut', 'error');
                    }
                })
                .catch(error => {
                    console.error('Erreur:', error);
                    showTemporaryMessage('Erreur lors de la modification du statut', 'error');
                });
            }
        });
    });
}

/**
 * Obtenir le token CSRF
 */
function getCSRFToken() {
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfToken ? csrfToken.value : '';
}

/**
 * Afficher un message temporaire
 */
function showTemporaryMessage(message, type = 'info') {
    // Créer l'élément de message
    const messageEl = document.createElement('div');
    messageEl.className = `temp-message temp-message-${type}`;
    messageEl.textContent = message;
    
    // Styles du message
    const bgColor = type === 'info' ? '#3b82f6' : '#ef4444';
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: ${bgColor};
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        z-index: 1000;
        opacity: 0;
        transform: translateY(-20px);
        transition: all 0.5s ease;
    `;
    
    document.body.appendChild(messageEl);
    
    // Animer l'apparition
    setTimeout(() => {
        messageEl.style.opacity = '1';
        messageEl.style.transform = 'translateY(0)';
    }, 100);
    
    // Animer la disparition après 3 secondes
    setTimeout(() => {
        messageEl.style.opacity = '0';
        messageEl.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            messageEl.remove();
        }, 500);
    }, 3000);
}

/**
 * Initialiser le filtre de matières pour les professeurs
 */
function initializeMatiereFilter() {
    const matiereSelect = document.getElementById('matiere-select');
    
    if (matiereSelect) {
        matiereSelect.addEventListener('change', function() {
            const selectedMatiereId = this.value;
            const professeurCards = document.querySelectorAll('.professeur-card');
            
            professeurCards.forEach(card => {
                if (selectedMatiereId === 'all') {
                    card.style.display = 'block';
                    card.style.animation = 'fadeIn 0.3s ease-out';
                } else {
                    const cardMatiere = card.getAttribute('data-matiere');
                    if (cardMatiere === selectedMatiereId) {
                        card.style.display = 'block';
                        card.style.animation = 'fadeIn 0.3s ease-out';
                    } else {
                        card.style.display = 'none';
                    }
                }
            });
            
            // Mettre à jour le compteur affiché
            updateFilteredCount(selectedMatiereId, professeurCards);
        });
    }
}

/**
 * Mettre à jour le compteur de professeurs filtrés
 */
function updateFilteredCount(selectedMatiereId, professeurCards) {
    let visibleCount = 0;
    
    professeurCards.forEach(card => {
        if (card.style.display !== 'none') {
            visibleCount++;
        }
    });
    
    // Mettre à jour l'option sélectionnée avec le nouveau compteur
    const matiereSelect = document.getElementById('matiere-select');
    if (matiereSelect) {
        const selectedOption = matiereSelect.options[matiereSelect.selectedIndex];
        if (selectedMatiereId === 'all') {
            selectedOption.text = `Toutes les matières (${visibleCount})`;
        } else {
            const matiereName = selectedOption.text.split(' (')[0];
            selectedOption.text = `${matiereName} (${visibleCount})`;
        }
    }
}

/**
 * Charger les professeurs via AJAX (pour l'onglet professeurs)
 */
function loadProfesseurs() {
    // Les professeurs sont maintenant chargés directement dans le template
    // Cette fonction peut être utilisée pour des mises à jour dynamiques
    console.log('Professeurs chargés depuis le template');
    updateTabCounts();
}

/**
 * Filtrer le personnel par type
 */
function filterPersonnelByType(type) {
    const allCards = document.querySelectorAll('.personnel-card');
    
    allCards.forEach(card => {
        const cardType = card.getAttribute('data-type');
        if (cardType === type) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * Rechercher dans le personnel
 */
function searchPersonnel(query) {
    const allCards = document.querySelectorAll('.personnel-card');
    const searchTerm = query.toLowerCase();
    
    allCards.forEach(card => {
        const name = card.querySelector('.personnel-name').textContent.toLowerCase();
        const role = card.querySelector('.personnel-role').textContent.toLowerCase();
        const email = card.querySelector('.detail-value')?.textContent.toLowerCase() || '';
        
        if (name.includes(searchTerm) || role.includes(searchTerm) || email.includes(searchTerm)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}
