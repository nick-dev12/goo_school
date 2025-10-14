/**
 * Liste des Professeurs - JavaScript
 * Fonctionnalités pour la page de liste des professeurs
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page de liste des professeurs chargée');
    
    // Recherche en temps réel
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const professeurCards = document.querySelectorAll('.professeur-card');
            
            professeurCards.forEach(card => {
                const professeurName = card.querySelector('.professeur-nom').textContent.toLowerCase();
                const professeurMatiere = card.querySelector('.professeur-matiere').textContent.toLowerCase();
                const professeurEmail = card.querySelector('.detail-value').textContent.toLowerCase();
                
                if (professeurName.includes(searchTerm) || 
                    professeurMatiere.includes(searchTerm) || 
                    professeurEmail.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }
    
    // Filtres par matière
    const matiereTabBtns = document.querySelectorAll('.matiere-tab-btn');
    if (matiereTabBtns.length > 0) {
        matiereTabBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                // Retirer la classe active de tous les boutons
                matiereTabBtns.forEach(b => b.classList.remove('active'));
                // Ajouter la classe active au bouton cliqué
                this.classList.add('active');
                
                const matiereId = this.getAttribute('data-matiere');
                const professeurCards = document.querySelectorAll('.professeur-card');
                
                professeurCards.forEach(card => {
                    if (matiereId === 'all') {
                        card.style.display = 'block';
                    } else {
                        const cardMatiere = card.getAttribute('data-matiere');
                        if (cardMatiere === matiereId) {
                            card.style.display = 'block';
                        } else {
                            card.style.display = 'none';
                        }
                    }
                });
            });
        });
    }
    
    // Gestion des actions des cartes
    const editBtns = document.querySelectorAll('.btn-edit');
    const deleteBtns = document.querySelectorAll('.btn-delete');
    
    editBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // TODO: Implémenter la modification
            console.log('Modifier professeur');
        });
    });
    
    deleteBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            if (confirm('Êtes-vous sûr de vouloir supprimer ce professeur ?')) {
                // TODO: Implémenter la suppression
                console.log('Supprimer professeur');
            }
        });
    });
    
    // Animation des statistiques
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.6s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 150);
    });
    
    // Effet de survol sur les cartes de professeurs
    const professeurCards = document.querySelectorAll('.professeur-card');
    professeurCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-8px) scale(1.02)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
    
    // Animation d'apparition des cartes
    professeurCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});