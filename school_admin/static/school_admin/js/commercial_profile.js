document.addEventListener('DOMContentLoaded', function () {
    // Éléments
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const periodBtns = document.querySelectorAll('.period-btn');
    const filterSelects = document.querySelectorAll('.filter-select');
    const filterInputs = document.querySelectorAll('.filter-input');

    // Navigation des onglets
    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            const targetTab = this.getAttribute('data-tab');

            // Retirer la classe active de tous les onglets
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Ajouter la classe active à l'onglet cliqué
            this.classList.add('active');

            // Afficher le contenu correspondant
            const targetContent = document.getElementById(targetTab + '-tab');
            if (targetContent) {
                targetContent.classList.add('active');

                // Initialiser les graphiques si nécessaire
                if (targetTab === 'performance') {
                    initPerformanceChart();
                }
            }
        });
    });

    // Sélecteur de période
    periodBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            periodBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Mettre à jour les données selon la période sélectionnée
            updatePerformanceData(this.textContent.trim());
        });
    });

    // Filtres
    filterSelects.forEach(select => {
        select.addEventListener('change', function () {
            applyFilters();
        });
    });

    filterInputs.forEach(input => {
        input.addEventListener('input', debounce(function () {
            applyFilters();
        }, 300));
    });

    // Initialiser le graphique de performance
    function initPerformanceChart() {
        const ctx = document.getElementById('performanceChart');
        if (!ctx) return;

        // Données simulées (à remplacer par les vraies données)
        const monthlyData = [
            { month: 'Jan', objectif: 50000, realise: 45000 },
            { month: 'Fév', objectif: 50000, realise: 52000 },
            { month: 'Mar', objectif: 50000, realise: 48000 },
            { month: 'Avr', objectif: 50000, realise: 55000 },
            { month: 'Mai', objectif: 50000, realise: 47000 },
            { month: 'Juin', objectif: 50000, realise: 60000 },
        ];

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: monthlyData.map(item => item.month),
                datasets: [
                    {
                        label: 'Objectif',
                        data: monthlyData.map(item => item.objectif),
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderColor: 'rgba(59, 130, 246, 0.8)',
                        borderWidth: 2,
                        borderRadius: 4,
                        borderSkipped: false,
                    },
                    {
                        label: 'Réalisé',
                        data: monthlyData.map(item => item.realise),
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderColor: 'rgba(16, 185, 129, 0.8)',
                        borderWidth: 2,
                        borderRadius: 4,
                        borderSkipped: false,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 20
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: 'white',
                        bodyColor: 'white',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        cornerRadius: 8,
                        displayColors: true,
                        callbacks: {
                            label: function (context) {
                                return context.dataset.label + ': ' + context.parsed.y.toLocaleString() + '€';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#64748b',
                            font: {
                                size: 12
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#64748b',
                            font: {
                                size: 12
                            },
                            callback: function (value) {
                                return value.toLocaleString() + '€';
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                }
            }
        });
    }

    // Mettre à jour les données de performance
    function updatePerformanceData(period) {
        console.log('Mise à jour des données pour la période:', period);
        // Ici vous pourriez faire un appel AJAX pour récupérer les nouvelles données
        // et mettre à jour le graphique
    }

    // Appliquer les filtres
    function applyFilters() {
        const filters = {
            type: document.querySelector('select[data-filter="type"]')?.value || '',
            startDate: document.querySelector('input[data-filter="start-date"]')?.value || '',
            endDate: document.querySelector('input[data-filter="end-date"]')?.value || ''
        };

        console.log('Filtres appliqués:', filters);
        // Ici vous pourriez faire un appel AJAX pour filtrer les données
    }

    // Fonction debounce pour les filtres
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Gestion des actions sur les cartes de projet
    document.addEventListener('click', function (e) {
        if (e.target.closest('.project-actions .btn')) {
            const action = e.target.closest('.btn');
            const projectCard = action.closest('.project-card');
            const projectName = projectCard.querySelector('h3').textContent;

            if (action.textContent.includes('Modifier')) {
                showModal('Modifier le projet', `Modification du projet "${projectName}"`);
            } else if (action.textContent.includes('Voir détails')) {
                showModal('Détails du projet', `Détails du projet "${projectName}"`);
            }
        }
    });

    // Gestion des actions sur les notes
    document.addEventListener('click', function (e) {
        if (e.target.closest('.note-actions .btn')) {
            const action = e.target.closest('.btn');
            const noteItem = action.closest('.note-item');

            if (action.textContent.includes('Modifier')) {
                showModal('Modifier la note', 'Modification de la note');
            } else if (action.textContent.includes('Supprimer')) {
                if (confirm('Êtes-vous sûr de vouloir supprimer cette note ?')) {
                    noteItem.style.animation = 'fadeOut 0.3s ease forwards';
                    setTimeout(() => noteItem.remove(), 300);
                }
            }
        }
    });

    // Gestion des actions sur les documents
    document.addEventListener('click', function (e) {
        if (e.target.closest('.document-actions .btn')) {
            const action = e.target.closest('.btn');
            const documentItem = action.closest('.document-item');
            const documentName = documentItem.querySelector('h4').textContent;

            if (action.querySelector('.fa-download')) {
                showToast(`Téléchargement de "${documentName}"`, 'info');
            } else if (action.querySelector('.fa-eye')) {
                showModal('Aperçu du document', `Aperçu de "${documentName}"`);
            }
        }
    });

    // Gestion des actions du profil
    document.addEventListener('click', function (e) {
        if (e.target.closest('.profile-actions .btn')) {
            const action = e.target.closest('.btn');

            if (action.textContent.includes('Modifier le profil')) {
                showModal('Modifier le profil', 'Modification du profil commercial');
            } else if (action.textContent.includes('Contacter')) {
                showModal('Contacter', 'Envoi d\'un message au commercial');
            } else if (action.textContent.includes('Exporter données')) {
                showToast('Export des données en cours...', 'info');
                // Simuler l'export
                setTimeout(() => {
                    showToast('Données exportées avec succès !', 'success');
                }, 2000);
            }
        }
    });

    // Fonction pour afficher un modal
    function showModal(title, content) {
        // Créer le modal s'il n'existe pas
        let modal = document.getElementById('dynamicModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'dynamicModal';
            modal.className = 'modal-overlay';
            modal.innerHTML = `
                <div class="modal">
                    <div class="modal-header">
                        <h3 class="modal-title"></h3>
                        <button class="modal-close">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        <p class="modal-content"></p>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary modal-cancel">Annuler</button>
                        <button class="btn btn-primary modal-confirm">Confirmer</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // Ajouter les styles pour le modal
            const style = document.createElement('style');
            style.textContent = `
                .modal-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 1000;
                    opacity: 0;
                    visibility: hidden;
                    transition: all 0.3s ease;
                }
                
                .modal-overlay.show {
                    opacity: 1;
                    visibility: visible;
                }
                
                .modal {
                    background: white;
                    border-radius: 0.75rem;
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                    max-width: 500px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                    transform: scale(0.9);
                    transition: transform 0.3s ease;
                }
                
                .modal-overlay.show .modal {
                    transform: scale(1);
                }
                
                .modal-header {
                    padding: 1.5rem 1.5rem 0;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 1px solid #e2e8f0;
                    margin-bottom: 1.5rem;
                }
                
                .modal-title {
                    font-size: 1.25rem;
                    font-weight: 600;
                    color: #1e293b;
                }
                
                .modal-close {
                    background: none;
                    border: none;
                    color: #64748b;
                    cursor: pointer;
                    padding: 0.5rem;
                    border-radius: 0.375rem;
                    transition: color 0.2s ease;
                }
                
                .modal-close:hover {
                    color: #1e293b;
                }
                
                .modal-body {
                    padding: 0 1.5rem;
                }
                
                .modal-content {
                    color: #64748b;
                    line-height: 1.6;
                }
                
                .modal-footer {
                    padding: 1.5rem;
                    display: flex;
                    justify-content: flex-end;
                    gap: 0.75rem;
                    border-top: 1px solid #e2e8f0;
                    margin-top: 1.5rem;
                }
                
                @keyframes fadeOut {
                    from { opacity: 1; transform: translateY(0); }
                    to { opacity: 0; transform: translateY(-20px); }
                }
            `;
            document.head.appendChild(style);

            // Ajouter les événements
            modal.querySelector('.modal-close').addEventListener('click', hideModal);
            modal.querySelector('.modal-cancel').addEventListener('click', hideModal);
            modal.querySelector('.modal-confirm').addEventListener('click', hideModal);
            modal.addEventListener('click', function (e) {
                if (e.target === modal) hideModal();
            });
        }

        // Mettre à jour le contenu
        modal.querySelector('.modal-title').textContent = title;
        modal.querySelector('.modal-content').textContent = content;

        // Afficher le modal
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    // Fonction pour masquer le modal
    function hideModal() {
        const modal = document.getElementById('dynamicModal');
        if (modal) {
            modal.classList.remove('show');
            document.body.style.overflow = '';
        }
    }

    // Fonction pour afficher un toast
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-times-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };

        const titles = {
            success: 'Succès',
            error: 'Erreur',
            warning: 'Attention',
            info: 'Information'
        };

        toast.innerHTML = `
            <div class="toast-icon">
                <i class="${icons[type]}"></i>
            </div>
            <div class="toast-content">
                <div class="toast-title">${titles[type]}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Ajouter au conteneur de notifications
        let container = document.querySelector('.notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'notifications-container';
            document.body.appendChild(container);
        }

        container.appendChild(toast);

        // Afficher le toast
        setTimeout(() => toast.classList.add('show'), 100);

        // Auto-masquer après 5 secondes
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 5000);

        // Bouton de fermeture
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        });
    }

    // Animation d'entrée pour les cartes
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animation = 'fadeIn 0.6s ease forwards';
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observer toutes les cartes
    document.querySelectorAll('.card, .project-card, .note-item, .document-item').forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        observer.observe(card);
    });

    // Initialiser le graphique si on est sur l'onglet performance
    if (document.querySelector('#performance-tab').classList.contains('active')) {
        initPerformanceChart();
    }
});
