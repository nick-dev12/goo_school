/**
 * Gestion des Matières - JavaScript
 * Fonctionnalités pour la page de gestion des matières
 */

// Toggle du formulaire d'ajout - Fonction globale
window.toggleAddForm = function() {
    const formContainer = document.getElementById('addFormContainer');
    if (formContainer) {
        const isVisible = formContainer.style.display !== 'none';
        formContainer.style.display = isVisible ? 'none' : 'block';
        
        if (!isVisible) {
            // Focus sur le premier champ
            const firstInput = formContainer.querySelector('input[type="text"]');
            if (firstInput) {
                setTimeout(() => firstInput.focus(), 100);
            }
        }
    }
};

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de gestion des matières chargée');
    
    // Filtres par type de matière
    const filterBtns = document.querySelectorAll('.filter-btn');
    if (filterBtns.length > 0) {
        filterBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                // Retirer la classe active de tous les boutons
                filterBtns.forEach(b => b.classList.remove('active'));
                // Ajouter la classe active au bouton cliqué
                this.classList.add('active');
                
                const filter = this.getAttribute('data-filter');
                const allCards = document.querySelectorAll('.matiere-card');
                
                allCards.forEach(card => {
                    if (filter === 'all') {
                        card.style.display = 'block';
                    } else {
                        const cardType = card.getAttribute('data-type');
                        if (cardType === filter) {
                            card.style.display = 'block';
                        } else {
                            card.style.display = 'none';
                        }
                    }
                });
            });
        });
    }
    
    // Recherche en temps réel
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const searchCards = document.querySelectorAll('.matiere-card');
            
            searchCards.forEach(card => {
                const matiereName = card.getAttribute('data-matiere') || '';
                if (matiereName.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }
    
    // Animation d'apparition des cartes
    const animatedCards = document.querySelectorAll('.matiere-card');
    animatedCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
    
    // Effet de survol sur les cartes de matières
    const hoverCards = document.querySelectorAll('.matiere-card');
    hoverCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
        });
    });
    
    // Gestion des boutons d'action
    const actionBtns = document.querySelectorAll('.action-btn');
    actionBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const action = this.classList.contains('btn-edit') ? 'modifier' : 
                          this.classList.contains('btn-delete') ? 'supprimer' : 'voir';
            
            if (action === 'supprimer') {
                if (confirm('Êtes-vous sûr de vouloir supprimer cette matière ?')) {
                    // Logique de suppression ici
                    console.log('Suppression de la matière');
                }
            } else if (action === 'modifier') {
                // Logique de modification ici
                console.log('Modification de la matière');
            } else {
                // Redirection vers la page de détail
                const href = this.getAttribute('href');
                if (href) {
                    window.location.href = href;
                }
            }
        });
    });
    
    // Validation du formulaire d'ajout
    const addForm = document.getElementById('ajouterMatiereForm');
    if (addForm) {
        addForm.addEventListener('submit', function(e) {
            const nom = document.getElementById('nom').value.trim();
            const type = document.getElementById('type_matiere').value;
            const niveau = document.getElementById('niveau').value;
            
            if (!nom) {
                e.preventDefault();
                alert('Le nom de la matière est obligatoire');
                document.getElementById('nom').focus();
                return false;
            }
            
            if (!type) {
                e.preventDefault();
                alert('Le type de matière est obligatoire');
                document.getElementById('type_matiere').focus();
                return false;
            }
            
            if (!niveau) {
                e.preventDefault();
                alert('Le niveau d\'enseignement est obligatoire');
                document.getElementById('niveau').focus();
                return false;
            }
        });
    }
    
    // Gestion des checkboxes de classes
    const classCheckboxes = document.querySelectorAll('.class-checkbox input[type="checkbox"]');
    classCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const label = this.closest('.class-checkbox');
            if (this.checked) {
                label.style.backgroundColor = 'var(--primary-color)';
                label.style.color = 'white';
            } else {
                label.style.backgroundColor = 'var(--gray-100)';
                label.style.color = 'var(--gray-700)';
            }
        });
    });
    
    // Message de confirmation pour les actions
    function showMessage(message, type = 'info') {
        const messageEl = document.createElement('div');
        messageEl.className = `alert alert-${type}`;
        messageEl.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}"></i>
            <span>${message}</span>
        `;
        
        document.body.appendChild(messageEl);
        
        setTimeout(() => {
            messageEl.style.opacity = '0';
            messageEl.style.transform = 'translateY(-10px)';
            setTimeout(() => {
                messageEl.remove();
            }, 300);
        }, 3000);
    }
    
    // Exposer la fonction globalement
    window.showMessage = showMessage;
});

/**
 * Fonction globale pour confirmer la suppression d'une matière
 */
window.confirmDelete = function(matiereId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer cette matière ? Cette action est irréversible.')) {
        // Rediriger vers l'URL de suppression
        window.location.href = `/matieres/${matiereId}/supprimer/`;
    }
};