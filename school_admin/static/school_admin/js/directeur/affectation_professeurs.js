/**
 * JavaScript pour la page d'affectation des professeurs
 * Utilisé uniquement pour les animations et interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Page d\'affectation des professeurs chargée');
    
    // Initialiser les onglets de matière
    initializeMatiereTabs();
    
    // Initialiser les interactions des cartes
    initializeProfessorCards();
    
    // Supérieur : filière → matières visibles, puis classes
    initializeAffectationFiliereSuperieur();
    // Filtrer les classes selon la matière (filière + classes cibles matière/module)
    initializeAffectationClasseFilter();
});

/**
 * Supérieur : choix de la filière puis filtrage des options « Matière » (comme l’ajout de professeur).
 */
function initializeAffectationFiliereSuperieur() {
    document.querySelectorAll('.affectation-filiere-select').forEach(function (filSel) {
        var pid = filSel.getAttribute('data-professeur-id');
        var matSel = document.getElementById('matiere' + pid);
        if (!matSel) return;

        function syncFromFiliere() {
            var depId = filSel.value;
            matSel.querySelectorAll('option').forEach(function (opt) {
                if (!opt.value) {
                    opt.hidden = !!depId;
                    opt.disabled = !!depId;
                    return;
                }
                var mdep = opt.getAttribute('data-department-id') || '';
                var show = depId && mdep === depId;
                opt.hidden = !show;
                opt.disabled = !show;
                if (!show && opt.selected) {
                    opt.selected = false;
                }
            });
            if (!depId) {
                matSel.value = '';
                var ph = matSel.querySelector('option[value=""]');
                if (ph) {
                    ph.selected = true;
                }
            } else {
                var curOpt = matSel.options[matSel.selectedIndex];
                if (!curOpt || !curOpt.value || curOpt.disabled) {
                    var firstOk = Array.prototype.find.call(matSel.options, function (o) {
                        return o.value && !o.disabled;
                    });
                    if (firstOk) {
                        firstOk.selected = true;
                    } else {
                        matSel.value = '';
                    }
                }
            }
            filterClassesByMatiere(matSel);
        }

        filSel.addEventListener('change', syncFromFiliere);
    });
}

/**
 * Filtre les classes selon la filière de la matière et les classes cibles (matière / module).
 */
function initializeAffectationClasseFilter() {
    const matiereSelects = document.querySelectorAll('.affectation-matiere-select');
    matiereSelects.forEach(function (matiereSelect) {
        matiereSelect.addEventListener('change', function () {
            filterClassesByMatiere(this);
        });
        filterClassesByMatiere(matiereSelect);
    });
}

function filterClassesByMatiere(matiereSelect) {
    const professeurId = matiereSelect.getAttribute('data-professeur-id');
    const classeSelect = document.getElementById('classe' + professeurId);
    if (!classeSelect) return;

    const selectedOpt = matiereSelect.options[matiereSelect.selectedIndex];
    const classOptions = classeSelect.querySelectorAll('option');

    if (!selectedOpt || !selectedOpt.value) {
        classOptions.forEach(function (opt) {
            if (!opt.value) {
                opt.style.display = '';
                opt.disabled = false;
                return;
            }
            opt.style.display = 'none';
            opt.disabled = true;
            opt.selected = false;
        });
        return;
    }

    const matiereDepId = selectedOpt.getAttribute('data-department-id') || '';
    const matiereClasseIdsStr = selectedOpt.getAttribute('data-classe-ids') || '';
    const matiereClasseIds = matiereClasseIdsStr
        ? matiereClasseIdsStr.split(',').filter(function (id) {
              return id.trim();
          })
        : [];

    classOptions.forEach(function (opt) {
        if (!opt.value) {
            opt.style.display = '';
            opt.disabled = false;
            return;
        }
        const classeDepId = opt.getAttribute('data-department-id') || '';
        const classeId = opt.getAttribute('data-classe-id') || opt.value;

        let match = true;
        if (matiereDepId && classeDepId !== matiereDepId) {
            match = false;
        }
        if (matiereClasseIds.length > 0 && match) {
            match = matiereClasseIds.indexOf(classeId) >= 0;
        }

        opt.style.display = match ? '' : 'none';
        opt.disabled = !match;
        if (!match) opt.selected = false;
    });

    const currentClasseOpt = classeSelect.options[classeSelect.selectedIndex];
    if (currentClasseOpt && currentClasseOpt.disabled) {
        const firstVisible =
            classeSelect.querySelector('option[value=""]') ||
            classeSelect.querySelector('option:not([disabled])');
        if (firstVisible) classeSelect.value = firstVisible.value;
    }
}

/**
 * Initialiser les onglets de matière
 */
function initializeMatiereTabs() {
    const tabButtons = document.querySelectorAll('.matiere-tab-btn');
    const professorCards = document.querySelectorAll('.professor-card');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const matiereId = this.getAttribute('data-matiere');
            
            // Mettre à jour l'état actif des onglets
            tabButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Filtrer les cartes de professeurs
            professorCards.forEach(card => {
                const cardMatiere = card.getAttribute('data-matiere');
                
                if (matiereId === 'all' || cardMatiere === matiereId) {
                    card.style.display = 'block';
                    card.style.animation = 'fadeIn 0.3s ease-in-out';
                } else {
                    card.style.display = 'none';
                }
            });
            
            // Mettre à jour le compteur
            updateFilteredCount();
        });
    });
}

/**
 * Initialiser les interactions des cartes de professeurs
 */
function initializeProfessorCards() {
    // Ajouter des effets de survol
    const professorCards = document.querySelectorAll('.professor-card');
    professorCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 8px 25px rgba(0, 0, 0, 0.15)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 4px 15px rgba(0, 0, 0, 0.1)';
        });
    });
}

/**
 * Toggle l'affichage du panneau d'affectations
 */
function toggleAffectations(professeurId) {
    const panel = document.getElementById(`affectationsPanel${professeurId}`);
    const overlay = document.getElementById(`modalOverlay${professeurId}`);
    
    if (panel && overlay) {
        if (panel.style.display === 'none' || panel.style.display === '') {
            // Ouvrir le modal
            overlay.style.display = 'block';
            panel.style.display = 'flex';
            document.body.style.overflow = 'hidden'; // Empêcher le scroll de la page

            // Supérieur : réinitialiser filière / matière / filtre classes
            const fil = document.getElementById('filiere' + professeurId);
            if (fil) {
                fil.value = '';
                fil.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                const mat = document.getElementById('matiere' + professeurId);
                if (mat) {
                    filterClassesByMatiere(mat);
                }
            }

            // Animation d'entrée
            setTimeout(() => {
                panel.classList.add('modal-active');
            }, 10);
        } else {
            // Fermer le modal
            panel.classList.remove('modal-active');
            
            setTimeout(() => {
                overlay.style.display = 'none';
                panel.style.display = 'none';
                document.body.style.overflow = ''; // Restaurer le scroll
            }, 300);
        }
    }
}

/**
 * Mettre à jour le compteur de professeurs filtrés
 */
function updateFilteredCount() {
    const activeTab = document.querySelector('.matiere-tab-btn.active');
    const matiereId = activeTab ? activeTab.getAttribute('data-matiere') : 'all';
    
    let visibleCount = 0;
    const professorCards = document.querySelectorAll('.professor-card');
    
    professorCards.forEach(card => {
        if (card.style.display !== 'none') {
            visibleCount++;
        }
    });
    
    // Mettre à jour le compteur dans l'onglet actif
    const countElement = activeTab.querySelector('.tab-count');
    if (countElement) {
        countElement.textContent = visibleCount;
    }
}

/**
 * Afficher un message temporaire
 */
function showTemporaryMessage(message, type = 'info') {
    // Créer l'élément de message
    const messageDiv = document.createElement('div');
    messageDiv.className = `temporary-message message-${type}`;
    messageDiv.textContent = message;
    
    // Styles pour le message
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        animation: slideInRight 0.3s ease-out;
        max-width: 300px;
        word-wrap: break-word;
    `;
    
    // Couleurs selon le type
    if (type === 'success') {
        messageDiv.style.backgroundColor = '#10b981';
    } else if (type === 'error') {
        messageDiv.style.backgroundColor = '#ef4444';
    } else if (type === 'warning') {
        messageDiv.style.backgroundColor = '#f59e0b';
    } else {
        messageDiv.style.backgroundColor = '#3b82f6';
    }
    
    // Ajouter au DOM
    document.body.appendChild(messageDiv);
    
    // Supprimer après 3 secondes
    setTimeout(() => {
        messageDiv.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 300);
    }, 3000);
}

/**
 * Animation de fade in
 */
const fadeInKeyframes = `
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
`;

/**
 * Animation de slide down
 */
const slideDownKeyframes = `
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
`;

/**
 * Animation de slide up
 */
const slideUpKeyframes = `
@keyframes slideUp {
    from { opacity: 1; transform: translateY(0); }
    to { opacity: 0; transform: translateY(-10px); }
}
`;

/**
 * Animation de slide in right
 */
const slideInRightKeyframes = `
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(100%); }
    to { opacity: 1; transform: translateX(0); }
}
`;

/**
 * Animation de slide out right
 */
const slideOutRightKeyframes = `
@keyframes slideOutRight {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(100%); }
}
`;

// Ajouter les animations CSS au document
const style = document.createElement('style');
style.textContent = fadeInKeyframes + slideDownKeyframes + slideUpKeyframes + slideInRightKeyframes + slideOutRightKeyframes;
document.head.appendChild(style);