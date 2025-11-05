/**
 * Script pour la page Notes & Évaluations
 * Gère uniquement les interactions (onglets, modals)
 */

document.addEventListener('DOMContentLoaded', function () {
    initTrimesterTabs();
    initSubjectCards();
});

/**
 * Initialisation des onglets de périodes
 */
function initTrimesterTabs() {
    const trimesterTabs = document.querySelectorAll('.trimester-tab');
    const trimesterSections = document.querySelectorAll('.trimester-section');

    // Créer l'indicateur de progression
    const tabsContainer = document.querySelector('.trimester-tabs-container');
    if (tabsContainer) {
        const progressContainer = document.createElement('div');
        progressContainer.className = 'trimester-progress';

        // Ajouter un point pour chaque onglet
        trimesterTabs.forEach((tab, index) => {
            const dot = document.createElement('div');
            dot.className = 'progress-dot';
            if (tab.classList.contains('active')) {
                dot.classList.add('active');
            }
            dot.setAttribute('data-index', index);
            progressContainer.appendChild(dot);
        });

        tabsContainer.appendChild(progressContainer);
    }

    // Gérer le clic sur les onglets de périodes
    trimesterTabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const trimester = this.getAttribute('data-trimester');

            // Désactiver tous les onglets et sections
            trimesterTabs.forEach(t => t.classList.remove('active'));
            trimesterSections.forEach(s => {
                s.classList.remove('active');
                s.style.animation = 'fadeOut 0.2s ease forwards';
            });

            // Activer l'onglet cliqué
            this.classList.add('active');

            // Mettre à jour les points de progression
            const dots = document.querySelectorAll('.progress-dot');
            const activeIndex = Array.from(trimesterTabs).indexOf(this);
            dots.forEach((dot, index) => {
                dot.classList.toggle('active', index === activeIndex);
            });

            // Activer la section correspondante avec un délai pour l'animation
            setTimeout(() => {
                const activeSection = document.querySelector(`.trimester-section[data-trimester="${trimester}"]`);
                if (activeSection) {
                    activeSection.classList.add('active');
                    activeSection.style.animation = 'fadeIn 0.5s ease forwards';
                }
            }, 200);
        });
    });
}

/**
 * Initialisation des cartes de matières
 */
function initSubjectCards() {
    const subjectCards = document.querySelectorAll('.subject-card');

    subjectCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-4px)';
        });

        card.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0)';
        });
    });
}

/**
 * Ouvre la modal plein écran pour une matière
 */
function openMatiereModal(matiereId) {
    const modal = document.getElementById(`matiere-modal-${matiereId}`);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Ferme la modal plein écran pour une matière
 */
function closeMatiereModal(matiereId) {
    const modal = document.getElementById(`matiere-modal-${matiereId}`);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

/**
 * Change de période dans la modal
 */
function switchPeriodeInModal(matiereId, periodeName) {
    // Désactiver tous les onglets de période pour cette modal
    const modalPeriodeTabs = document.querySelectorAll(`.modal-periode-tab[data-modal-id="${matiereId}"]`);
    modalPeriodeTabs.forEach(tab => tab.classList.remove('active'));

    // Activer l'onglet cliqué
    const clickedTab = document.querySelector(`.modal-periode-tab[data-modal-id="${matiereId}"][data-periode="${periodeName}"]`);
    if (clickedTab) {
        clickedTab.classList.add('active');
    }

    // Masquer tous les contenus de période pour cette modal
    const periodContents = document.querySelectorAll(`.modal-periode-content[data-modal-id="${matiereId}"]`);
    periodContents.forEach(content => content.classList.remove('active'));

    // Afficher le contenu de la période sélectionnée
    const activeContent = document.getElementById(`modal-periode-${matiereId}-${periodeName.toLowerCase().replace(/\s+/g, '-')}`);
    if (activeContent) {
        activeContent.classList.add('active');
    }
}

// Fermer la modal avec la touche Échap
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        const activeModals = document.querySelectorAll('.fullscreen-modal.active');
        activeModals.forEach(modal => {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        });
    }
});
