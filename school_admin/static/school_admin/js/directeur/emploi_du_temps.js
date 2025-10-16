// school_admin/static/school_admin/js/directeur/emploi_du_temps.js
// JavaScript pour la gestion des emplois du temps

document.addEventListener('DOMContentLoaded', function() {
    // Initialisation
    initTabs();
    initScrollButtons();
    initAnimations();
});

/**
 * Initialise le système d'onglets
 */
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const category = this.getAttribute('data-category');
            switchTab(category);
        });
    });
}

/**
 * Change d'onglet
 * @param {string} category - La catégorie à afficher
 */
function switchTab(category) {
    // Désactiver tous les onglets
    const allTabs = document.querySelectorAll('.tab-btn');
    const allPanels = document.querySelectorAll('.tab-panel');
    
    allTabs.forEach(tab => tab.classList.remove('active'));
    allPanels.forEach(panel => panel.classList.remove('active'));
    
    // Activer l'onglet sélectionné
    const activeTab = document.querySelector(`.tab-btn[data-category="${category}"]`);
    const activePanel = document.getElementById(`panel-${slugify(category)}`);
    
    if (activeTab) {
        activeTab.classList.add('active');
        
        // Faire défiler l'onglet dans la vue si nécessaire
        activeTab.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'nearest',
            inline: 'center'
        });
    }
    
    if (activePanel) {
        activePanel.classList.add('active');
    }
}

/**
 * Initialise les boutons de défilement des onglets
 */
function initScrollButtons() {
    const scrollLeft = document.getElementById('scrollLeft');
    const scrollRight = document.getElementById('scrollRight');
    const tabsContainer = document.querySelector('.tabs-nav-container');
    
    if (!tabsContainer) return;
    
    // Défilement vers la gauche
    if (scrollLeft) {
        scrollLeft.addEventListener('click', function() {
            tabsContainer.scrollBy({
                left: -200,
                behavior: 'smooth'
            });
        });
    }
    
    // Défilement vers la droite
    if (scrollRight) {
        scrollRight.addEventListener('click', function() {
            tabsContainer.scrollBy({
                left: 200,
                behavior: 'smooth'
            });
        });
    }
    
    // Masquer/afficher les boutons de défilement selon le besoin
    updateScrollButtons();
    tabsContainer.addEventListener('scroll', updateScrollButtons);
    window.addEventListener('resize', updateScrollButtons);
}

/**
 * Met à jour la visibilité des boutons de défilement
 */
function updateScrollButtons() {
    const tabsContainer = document.querySelector('.tabs-nav-container');
    const scrollLeft = document.getElementById('scrollLeft');
    const scrollRight = document.getElementById('scrollRight');
    
    if (!tabsContainer || !scrollLeft || !scrollRight) return;
    
    const isScrollable = tabsContainer.scrollWidth > tabsContainer.clientWidth;
    const isAtStart = tabsContainer.scrollLeft === 0;
    const isAtEnd = tabsContainer.scrollLeft + tabsContainer.clientWidth >= tabsContainer.scrollWidth - 1;
    
    if (!isScrollable) {
        scrollLeft.style.display = 'none';
        scrollRight.style.display = 'none';
    } else {
        scrollLeft.style.display = isAtStart ? 'none' : 'flex';
        scrollRight.style.display = isAtEnd ? 'none' : 'flex';
    }
}

/**
 * Initialise les animations au scroll
 */
function initAnimations() {
    // Observer pour les animations d'apparition
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }
            });
        },
        {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        }
    );
    
    // Observer les cartes de classe
    const classeCards = document.querySelectorAll('.classe-card');
    classeCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = `all 0.5s ease ${index * 0.1}s`;
        observer.observe(card);
    });
}

/**
 * Convertit une chaîne en slug
 * @param {string} text - Le texte à convertir
 * @returns {string} Le slug
 */
function slugify(text) {
    return text
        .toString()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');
}

/**
 * Anime un élément avec un effet de pulsation
 * @param {HTMLElement} element - L'élément à animer
 */
function pulseAnimation(element) {
    element.style.animation = 'pulse 0.5s ease-in-out';
    setTimeout(() => {
        element.style.animation = '';
    }, 500);
}

/**
 * Affiche une notification toast
 * @param {string} message - Le message à afficher
 * @param {string} type - Le type de notification (success, error, warning, info)
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas fa-${getIconForType(type)}"></i>
        <span>${message}</span>
    `;
    
    document.body.appendChild(toast);
    
    // Animation d'entrée
    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    }, 10);
    
    // Animation de sortie
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 3000);
}

/**
 * Retourne l'icône FontAwesome appropriée pour un type de notification
 * @param {string} type - Le type de notification
 * @returns {string} Le nom de l'icône
 */
function getIconForType(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-triangle',
        warning: 'exclamation-circle',
        info: 'info-circle'
    };
    return icons[type] || 'info-circle';
}

/**
 * Fonction de recherche dans les classes
 * @param {string} query - La requête de recherche
 */
function searchClasses(query) {
    const normalizedQuery = query.toLowerCase().trim();
    const classeCards = document.querySelectorAll('.classe-card');
    
    classeCards.forEach(card => {
        const className = card.querySelector('.classe-nom').textContent.toLowerCase();
        const classLevel = card.querySelector('.classe-niveau').textContent.toLowerCase();
        
        if (className.includes(normalizedQuery) || classLevel.includes(normalizedQuery)) {
            card.style.display = '';
            card.style.animation = 'fadeIn 0.3s ease-out';
        } else {
            card.style.display = 'none';
        }
    });
    
    // Vérifier si des résultats sont affichés dans chaque panel
    const panels = document.querySelectorAll('.tab-panel');
    panels.forEach(panel => {
        const visibleCards = panel.querySelectorAll('.classe-card:not([style*="display: none"])');
        const emptyMessage = panel.querySelector('.no-results-message');
        
        if (visibleCards.length === 0) {
            if (!emptyMessage) {
                const message = document.createElement('div');
                message.className = 'no-results-message empty-state';
                message.innerHTML = `
                    <div class="empty-state-icon">
                        <i class="fas fa-search"></i>
                    </div>
                    <h3 class="empty-state-title">Aucun résultat</h3>
                    <p class="empty-state-text">
                        Aucune classe ne correspond à votre recherche dans cette catégorie.
                    </p>
                `;
                panel.querySelector('.classes-grid').style.display = 'none';
                panel.appendChild(message);
            }
        } else {
            if (emptyMessage) {
                emptyMessage.remove();
                panel.querySelector('.classes-grid').style.display = '';
            }
        }
    });
}

/**
 * Filtre les classes par statut d'emploi du temps
 * @param {string} filter - Le filtre à appliquer ('all', 'with-edt', 'without-edt')
 */
function filterByStatus(filter) {
    const classeCards = document.querySelectorAll('.classe-card');
    
    classeCards.forEach(card => {
        const hasEdt = !card.classList.contains('classe-card-no-edt');
        
        switch(filter) {
            case 'with-edt':
                card.style.display = hasEdt ? '' : 'none';
                break;
            case 'without-edt':
                card.style.display = !hasEdt ? '' : 'none';
                break;
            default: // 'all'
                card.style.display = '';
        }
    });
}

/**
 * Gère le défilement fluide vers le haut de la page
 */
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

// Ajouter un bouton de retour en haut si la page est longue
window.addEventListener('scroll', function() {
    const scrollButton = document.getElementById('scrollTopBtn');
    
    if (window.pageYOffset > 300) {
        if (!scrollButton) {
            const button = document.createElement('button');
            button.id = 'scrollTopBtn';
            button.className = 'scroll-top-btn';
            button.innerHTML = '<i class="fas fa-arrow-up"></i>';
            button.onclick = scrollToTop;
            document.body.appendChild(button);
            
            // Animation d'entrée
            setTimeout(() => {
                button.style.opacity = '1';
                button.style.transform = 'scale(1)';
            }, 10);
        }
    } else {
        if (scrollButton) {
            scrollButton.style.opacity = '0';
            scrollButton.style.transform = 'scale(0)';
            setTimeout(() => {
                scrollButton.remove();
            }, 300);
        }
    }
});

// Exposer les fonctions globalement pour pouvoir les appeler depuis le HTML
window.switchTab = switchTab;
window.searchClasses = searchClasses;
window.filterByStatus = filterByStatus;
window.scrollToTop = scrollToTop;

