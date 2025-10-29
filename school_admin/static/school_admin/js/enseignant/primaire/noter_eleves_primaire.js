/**
 * JavaScript pour la page de notation primaire multi-matières
 */

// Switch entre les onglets de matières
function switchMatiereTab(matiereId) {
    console.log('Switch vers matière:', matiereId);
    
    // Désactiver tous les onglets
    document.querySelectorAll('.matiere-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Masquer tous les contenus
    document.querySelectorAll('.matiere-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    // Activer l'onglet sélectionné
    const selectedBtn = document.querySelector(`[data-tab="${matiereId}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active');
    }
    
    // Afficher le contenu sélectionné
    const selectedContent = document.getElementById(matiereId);
    if (selectedContent) {
        selectedContent.classList.add('active');
    }
}

// Calculer les moyennes pour une matière spécifique
function calculerMoyennes(matiereId) {
    console.log('Calcul des moyennes pour matière:', matiereId);
    
    const table = document.querySelector(`#table-${matiereId}`);
    if (!table) {
        console.error('Table non trouvée pour matière:', matiereId);
        return;
    }
    
    const rows = table.querySelectorAll('tbody tr');
    
    rows.forEach(row => {
        const eleveId = row.getAttribute('data-eleve-id');
        const inputs = row.querySelectorAll('.note-input[data-eval-id]');
        
        let total = 0;
        let count = 0;
        
        inputs.forEach(input => {
            const value = parseFloat(input.value);
            const bareme = parseFloat(input.getAttribute('data-bareme'));
            
            if (!isNaN(value) && !isNaN(bareme) && bareme > 0) {
                // Convertir en note sur 20
                const noteSur20 = (value / bareme) * 20;
                total += noteSur20;
                count++;
            }
        });
        
        if (count > 0) {
            const moyenne = total / count;
            const moyenneInput = row.querySelector(`#moyenne_${matiereId}_${eleveId}`);
            
            if (moyenneInput) {
                moyenneInput.value = moyenne.toFixed(2);
                
                // Appliquer la couleur
                moyenneInput.classList.remove('excellent', 'tres-bien', 'bien', 'passable', 'fragile', 'insuffisant');
                if (moyenne >= 16) {
                    moyenneInput.classList.add('excellent');
                } else if (moyenne >= 14) {
                    moyenneInput.classList.add('tres-bien');
                } else if (moyenne >= 12) {
                    moyenneInput.classList.add('bien');
                } else if (moyenne >= 10) {
                    moyenneInput.classList.add('passable');
                } else if (moyenne >= 8) {
                    moyenneInput.classList.add('fragile');
                } else {
                    moyenneInput.classList.add('insuffisant');
                }
            }
        } else {
            const moyenneInput = row.querySelector(`#moyenne_${matiereId}_${eleveId}`);
            if (moyenneInput) {
                moyenneInput.value = '--';
                moyenneInput.classList.remove('excellent', 'tres-bien', 'bien', 'passable', 'fragile', 'insuffisant');
            }
        }
    });
    
    console.log('Moyennes calculées pour', count, 'élèves');
}

// Colorier une note selon sa valeur
function colorNote(input) {
    const value = parseFloat(input.value);
    const bareme = parseFloat(input.getAttribute('data-bareme'));
    
    if (!isNaN(value) && !isNaN(bareme) && bareme > 0) {
        const noteSur20 = (value / bareme) * 20;
        
        input.classList.remove('excellent', 'tres-bien', 'bien', 'passable', 'fragile', 'insuffisant');
        
        if (noteSur20 >= 16) {
            input.classList.add('excellent');
        } else if (noteSur20 >= 14) {
            input.classList.add('tres-bien');
        } else if (noteSur20 >= 12) {
            input.classList.add('bien');
        } else if (noteSur20 >= 10) {
            input.classList.add('passable');
        } else if (noteSur20 >= 8) {
            input.classList.add('fragile');
        } else {
            input.classList.add('insuffisant');
        }
        
        input.classList.add('saved');
    } else {
        input.classList.remove('excellent', 'tres-bien', 'bien', 'passable', 'fragile', 'insuffisant', 'saved');
    }
}

// Compter les évaluations sélectionnées par matière
function updateSelectedCount(matiereId) {
    const checkboxes = document.querySelectorAll(`.eval-checkbox[data-matiere="${matiereId}"]`);
    const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
    
    const counter = document.querySelector(`#selectedCount-${matiereId}`);
    if (counter) {
        counter.textContent = checkedCount;
    }
}

// Synchroniser les dropdowns de mode de calcul
function syncModeCalculDropdowns() {
    const topSelect = document.getElementById('mode_calcul');
    const bottomSelect = document.getElementById('mode_calcul_bottom');
    
    if (topSelect && bottomSelect) {
        topSelect.addEventListener('change', function() {
            bottomSelect.value = this.value;
        });
        
        bottomSelect.addEventListener('change', function() {
            topSelect.value = this.value;
        });
    }
}

// Initialisation au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initialisation de la page de notation primaire');
    
    // Synchroniser les dropdowns de mode de calcul
    syncModeCalculDropdowns();
    
    // Ajouter les événements sur les checkboxes
    document.querySelectorAll('.eval-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const matiereId = this.getAttribute('data-matiere');
            updateSelectedCount(matiereId);
        });
    });
    
    // Activer le premier onglet par défaut
    const firstTab = document.querySelector('.matiere-tab-btn');
    if (firstTab) {
        const firstMatiereId = firstTab.getAttribute('data-tab');
        switchMatiereTab(firstMatiereId);
    }
    
    // Mettre à jour les compteurs initiaux
    document.querySelectorAll('.matiere-tab-btn').forEach(btn => {
        const matiereId = btn.getAttribute('data-tab');
        updateSelectedCount(matiereId);
    });
});

