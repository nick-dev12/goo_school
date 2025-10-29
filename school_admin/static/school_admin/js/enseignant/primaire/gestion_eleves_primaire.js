/**
 * JavaScript pour la page de Gestion des Élèves Primaire
 * Copie exacte du système standard avec adaptations primaire
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page gestion élèves primaire chargée');
    
    // Activer le premier onglet et la première classe par défaut
    const firstTab = document.querySelector('.tab-btn.active');
    if (firstTab) {
        const firstTabId = firstTab.getAttribute('data-tab');
        const firstTabPanel = document.getElementById(firstTabId);
        
        if (firstTabPanel) {
            const firstClasseBtn = firstTabPanel.querySelector('.classe-tab-btn');
            if (firstClasseBtn && firstClasseBtn.classList.contains('active')) {
                const firstClasseId = firstClasseBtn.getAttribute('data-classe');
                // Assurer que le contenu est affiché
                const firstClasseContent = document.getElementById(firstClasseId);
                if (firstClasseContent && !firstClasseContent.classList.contains('active')) {
                    firstClasseContent.classList.add('active');
                }
            }
        }
    }
});

/**
 * Changer d'onglet principal (catégorie)
 */
function switchTab(tabId) {
    console.log('Switch vers onglet:', tabId);
    
    // Désactiver tous les onglets principaux
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.tab-content-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    
    // Activer l'onglet sélectionné
    const selectedBtn = document.querySelector(`[data-tab="${tabId}"]`);
    const selectedPanel = document.getElementById(tabId);
    
    if (selectedBtn && selectedPanel) {
        selectedBtn.classList.add('active');
        selectedPanel.classList.add('active');
    }
}

/**
 * Afficher une classe spécifique
 */
function showClasse(classeId, tabId) {
    console.log('Show classe:', classeId, 'in tab:', tabId);
    
    // Désactiver tous les boutons de classe dans cet onglet
    const tabPanel = document.getElementById(tabId);
    if (tabPanel) {
        tabPanel.querySelectorAll('.classe-tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        tabPanel.querySelectorAll('.classe-content').forEach(content => {
            content.classList.remove('active');
        });
        
        // Activer la classe sélectionnée
        const selectedBtn = tabPanel.querySelector(`[data-classe="${classeId}"]`);
        const selectedContent = document.getElementById(classeId);
        
        if (selectedBtn && selectedContent) {
            selectedBtn.classList.add('active');
            selectedContent.classList.add('active');
        }
    }
}

/**
 * Ouvrir le modal de sanction
 */
function ouvrirModalSanction(eleveId, eleveNom, classeId) {
    console.log('Ouverture modal sanction - Élève:', eleveId, eleveNom, 'Classe:', classeId);
    
    document.getElementById('sanction-eleve-id').value = eleveId;
    document.getElementById('sanction-classe-id').value = classeId;
    document.getElementById('sanction-eleve-nom').textContent = eleveNom;
    
    const modal = document.getElementById('modal-sanction');
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Fermer le modal de sanction
 */
function fermerModalSanction() {
    const modal = document.getElementById('modal-sanction');
    modal.classList.remove('active');
    document.body.style.overflow = 'auto';
    
    // Réinitialiser le formulaire
    document.getElementById('form-sanction').reset();
}

/**
 * Fermer le modal si clic en dehors
 */
document.addEventListener('click', function(e) {
    const modal = document.getElementById('modal-sanction');
    if (modal && e.target === modal) {
        fermerModalSanction();
    }
});

/**
 * Fermer le modal avec la touche Escape
 */
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('modal-sanction');
        if (modal && modal.classList.contains('active')) {
            fermerModalSanction();
        }
    }
});

/**
 * Animation au survol des cartes d'élèves
 */
document.querySelectorAll('.presence-row').forEach(row => {
    row.addEventListener('mouseenter', function() {
        this.style.transition = 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
    });
});

