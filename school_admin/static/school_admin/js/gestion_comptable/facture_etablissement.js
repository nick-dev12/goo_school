// Facture Établissement JavaScript
document.addEventListener('DOMContentLoaded', function () {
    initializeInvoice();
    initializeAnimations();
});

// Initialize Invoice
function initializeInvoice() {
    // Add any initialization logic here
    console.log('Facture initialisée');
}

// Go Back
function goBack() {
    if (window.history.length > 1) {
        window.history.back();
    } else {
        window.location.href = '/comptable/gestion_etablissements/';
    }
}

// Print Invoice
function printInvoice() {
    showNotification('Préparation de l\'impression...', 'info');

    // Hide action buttons for printing
    const actions = document.querySelector('.invoice-actions');
    if (actions) {
        actions.style.display = 'none';
    }

    setTimeout(() => {
        window.print();

        // Show action buttons again after printing
        setTimeout(() => {
            if (actions) {
                actions.style.display = 'flex';
            }
        }, 1000);

        showNotification('Impression lancée', 'success');
    }, 500);
}

// Download PDF
function downloadPDF() {
    showNotification('Génération du PDF...', 'info');

    // Simulate PDF generation
    setTimeout(() => {
        // Create a temporary link to download
        const link = document.createElement('a');
        link.href = '#'; // In a real app, this would be the PDF URL
        link.download = 'Facture-FAC-2024-001.pdf';

        // Trigger download
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        showNotification('PDF téléchargé avec succès', 'success');
    }, 2000);
}

// Send Invoice
function sendInvoice() {
    showNotification('Envoi de la facture par email...', 'info');

    // Simulate email sending
    setTimeout(() => {
        showNotification('Facture envoyée avec succès', 'success');
    }, 2000);
}

// Initialize Animations
function initializeAnimations() {
    // Animate invoice document on load
    const invoiceDocument = document.getElementById('invoiceDocument');
    if (invoiceDocument) {
        invoiceDocument.style.opacity = '0';
        invoiceDocument.style.transform = 'translateY(20px)';

        setTimeout(() => {
            invoiceDocument.style.transition = 'all 0.8s ease-out';
            invoiceDocument.style.opacity = '1';
            invoiceDocument.style.transform = 'translateY(0)';
        }, 200);
    }

    // Add hover effects to buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-2px)';
        });

        button.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0)';
        });
    });

    // Add hover effects to table rows
    const tableRows = document.querySelectorAll('.items-table tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('mouseenter', function () {
            this.style.backgroundColor = 'var(--light-bg)';
        });

        row.addEventListener('mouseleave', function () {
            this.style.backgroundColor = 'transparent';
        });
    });
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

// Add CSS for animations
const style = document.createElement('style');
style.textContent = `
    .success-animation {
        animation: successPulse 0.6s ease-in-out;
    }
    
    @keyframes successPulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(style);

// Export functions to global scope
window.FactureEtablissement = {
    goBack,
    printInvoice,
    downloadPDF,
    sendInvoice,
    showNotification
};
