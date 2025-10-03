/**
 * Script pour la liste des établissements - Interface commerciale
 * Gestion des interactions, recherche et filtres
 */

class ListeEtablissements {
    constructor() {
        this.searchForm = document.querySelector('.search-form');
        this.searchInput = document.querySelector('.search-input');
        this.filterSelects = document.querySelectorAll('.filter-select');
        this.etablissementCards = document.querySelectorAll('.etablissement-card');
        this.actionBtns = document.querySelectorAll('.action-btn');

        this.init();
    }

    init() {
        this.bindEvents();
        this.initSearch();
        this.initFilters();
        this.initActions();
    }

    bindEvents() {
        // Recherche en temps réel
        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => {
                this.debounceSearch(e.target.value);
            });
        }

        // Filtres automatiques
        this.filterSelects.forEach(select => {
            select.addEventListener('change', () => {
                this.autoSubmitForm();
            });
        });

        // Soumission du formulaire
        if (this.searchForm) {
            this.searchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.submitForm();
            });
        }
    }

    initSearch() {
        // Animation de la barre de recherche
        if (this.searchInput) {
            this.searchInput.addEventListener('focus', () => {
                this.searchInput.parentElement.style.transform = 'scale(1.02)';
                this.searchInput.parentElement.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)';
            });

            this.searchInput.addEventListener('blur', () => {
                this.searchInput.parentElement.style.transform = 'scale(1)';
                this.searchInput.parentElement.style.boxShadow = '0 1px 3px 0 rgba(0, 0, 0, 0.1)';
            });
        }
    }

    initFilters() {
        // Animation des filtres
        this.filterSelects.forEach(select => {
            select.addEventListener('focus', () => {
                select.style.transform = 'scale(1.02)';
                select.style.borderColor = 'var(--primary)';
            });

            select.addEventListener('blur', () => {
                select.style.transform = 'scale(1)';
                select.style.borderColor = 'var(--border-light)';
            });
        });
    }

    initActions() {
        // Actions sur les cartes d'établissements
        this.actionBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const icon = btn.querySelector('i');
                if (icon.classList.contains('fa-eye')) {
                    // Le bouton "Voir les détails" est un lien, on laisse le comportement par défaut
                    return;
                } else {
                    e.preventDefault();
                    const action = icon.classList.contains('fa-edit') ? 'edit' : 'delete';
                    this.handleAction(action, btn);
                }
            });
        });

        // Animation des cartes au survol
        this.etablissementCards.forEach(card => {
            card.addEventListener('mouseenter', () => {
                card.style.transform = 'translateY(-8px)';
                card.style.boxShadow = 'var(--shadow-xl)';
            });

            card.addEventListener('mouseleave', () => {
                card.style.transform = 'translateY(0)';
                card.style.boxShadow = 'var(--shadow)';
            });
        });
    }

    debounceSearch(query) {
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.performSearch(query);
        }, 300);
    }

    performSearch(query) {
        // Mise en surbrillance des résultats de recherche
        this.etablissementCards.forEach(card => {
            const nom = card.querySelector('.etablissement-nom');
            const location = card.querySelector('.etablissement-location');

            if (query.length > 2) {
                this.highlightText(nom, query);
                this.highlightText(location, query);
            } else {
                this.removeHighlight(nom);
                this.removeHighlight(location);
            }
        });
    }

    highlightText(element, query) {
        if (!element || !query) return;

        const text = element.textContent;
        const regex = new RegExp(`(${query})`, 'gi');
        const highlightedText = text.replace(regex, '<mark class="search-highlight">$1</mark>');
        element.innerHTML = highlightedText;
    }

    removeHighlight(element) {
        if (!element) return;

        const text = element.textContent;
        element.innerHTML = text;
    }

    autoSubmitForm() {
        // Soumission automatique du formulaire après changement de filtre
        if (this.searchForm) {
            this.showLoadingState();
            setTimeout(() => {
                this.searchForm.submit();
            }, 100);
        }
    }

    submitForm() {
        this.showLoadingState();
        this.searchForm.submit();
    }

    showLoadingState() {
        // Afficher un état de chargement
        const submitBtn = this.searchForm.querySelector('button[type="submit"]');
        if (submitBtn) {
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Recherche...';
            submitBtn.disabled = true;

            // Restaurer après 2 secondes
            setTimeout(() => {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }, 2000);
        }
    }

    handleAction(action, button) {
        const card = button.closest('.etablissement-card');
        const etablissementNom = card.querySelector('.etablissement-nom').textContent;

        if (action === 'edit') {
            this.showEditModal(etablissementNom);
        } else if (action === 'delete') {
            this.showDeleteConfirm(etablissementNom, card);
        }
    }

    showEditModal(etablissementNom) {
        // Créer un modal de modification (à implémenter selon vos besoins)
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Modifier l'établissement</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <p>Modification de : <strong>${etablissementNom}</strong></p>
                    <p class="text-muted">Cette fonctionnalité sera implémentée prochainement.</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary modal-close">Fermer</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.bindModalEvents(modal);
    }

    showDeleteConfirm(etablissementNom, card) {
        // Créer une confirmation de suppression
        const confirmModal = document.createElement('div');
        confirmModal.className = 'modal-overlay';
        confirmModal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Confirmer la suppression</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <p>Êtes-vous sûr de vouloir supprimer l'établissement :</p>
                    <p><strong>${etablissementNom}</strong></p>
                    <p class="text-warning">Cette action est irréversible.</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary modal-close">Annuler</button>
                    <button class="btn btn-danger confirm-delete">Supprimer</button>
                </div>
            </div>
        `;

        document.body.appendChild(confirmModal);
        this.bindModalEvents(confirmModal);

        // Gérer la confirmation de suppression
        const confirmBtn = confirmModal.querySelector('.confirm-delete');
        confirmBtn.addEventListener('click', () => {
            this.deleteEtablissement(card);
            confirmModal.remove();
        });
    }

    deleteEtablissement(card) {
        // Animation de suppression
        card.style.transition = 'all 0.3s ease';
        card.style.transform = 'scale(0.8)';
        card.style.opacity = '0';

        setTimeout(() => {
            card.remove();
            this.showNotification('Établissement supprimé avec succès', 'success');
        }, 300);
    }

    bindModalEvents(modal) {
        const closeBtns = modal.querySelectorAll('.modal-close');
        closeBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                modal.remove();
            });
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}"></i>
                <span>${message}</span>
            </div>
            <button class="notification-close">&times;</button>
        `;

        // Styles pour la notification
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? 'var(--success)' : 'var(--info)'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: var(--radius);
            box-shadow: var(--shadow-lg);
            z-index: 10000;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            min-width: 300px;
            animation: slideInRight 0.3s ease;
        `;

        document.body.appendChild(notification);

        // Auto-suppression après 5 secondes
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.animation = 'slideOutRight 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }
        }, 5000);

        // Fermeture manuelle
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        });
    }
}

// Styles CSS pour les modals et notifications
const additionalStyles = `
<style>
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    animation: fadeIn 0.3s ease;
}

.modal-content {
    background: white;
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xl);
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    animation: slideInUp 0.3s ease;
}

.modal-header {
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-light);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-header h3 {
    margin: 0;
    color: var(--text-primary);
}

.modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-light);
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius);
    transition: all 0.3s ease;
}

.modal-close:hover {
    background: var(--bg-secondary);
    color: var(--text-primary);
}

.modal-body {
    padding: 1.5rem;
}

.modal-footer {
    padding: 1.5rem;
    border-top: 1px solid var(--border-light);
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
}

.search-highlight {
    background: var(--accent);
    color: white;
    padding: 0.1rem 0.2rem;
    border-radius: 0.2rem;
    font-weight: 600;
}

.text-muted {
    color: var(--text-light);
}

.text-warning {
    color: var(--warning);
}

.btn-danger {
    background: var(--error);
    color: white;
}

.btn-danger:hover {
    background: #dc2626;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

@keyframes slideInUp {
    from {
        transform: translateY(50px);
        opacity: 0;
    }
    to {
        transform: translateY(0);
        opacity: 1;
    }
}

@keyframes slideInRight {
    from {
        transform: translateX(100%);
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
        transform: translateX(100%);
        opacity: 0;
    }
}
</style>
`;

// Ajouter les styles au document
document.head.insertAdjacentHTML('beforeend', additionalStyles);

// Initialisation quand le DOM est chargé
document.addEventListener('DOMContentLoaded', () => {
    new ListeEtablissements();
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
