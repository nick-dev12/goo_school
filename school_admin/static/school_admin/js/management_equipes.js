document.addEventListener('DOMContentLoaded', function () {
    // Elements
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const searchInput = document.getElementById('searchInput');
    const roleFilter = document.getElementById('roleFilter');
    const statusFilter = document.getElementById('statusFilter');
    const departmentFilter = document.getElementById('departmentFilter');
    const memberCards = document.querySelectorAll('.member-card');
    const toast = document.getElementById('toastNotification');
    const closeToast = document.getElementById('closeToast');
    const exportTeamBtn = document.getElementById('exportTeam');

    // Tab switching functionality
    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            // Remove active class from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            // Add active class to clicked tab
            this.classList.add('active');

            // Hide all tab contents
            tabContents.forEach(content => content.classList.remove('active'));

            // Show selected tab content
            const tabId = this.getAttribute('data-tab') + '-tab';
            const targetContent = document.getElementById(tabId);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });


    // Search and filter functionality
    function filterMembers() {
        const searchTerm = searchInput.value.toLowerCase();
        const selectedRole = roleFilter.value;
        const selectedStatus = statusFilter.value;
        const selectedDepartment = departmentFilter.value;

        memberCards.forEach(card => {
            const memberName = card.querySelector('.member-name').textContent.toLowerCase();
            const memberEmail = card.querySelector('.detail-item span').textContent.toLowerCase();
            const cardRole = card.getAttribute('data-role');
            const cardStatus = card.getAttribute('data-status');
            const cardDepartment = card.getAttribute('data-department');

            const matchesSearch = memberName.includes(searchTerm) || memberEmail.includes(searchTerm);
            const matchesRole = !selectedRole || cardRole === selectedRole;
            const matchesStatus = !selectedStatus || cardStatus === selectedStatus;
            const matchesDepartment = !selectedDepartment || cardDepartment === selectedDepartment;

            if (matchesSearch && matchesRole && matchesStatus && matchesDepartment) {
                card.style.display = 'block';
                card.style.animation = 'fadeIn 0.3s ease forwards';
            } else {
                card.style.display = 'none';
            }
        });
    }

    searchInput.addEventListener('input', filterMembers);
    roleFilter.addEventListener('change', filterMembers);
    statusFilter.addEventListener('change', filterMembers);
    departmentFilter.addEventListener('change', filterMembers);

    // Member action buttons
    function setupMemberActions() {
        const actionBtns = document.querySelectorAll('.action-btn');

        actionBtns.forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();

                const memberCard = this.closest('.member-card');
                const memberName = memberCard.querySelector('.member-name').textContent;

                if (this.classList.contains('profile')) {
                    // Le lien de profil redirige automatiquement
                    return;
                } else if (this.classList.contains('edit')) {
                    showToast(`Modification du profil de ${memberName}`, 'info');
                    // Ici vous pourriez ouvrir un modal d'édition
                } else if (this.classList.contains('message')) {
                    showToast(`Envoi d'un message à ${memberName}`, 'info');
                    // Ici vous pourriez ouvrir une interface de messagerie
                } else if (this.classList.contains('more')) {
                    showContextMenu(this, memberName);
                }
            });
        });
    }

    // Context menu for more options
    function showContextMenu(btn, memberName) {
        const existingMenu = document.querySelector('.context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        const contextMenu = document.createElement('div');
        contextMenu.className = 'context-menu';
        contextMenu.innerHTML = `
            <div class="context-menu-item" data-action="view">
                <i class="fas fa-eye"></i> Voir le profil
            </div>
            <div class="context-menu-item" data-action="permissions">
                <i class="fas fa-key"></i> Gérer les permissions
            </div>
            <div class="context-menu-item" data-action="deactivate">
                <i class="fas fa-user-slash"></i> Désactiver
            </div>
            <div class="context-menu-item context-menu-item-danger" data-action="delete">
                <i class="fas fa-trash"></i> Supprimer
            </div>
        `;

        // Position the menu
        const rect = btn.getBoundingClientRect();
        contextMenu.style.position = 'fixed';
        contextMenu.style.top = rect.bottom + 5 + 'px';
        contextMenu.style.left = rect.left + 'px';
        contextMenu.style.zIndex = '1002';

        document.body.appendChild(contextMenu);

        // Add event listeners to menu items
        contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
            item.addEventListener('click', function () {
                const action = this.getAttribute('data-action');
                handleContextMenuAction(action, memberName);
                contextMenu.remove();
            });
        });

        // Close menu when clicking outside
        document.addEventListener('click', function (e) {
            if (!contextMenu.contains(e.target)) {
                contextMenu.remove();
            }
        }, { once: true });
    }

    function handleContextMenuAction(action, memberName) {
        switch (action) {
            case 'view':
                showToast(`Affichage du profil de ${memberName}`, 'info');
                break;
            case 'permissions':
                showToast(`Gestion des permissions de ${memberName}`, 'info');
                break;
            case 'deactivate':
                if (confirm(`Êtes-vous sûr de vouloir désactiver ${memberName} ?`)) {
                    showToast(`${memberName} a été désactivé`, 'warning');
                }
                break;
            case 'delete':
                if (confirm(`Êtes-vous sûr de vouloir supprimer ${memberName} de l'équipe ?`)) {
                    showToast(`${memberName} a été supprimé de l'équipe`, 'error');
                }
                break;
        }
    }


    // Update statistics
    function updateStatistics() {
        const roles = ['commercial', 'developer', 'accountant', 'support', 'manager'];
        const statCards = document.querySelectorAll('.stat-card');

        roles.forEach((role, index) => {
            const count = document.querySelectorAll(`[data-role="${role}"]`).length;
            const statValue = statCards[index]?.querySelector('.stat-value');
            if (statValue) {
                statValue.textContent = count;
                statValue.style.animation = 'pulse 0.5s ease';
            }
        });
    }

    // Export team functionality
    exportTeamBtn.addEventListener('click', function () {
        const teamData = Array.from(memberCards).map(card => {
            return {
                name: card.querySelector('.member-name').textContent,
                role: card.querySelector('.member-role').textContent,
                department: card.querySelector('.member-department').textContent,
                email: card.querySelector('.detail-item span').textContent,
                status: card.getAttribute('data-status')
            };
        });

        // Simulate export (in real app, this would generate a file)
        console.log('Team data exported:', teamData);
        showToast('Les données de l\'équipe ont été exportées avec succès !', 'success');
    });

    // Toast notification system
    function showToast(message, type = 'success') {
        const toastMessage = toast.querySelector('.toast-message');
        const toastIcon = toast.querySelector('.toast-icon');
        const toastTitle = toast.querySelector('.toast-title');

        // Set message
        toastMessage.textContent = message;

        // Set type and icon
        toast.className = 'toast';
        switch (type) {
            case 'success':
                toast.classList.add('toast-success');
                toastIcon.className = 'fas fa-check-circle toast-icon';
                toastTitle.textContent = 'Succès';
                break;
            case 'error':
                toast.classList.add('toast-error');
                toastIcon.className = 'fas fa-exclamation-circle toast-icon';
                toastTitle.textContent = 'Erreur';
                break;
            case 'warning':
                toast.classList.add('toast-warning');
                toastIcon.className = 'fas fa-exclamation-triangle toast-icon';
                toastTitle.textContent = 'Attention';
                break;
            case 'info':
                toast.classList.add('toast-info');
                toastIcon.className = 'fas fa-info-circle toast-icon';
                toastTitle.textContent = 'Information';
                break;
        }

        // Show toast
        toast.classList.add('show');

        // Auto hide after 5 seconds
        setTimeout(() => {
            toast.classList.remove('show');
        }, 5000);
    }

    // Close toast manually
    closeToast.addEventListener('click', function () {
        toast.classList.remove('show');
    });

    // Initialize member actions
    setupMemberActions();

    // Add CSS for animations and context menu
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        
        .context-menu {
            background: var(--white);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-lg);
            padding: 0.5rem 0;
            min-width: 180px;
            border: 1px solid var(--gray-200);
        }
        
        .context-menu-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            font-size: 0.9rem;
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .context-menu-item:hover {
            background: var(--gray-50);
        }
        
        .context-menu-item-danger {
            color: var(--warning);
        }
        
        .context-menu-item-danger:hover {
            background: var(--warning-light);
        }
        
        .toast-error {
            border-left: 4px solid var(--warning);
        }
        
        .toast-warning {
            border-left: 4px solid #f9c74f;
        }
        
        .toast-info {
            border-left: 4px solid var(--admin-primary);
        }
        
        .toast-error .toast-icon {
            color: var(--warning);
        }
        
        .toast-warning .toast-icon {
            color: #f9c74f;
        }
        
        .toast-info .toast-icon {
            color: var(--admin-primary);
        }
    `;
    document.head.appendChild(style);

    // Add initial fade-in animation to existing cards
    memberCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'all 0.5s ease';

        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Update initial statistics
    updateStatistics();
});
