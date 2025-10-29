/**
 * JavaScript pour la page de Gestion des Notes Primaire
 * Système à 3 niveaux : Classes -> Matières -> Relevé de notes
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Initialisation de la page de gestion des notes primaire');
    
    // Activer le premier onglet par défaut si aucun n'est actif
    const firstTab = document.querySelector('.tab-btn');
    if (firstTab && !document.querySelector('.tab-btn.active')) {
        const firstTabId = firstTab.getAttribute('onclick').match(/'([^']+)'/)[1];
        switchTab(firstTabId);
    }
});

/**
 * Changer d'onglet de catégorie de classe
 */
function switchTab(tabId) {
    console.log('Switch vers onglet:', tabId);
    
    // Désactiver tous les boutons d'onglets
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Masquer tous les contenus d'onglets
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    // Activer le bouton cliqué
    const clickedBtn = Array.from(document.querySelectorAll('.tab-btn')).find(btn => {
        const onclick = btn.getAttribute('onclick');
        return onclick && onclick.includes(tabId);
    });
    
    if (clickedBtn) {
        clickedBtn.classList.add('active');
    }
    
    // Afficher le contenu correspondant
    const targetContent = document.getElementById(tabId);
    if (targetContent) {
        targetContent.classList.add('active');
    }
}

/**
 * Animer le survol des cartes
 */
document.querySelectorAll('.classe-card, .matiere-card').forEach(card => {
    card.addEventListener('mouseenter', function() {
        this.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
    });
});

/**
 * Gestion des messages d'alerte (auto-fermeture après 5 secondes)
 */
const alerts = document.querySelectorAll('.alert');
if (alerts.length > 0) {
    setTimeout(() => {
        alerts.forEach(alert => {
            alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-20px)';
            
            setTimeout(() => {
                alert.remove();
            }, 500);
        });
    }, 5000);
}

