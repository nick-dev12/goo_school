// Gestion des Notes - Tabs et Actions

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page gestion notes chargée');
    
    // Gestion des onglets de classes
    const tabBtns = document.querySelectorAll('.tab-btn');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // Retirer la classe active de tous les boutons
            tabBtns.forEach(b => b.classList.remove('active'));
            
            // Ajouter la classe active au bouton cliqué
            this.classList.add('active');
            
            const classeId = this.dataset.classe;
            console.log('Classe sélectionnée:', classeId);
            
            // Ici, vous pouvez ajouter la logique pour filtrer les évaluations par classe
        });
    });
    
    // Animation des quick action cards
    const quickActionCards = document.querySelectorAll('.quick-action-card');
    
    quickActionCards.forEach(card => {
        card.addEventListener('click', function() {
            const actionType = this.querySelector('h3').textContent;
            console.log('Action rapide:', actionType);
            
            // Ajouter ici la logique pour chaque action
        });
    });
});

