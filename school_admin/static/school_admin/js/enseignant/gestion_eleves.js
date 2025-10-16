// Gestion des Élèves - Filtrage

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page gestion élèves chargée');
    
    const classeFilter = document.getElementById('classe-filter');
    const elevesGrid = document.getElementById('elevesGrid');
    
    if (classeFilter && elevesGrid) {
        classeFilter.addEventListener('change', function() {
            const selectedClasse = this.value;
            const eleveCards = elevesGrid.querySelectorAll('.eleve-card');
            
            eleveCards.forEach(card => {
                if (selectedClasse === 'all' || card.dataset.classe === selectedClasse) {
                    card.style.display = 'block';
                    setTimeout(() => {
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, 10);
                } else {
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(20px)';
                    setTimeout(() => {
                        card.style.display = 'none';
                    }, 300);
                }
            });
        });
    }
});

