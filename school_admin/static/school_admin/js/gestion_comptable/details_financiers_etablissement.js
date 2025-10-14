// Détails Financiers Établissement JavaScript

// Fonctions de navigation
function goBack() {
    window.history.back();
}

function refreshData() {
    location.reload();
}

function exportData() {
    // Fonction d'export des données
    console.log('Export des données...');
    // TODO: Implémenter l'export
}

// Gestion de la modal de facturation
function openInvoiceModal() {
    const modal = document.getElementById('invoiceModal');
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
    
    // Définir la date d'échéance par défaut (30 jours)
    const dateEcheance = document.getElementById('date_echeance');
    const today = new Date();
    const futureDate = new Date(today.getTime() + (30 * 24 * 60 * 60 * 1000));
    dateEcheance.value = futureDate.toISOString().split('T')[0];
    
    // Calculer le montant total initial
    calculateTotal();
}

function closeInvoiceModal() {
    const modal = document.getElementById('invoiceModal');
    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
        // Réinitialiser le formulaire
        document.getElementById('invoiceForm').reset();
        document.getElementById('totalAmount').textContent = '0.00';
    }, 300);
}

// Calcul automatique du montant total
function calculateTotal() {
    const montantUnitaire = parseFloat(document.getElementById('montant_unitaire').value) || 0;
    const quantite = parseInt(document.getElementById('quantite').value) || 1;
    const total = montantUnitaire * quantite;
    
    document.getElementById('totalAmount').textContent = total.toFixed(2);
}

// Événements pour le calcul automatique
document.addEventListener('DOMContentLoaded', function() {
    const montantInput = document.getElementById('montant_unitaire');
    const quantiteInput = document.getElementById('quantite');
    
    if (montantInput) {
        montantInput.addEventListener('input', calculateTotal);
    }
    
    if (quantiteInput) {
        quantiteInput.addEventListener('input', calculateTotal);
    }
    
    // Fermer la modal en cliquant à l'extérieur
    const modal = document.getElementById('invoiceModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeInvoiceModal();
            }
        });
    }
    
    // Fermer la modal avec la touche Échap
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeInvoiceModal();
        }
    });
});

// Gestion des onglets
function switchTab(tabName) {
    // Masquer tous les onglets
    const tabs = document.querySelectorAll('.tab-panel');
    tabs.forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Désactiver tous les boutons d'onglets
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Afficher l'onglet sélectionné
    const activeTab = document.getElementById(tabName);
    if (activeTab) {
        activeTab.classList.add('active');
    }
    
    // Activer le bouton correspondant
    const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
    if (activeButton) {
        activeButton.classList.add('active');
    }
}

// Fonctions pour les actions des boutons
function addPayment() {
    console.log('Ajouter un paiement...');
    // TODO: Implémenter l'ajout de paiement
}

function generateNewInvoice() {
    openInvoiceModal();
}

function generateReport() {
    console.log('Générer un rapport...');
    // TODO: Implémenter la génération de rapport
}

function uploadDocument() {
    console.log('Télécharger un document...');
    // TODO: Implémenter le téléchargement de document
}

// Validation du formulaire de facturation
function validateInvoiceForm() {
    const form = document.getElementById('invoiceForm');
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = '#ef4444';
            isValid = false;
        } else {
            field.style.borderColor = '';
        }
    });
    
    // Validation spécifique pour les montants
    const montantUnitaire = parseFloat(document.getElementById('montant_unitaire').value);
    if (montantUnitaire <= 0) {
        document.getElementById('montant_unitaire').style.borderColor = '#ef4444';
        isValid = false;
    }
    
    return isValid;
}

// Soumission du formulaire avec validation
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('invoiceForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!validateInvoiceForm()) {
                e.preventDefault();
                alert('Veuillez remplir tous les champs obligatoires correctement.');
            }
        });
    }
});

// Auto-refresh des données (optionnel)
function startAutoRefresh() {
    setInterval(function() {
        // Actualiser seulement les données critiques
        console.log('Actualisation automatique des données...');
    }, 300000); // 5 minutes
}

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    console.log('Détails financiers établissement initialisés');
    
    // Initialiser les événements des onglets
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const tabName = this.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
    
    // Démarrer l'auto-refresh si nécessaire
    // startAutoRefresh();
});