

    // Activer les menus déroulants
    document.addEventListener('DOMContentLoaded', function () {
        const dropdowns = document.querySelectorAll('.nav-dropdown-toggle');

        dropdowns.forEach(dropdown => {
            dropdown.addEventListener('click', function () {
                const parent = this.parentElement;
                parent.classList.toggle('active');
            });
        });

        // Toggle sidebar on mobile
        const sidebarToggle = document.getElementById('sidebar-toggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', function () {
                const sidebar = document.querySelector('.sidebar');
                sidebar.classList.toggle('active');
            });
        }

        // Détection de la page active
        const currentPath = window.location.pathname;
        const filename = currentPath.split('/').pop();

        const navLinks = document.querySelectorAll('.nav-link, .nav-dropdown-link');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === filename) {
                link.classList.add('active');

                // Si c'est un lien dans un dropdown, activer le dropdown parent
                if (link.classList.contains('nav-dropdown-link')) {
                    const dropdown = link.closest('.nav-dropdown');
                    if (dropdown) {
                        dropdown.classList.add('active');
                    }
                }
            }
        });
    });

    // Simulation de notifications
    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
                <div class="notification-content">
                    <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'}"></i>
                    <span>${message}</span>
                </div>
                <button class="notification-close"><i class="fas fa-times"></i></button>
            `;

        document.body.appendChild(notification);

        // Afficher avec animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        // Fermer la notification
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
            }, 300);
        });

        // Auto-fermeture après 5 secondes
        setTimeout(() => {
            if (document.body.contains(notification)) {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (document.body.contains(notification)) {
                        notification.remove();
                    }
                }, 300);
            }
        }, 5000);
    }

    // Style pour les notifications
    const notificationStyle = document.createElement('style');
    notificationStyle.textContent = `
            .notification {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 15px 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                display: flex;
                align-items: center;
                justify-content: space-between;
                width: 300px;
                max-width: 90vw;
                transform: translateX(120%);
                opacity: 0;
                transition: all 0.3s ease;
                z-index: 9999;
            }
            
            .notification.show {
                transform: translateX(0);
                opacity: 1;
            }
            
            .notification.success {
                border-left: 4px solid var(--success);
            }
            
            .notification.warning {
                border-left: 4px solid var(--warning);
            }
            
            .notification.info {
                border-left: 4px solid var(--primary);
            }
            
            .notification-content {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .notification-content i {
                font-size: 1.2rem;
            }
            
            .notification.success .notification-content i {
                color: var(--success);
            }
            
            .notification.warning .notification-content i {
                color: var(--warning);
            }
            
            .notification.info .notification-content i {
                color: var(--primary);
            }
            
            .notification-close {
                background: none;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                padding: 5px;
                transition: color 0.2s ease;
            }
            
            .notification-close:hover {
                color: var(--text-primary);
            }
        `;
    document.head.appendChild(notificationStyle);
