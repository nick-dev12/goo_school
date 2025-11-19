// Suivi des Revenus JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    initializeSubTabs();
    initializeSearchEntrees();
    initializeSearchDepenses();
    initializeFiltersEntrees();
    initializeFiltersDepenses();
    initializeTableActions();
    initializeTooltips();
    initializeAnimations();
    initializeDepenseModals();
});

// Initialize Main Tabs
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabButtons.forEach(button => {
        button.addEventListener('click', function () {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and panels
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabPanels.forEach(panel => panel.classList.remove('active'));

            // Add active class to clicked button and corresponding panel
            this.classList.add('active');
            document.getElementById(targetTab).classList.add('active');

            // Update URL hash
            window.location.hash = targetTab;

            // Trigger custom event
            document.dispatchEvent(new CustomEvent('tabChanged', {
                detail: { activeTab: targetTab }
            }));
        });
    });

    // Handle initial tab from URL hash
    const hash = window.location.hash.substring(1);
    if (hash && document.getElementById(hash)) {
        const targetButton = document.querySelector(`[data-tab="${hash}"]`);
        if (targetButton) {
            targetButton.click();
        }
    }
}

// Initialize Sub-tabs for Categories
function initializeSubTabs() {
    const subTabButtons = document.querySelectorAll('.sub-tab-btn');
    const subTabTables = document.querySelectorAll('.sub-tab-table');
    const mainTable = document.getElementById('tableToutesDepenses');

    function activateSubTab(button) {
        subTabButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');

        if (mainTable) {
            mainTable.style.display = button.dataset.subTab === 'toutes' ? 'table' : 'none';
        }

        subTabTables.forEach(table => table.style.display = 'none');

        if (button.dataset.subTab !== 'toutes') {
            const targetId = button.dataset.target;
            if (targetId) {
                const targetTable = document.getElementById(targetId);
                if (targetTable) {
                    targetTable.style.display = 'table';
                }
            }
        }

        applyDepensesFilters();
    }

    subTabButtons.forEach(button => {
        button.addEventListener('click', function () {
            activateSubTab(this);
        });
    });

    const defaultButton = document.querySelector('.sub-tab-btn.active') || subTabButtons[0];
    if (defaultButton) {
        activateSubTab(defaultButton);
    }
}

// Initialize Search for Entrées Tab
function initializeSearchEntrees() {
    const searchInput = document.getElementById('searchInputEntrees');
    if (!searchInput) return;

    searchInput.addEventListener('input', function () {
        const searchTerm = this.value.toLowerCase().trim();
        const tableRows = document.querySelectorAll('#entrees .data-table tbody tr');

        tableRows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const shouldShow = text.includes(searchTerm);
            row.style.display = shouldShow ? '' : 'none';
        });

        updateEmptyStateEntrees();
    });
}

// Initialize Search for Dépenses Tab
function initializeSearchDepenses() {
    const searchInput = document.getElementById('searchInputDepenses');
    if (!searchInput) return;

    searchInput.addEventListener('input', function () {
        applyDepensesFilters();
    });
}

// Initialize Filters for Entrées Tab
function initializeFiltersEntrees() {
    const statusFilter = document.getElementById('statusFilterEntrees');
    const typeFilter = document.getElementById('typeFilterEntrees');
    const clearFiltersBtn = document.getElementById('clearFiltersEntrees');

    function applyFilters() {
        const statusValue = statusFilter?.value || '';
        const typeValue = typeFilter?.value || '';
        const searchTerm = document.getElementById('searchInputEntrees')?.value.toLowerCase().trim() || '';
        const tableRows = document.querySelectorAll('#entrees .data-table tbody tr');

        tableRows.forEach(row => {
            let shouldShow = true;

            // Search filter
            if (searchTerm) {
                const text = row.textContent.toLowerCase();
                shouldShow = shouldShow && text.includes(searchTerm);
            }

            // Status filter
            if (statusValue) {
                const statusBadge = row.querySelector('.status-badge');
                if (statusBadge) {
                    const statusText = statusBadge.textContent.toLowerCase().trim();
                    const statusMap = {
                        'en_regle': ['en règle', 'en-regle'],
                        'en_retard': ['en retard', 'en-retard'],
                        'non_en_regle': ['non en règle', 'non-en-regle'],
                        'contentieux': ['contentieux']
                    };
                    const matches = statusMap[statusValue] || [];
                    shouldShow = shouldShow && matches.some(m => statusText.includes(m));
                }
            }

            // Type filter
            if (typeValue) {
                const etablissementInfo = row.querySelector('.etablissement-info');
                if (etablissementInfo) {
                    const typeBadge = row.querySelector('.type-badge');
                    if (typeBadge) {
                        const typeText = typeBadge.textContent.toLowerCase().trim();
                        shouldShow = shouldShow && typeText.includes(typeValue);
                    }
                }
            }

            row.style.display = shouldShow ? '' : 'none';
        });

        updateEmptyStateEntrees();
    }

    if (statusFilter) statusFilter.addEventListener('change', applyFilters);
    if (typeFilter) typeFilter.addEventListener('change', applyFilters);
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', function () {
            if (statusFilter) statusFilter.value = '';
            if (typeFilter) typeFilter.value = '';
            const searchInput = document.getElementById('searchInputEntrees');
            if (searchInput) searchInput.value = '';
            applyFilters();
        });
    }
}

// Initialize Filters for Dépenses Tab
function initializeFiltersDepenses() {
    const statutFilter = document.getElementById('statutFilterDepenses');
    const typeDepenseFilter = document.getElementById('typeDepenseFilter');
    const methodePaiementFilter = document.getElementById('methodePaiementFilter');
    const clearFiltersBtn = document.getElementById('clearFiltersDepenses');

    function applyFilters() {
        applyDepensesFilters();
    }

    if (statutFilter) statutFilter.addEventListener('change', applyFilters);
    if (typeDepenseFilter) typeDepenseFilter.addEventListener('change', applyFilters);
    if (methodePaiementFilter) methodePaiementFilter.addEventListener('change', applyFilters);
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', function () {
            if (statutFilter) statutFilter.value = '';
            if (typeDepenseFilter) typeDepenseFilter.value = '';
            if (methodePaiementFilter) methodePaiementFilter.value = '';
            const searchInput = document.getElementById('searchInputDepenses');
            if (searchInput) searchInput.value = '';
            applyDepensesFilters();
        });
    }
}

// Apply filters for Dépenses
function applyDepensesFilters() {
    const searchTerm = document.getElementById('searchInputDepenses')?.value.toLowerCase().trim() || '';
    const statutValue = document.getElementById('statutFilterDepenses')?.value || '';
    const typeDepenseValue = document.getElementById('typeDepenseFilter')?.value || '';
    const methodePaiementValue = document.getElementById('methodePaiementFilter')?.value || '';

    const depensesTables = document.querySelectorAll('#depenses .data-table');

    depensesTables.forEach(table => {
        const rows = table.querySelectorAll('tbody tr');

        rows.forEach(row => {
            let shouldShow = true;

            if (searchTerm) {
                const searchText = row.getAttribute('data-search-text') || '';
                shouldShow = shouldShow && searchText.includes(searchTerm);
            }

            if (statutValue) {
                const rowStatut = row.getAttribute('data-statut') || '';
                shouldShow = shouldShow && rowStatut === statutValue;
            }

            if (typeDepenseValue) {
                const rowTypeDepense = row.getAttribute('data-type-depense') || '';
                shouldShow = shouldShow && rowTypeDepense === typeDepenseValue;
            }

            if (methodePaiementValue) {
                const rowMethodePaiement = (row.getAttribute('data-methode-paiement') || '').toLowerCase();
                shouldShow = shouldShow && rowMethodePaiement === methodePaiementValue;
            }

            row.style.display = shouldShow ? '' : 'none';
        });
    });

    updateEmptyStateDepenses();
}

// Update Empty State for Entrées
function updateEmptyStateEntrees() {
    const entreesPanel = document.getElementById('entrees');
    if (!entreesPanel) return;
    
    const visibleRows = entreesPanel.querySelectorAll('.data-table tbody tr:not([style*="display: none"])');
    const emptyState = entreesPanel.querySelector('.empty-state');
    
    if (visibleRows.length === 0 && !emptyState) {
        const emptyStateDiv = document.createElement('div');
        emptyStateDiv.className = 'empty-state';
        emptyStateDiv.innerHTML = `
            <i class="fas fa-search"></i>
            <h3>Aucun résultat trouvé</h3>
            <p>Essayez de modifier vos critères de recherche ou de filtrage</p>
        `;
        const tableContainer = entreesPanel.querySelector('.table-container');
        if (tableContainer) {
            tableContainer.appendChild(emptyStateDiv);
        }
    } else if (visibleRows.length > 0 && emptyState) {
        emptyState.remove();
    }
}

// Update Empty State for Dépenses
function updateEmptyStateDepenses() {
    const depensesPanel = document.getElementById('depenses');
    if (!depensesPanel) return;
    
    const activeSubTab = document.querySelector('.sub-tab-btn.active');
    const defaultTable = document.getElementById('tableToutesDepenses');
    let activeTable = defaultTable;

    if (activeSubTab) {
        if (activeSubTab.dataset.subTab === 'toutes' || !activeSubTab.dataset.target) {
            activeTable = defaultTable;
        } else {
            activeTable = document.getElementById(activeSubTab.dataset.target) || defaultTable;
        }
    }
    
    if (!activeTable) return;
    
    const visibleRows = activeTable.querySelectorAll('tbody tr:not([style*="display: none"])');
    const tableWrapper = activeTable.closest('.table-wrapper');
    let emptyState = tableWrapper?.querySelector('.empty-state');
    
    if (visibleRows.length === 0 && !emptyState) {
        const emptyStateDiv = document.createElement('div');
        emptyStateDiv.className = 'empty-state';
        emptyStateDiv.innerHTML = `
            <i class="fas fa-search"></i>
            <h3>Aucun résultat trouvé</h3>
            <p>Essayez de modifier vos critères de recherche ou de filtrage</p>
        `;
        if (tableWrapper) {
            tableWrapper.appendChild(emptyStateDiv);
        }
    } else if (visibleRows.length > 0 && emptyState) {
        emptyState.remove();
    }
}

// Initialize Table Actions
function initializeTableActions() {
    const actionButtons = document.querySelectorAll('.btn-action');

    actionButtons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    });
}

// Initialize Tooltips
function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[title]');

    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

// Show Tooltip
function showTooltip(event) {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = event.target.getAttribute('title');
    tooltip.style.cssText = `
        position: absolute;
        background: #2d3748;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 12px;
        z-index: 1000;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.2s ease;
        max-width: 200px;
        word-wrap: break-word;
    `;

    document.body.appendChild(tooltip);

    const rect = event.target.getBoundingClientRect();
    tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
    tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';

    // Adjust if tooltip goes off screen
    if (tooltip.offsetLeft < 0) {
        tooltip.style.left = '8px';
    }
    if (tooltip.offsetLeft + tooltip.offsetWidth > window.innerWidth) {
        tooltip.style.left = (window.innerWidth - tooltip.offsetWidth - 8) + 'px';
    }

    setTimeout(() => {
        tooltip.style.opacity = '1';
    }, 10);

    event.target._tooltip = tooltip;
}

// Hide Tooltip
function hideTooltip(event) {
    if (event.target._tooltip) {
        event.target._tooltip.remove();
        delete event.target._tooltip;
    }
}

// Initialize Animations
function initializeAnimations() {
    // Animate cards on load
    const cards = document.querySelectorAll('.summary-card, .table-container');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';

        setTimeout(() => {
            card.style.transition = 'all 0.6s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Add hover effects to table rows
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('mouseenter', function () {
            this.style.transform = 'translateX(4px)';
        });

        row.addEventListener('mouseleave', function () {
            this.style.transform = 'translateX(0)';
        });
    });
}

// Initialize Depense Modals
function initializeDepenseModals() {
    // Bouton ajouter dépense
    const btnAjouterDepense = document.getElementById('btnAjouterDepense');
    if (btnAjouterDepense) {
        btnAjouterDepense.addEventListener('click', function() {
            ouvrirModalDepense();
        });
    }
    
    // Fermer modal en cliquant en dehors
    const depenseModal = document.getElementById('depenseModal');
    if (depenseModal) {
        depenseModal.addEventListener('click', function(e) {
            if (e.target === depenseModal) {
                fermerModalDepense();
            }
        });
    }
    
    const voirDepenseModal = document.getElementById('voirDepenseModal');
    if (voirDepenseModal) {
        voirDepenseModal.addEventListener('click', function(e) {
            if (e.target === voirDepenseModal) {
                fermerModalVoirDepense();
            }
        });
    }
}

// Ouvrir modal pour ajouter une dépense
function ouvrirModalDepense() {
    const modal = document.getElementById('depenseModal');
    const form = document.getElementById('depenseForm');
    const title = document.getElementById('modalDepenseTitle');
    
    if (modal && form && title) {
        // Réinitialiser le formulaire
        form.reset();
        document.getElementById('depenseAction').value = 'ajouter_depense';
        document.getElementById('depenseId').value = '';
        document.getElementById('datePaiementGroup').style.display = 'none';
        document.getElementById('pieceJointePreview').style.display = 'none';
        const typeSelect = document.getElementById('type_depense');
        if (typeSelect) {
            typeSelect.value = 'unique';
        }
        
        // Mettre à jour le titre
        title.innerHTML = '<i class="fas fa-plus-circle"></i> Ajouter une dépense';
        
        // Afficher le modal
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

// Modifier une dépense
function modifierDepense(depenseId) {
    // Récupérer les données de la dépense depuis le serveur
    fetch(`/gestion_comptable/depense/${depenseId}/`, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const depense = data.depense;
                const modal = document.getElementById('depenseModal');
                const form = document.getElementById('depenseForm');
                const title = document.getElementById('modalDepenseTitle');
                
                if (modal && form && title) {
                    // Remplir le formulaire
                    document.getElementById('depenseAction').value = 'modifier_depense';
                    document.getElementById('depenseId').value = depenseId;
                    document.getElementById('description').value = depense.description || '';
                    document.getElementById('montant').value = depense.montant || '';
                    document.getElementById('categorie').value = depense.categorie || '';
                    if (document.getElementById('type_depense')) {
                        document.getElementById('type_depense').value = depense.type_depense || 'unique';
                    }
                    document.getElementById('date_depense').value = depense.date_depense || '';
                    document.getElementById('statut').value = depense.statut || 'en_attente';
                    document.getElementById('fournisseur').value = depense.fournisseur || '';
                    document.getElementById('numero_facture').value = depense.numero_facture || '';
                    document.getElementById('methode_paiement').value = depense.methode_paiement || 'virement';
                    document.getElementById('etablissement').value = depense.etablissement_id || '';
                    document.getElementById('notes').value = depense.notes || '';
                    
                    // Gérer la date de paiement
                    if (depense.date_paiement) {
                        document.getElementById('date_paiement').value = depense.date_paiement;
                    }
                    toggleDatePaiement();
                    
                    // Gérer la pièce jointe
                    if (depense.piece_jointe) {
                        document.getElementById('pieceJointeLink').href = depense.piece_jointe;
                        document.getElementById('pieceJointePreview').style.display = 'block';
                    } else {
                        document.getElementById('pieceJointePreview').style.display = 'none';
                    }
                    
                    // Mettre à jour le titre
                    title.innerHTML = '<i class="fas fa-edit"></i> Modifier la dépense';
                    
                    // Afficher le modal
                    modal.style.display = 'flex';
                    document.body.style.overflow = 'hidden';
                }
            } else {
                showNotification('Erreur lors du chargement de la dépense', 'error');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showNotification('Erreur lors du chargement de la dépense', 'error');
        });
}

// Voir une dépense
function voirDepense(depenseId) {
    // Récupérer les données de la dépense depuis le serveur
    fetch(`/gestion_comptable/depense/${depenseId}/`, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const depense = data.depense;
                const modal = document.getElementById('voirDepenseModal');
                const content = document.getElementById('voirDepenseContent');
                
                if (modal && content) {
                    // Construire le contenu HTML
                    let html = `
                        <div class="depense-details">
                            <div class="detail-section">
                                <h3><i class="fas fa-info-circle"></i> Informations générales</h3>
                                <div class="detail-grid">
                                    <div class="detail-item">
                                        <label>Description:</label>
                                        <p>${depense.description || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Catégorie:</label>
                                        <p>${depense.categorie_display || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Type de dépense:</label>
                                        <p>${depense.type_depense_display || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Montant:</label>
                                        <p class="amount">${depense.montant_formatted || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Date de dépense:</label>
                                        <p>${depense.date_depense_display || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Statut:</label>
                                        <span class="status-badge ${depense.statut_class || ''}">${depense.statut_display || 'N/A'}</span>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="detail-section">
                                <h3><i class="fas fa-building"></i> Fournisseur et paiement</h3>
                                <div class="detail-grid">
                                    <div class="detail-item">
                                        <label>Fournisseur:</label>
                                        <p>${depense.fournisseur || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Numéro de facture:</label>
                                        <p>${depense.numero_facture || 'N/A'}</p>
                                    </div>
                                    <div class="detail-item">
                                        <label>Méthode de paiement:</label>
                                        <p>${depense.methode_paiement_display || 'N/A'}</p>
                                    </div>
                                    ${depense.date_paiement ? `
                                    <div class="detail-item">
                                        <label>Date de paiement:</label>
                                        <p>${depense.date_paiement_display}</p>
                                    </div>
                                    ` : ''}
                                </div>
                            </div>
                            
                            ${depense.etablissement ? `
                            <div class="detail-section">
                                <h3><i class="fas fa-school"></i> Établissement</h3>
                                <div class="detail-item">
                                    <label>Établissement concerné:</label>
                                    <p>${depense.etablissement_nom}</p>
                                </div>
                            </div>
                            ` : ''}
                            
                            ${depense.notes ? `
                            <div class="detail-section">
                                <h3><i class="fas fa-sticky-note"></i> Notes</h3>
                                <p>${depense.notes}</p>
                            </div>
                            ` : ''}
                            
                            ${depense.piece_jointe ? `
                            <div class="detail-section">
                                <h3><i class="fas fa-file"></i> Pièce jointe</h3>
                                <a href="${depense.piece_jointe}" target="_blank" class="btn-primary">
                                    <i class="fas fa-download"></i> Télécharger la pièce jointe
                                </a>
                            </div>
                            ` : ''}
                        </div>
                    `;
                    
                    content.innerHTML = html;
                    
                    // Afficher le modal
                    modal.style.display = 'flex';
                    document.body.style.overflow = 'hidden';
                }
            } else {
                showNotification('Erreur lors du chargement de la dépense', 'error');
            }
        })
        .catch(error => {
            console.error('Erreur:', error);
            showNotification('Erreur lors du chargement de la dépense', 'error');
        });
}

// Fermer modal dépense
function fermerModalDepense() {
    const modal = document.getElementById('depenseModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Fermer modal voir dépense
function fermerModalVoirDepense() {
    const modal = document.getElementById('voirDepenseModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Toggle date de paiement
function toggleDatePaiement() {
    const statut = document.getElementById('statut').value;
    const datePaiementGroup = document.getElementById('datePaiementGroup');
    
    if (statut === 'paye') {
        datePaiementGroup.style.display = 'block';
        document.getElementById('date_paiement').required = true;
    } else {
        datePaiementGroup.style.display = 'none';
        document.getElementById('date_paiement').required = false;
    }
}

// Show Notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    const styles = {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '12px 20px',
        borderRadius: '8px',
        color: 'white',
        fontWeight: '600',
        zIndex: '10000',
        opacity: '0',
        transform: 'translateX(100%)',
        transition: 'all 0.3s ease',
        maxWidth: '300px',
        wordWrap: 'break-word'
    };

    // Colors according to type
    switch (type) {
        case 'success':
            styles.backgroundColor = '#38a169';
            break;
        case 'error':
            styles.backgroundColor = '#e53e3e';
            break;
        case 'warning':
            styles.backgroundColor = '#dd6b20';
            break;
        default:
            styles.backgroundColor = '#3182ce';
    }

    Object.assign(notification.style, styles);

    document.body.appendChild(notification);

    // Animation d'entrée
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    }, 10);

    // Suppression automatique
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Export functions to global scope
window.ouvrirModalDepense = ouvrirModalDepense;
window.modifierDepense = modifierDepense;
window.voirDepense = voirDepense;
window.fermerModalDepense = fermerModalDepense;
window.fermerModalVoirDepense = fermerModalVoirDepense;
window.toggleDatePaiement = toggleDatePaiement;

// Add CSS for search highlight
const style = document.createElement('style');
style.textContent = `
    .search-highlight {
        background-color: #fef5e7 !important;
        border-left: 4px solid #f6ad55 !important;
    }
    
    .tooltip {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    .empty-state {
        text-align: center;
        padding: 3rem 1rem;
        color: var(--text-secondary);
    }
    
    .empty-state i {
        font-size: 3rem;
        margin-bottom: 1rem;
        opacity: 0.5;
    }
    
    .empty-state h3 {
        margin: 0.5rem 0;
        color: var(--text-primary);
    }
`;
document.head.appendChild(style);
