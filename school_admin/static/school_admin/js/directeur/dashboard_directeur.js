

document.addEventListener('DOMContentLoaded', function () {
    // Toggle sidebar on mobile
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function () {
            sidebar.classList.toggle('active');
        });
    }

    // Toggle dropdown menus
    const dropdownToggles = document.querySelectorAll('.nav-dropdown-toggle');

    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', function () {
            const parent = this.closest('.nav-dropdown');
            parent.classList.toggle('active');
        });
    });

    // Toggle more actions on cards if present
    const cardActionToggles = document.querySelectorAll('.card-action-toggle');

    cardActionToggles.forEach(toggle => {
        toggle.addEventListener('click', function () {
            const actionsMenu = this.nextElementSibling;
            actionsMenu.classList.toggle('show');

            // Close other open menus
            cardActionToggles.forEach(otherToggle => {
                if (otherToggle !== toggle) {
                    const otherMenu = otherToggle.nextElementSibling;
                    if (otherMenu.classList.contains('show')) {
                        otherMenu.classList.remove('show');
                    }
                }
            });

            // Close when clicking outside
            document.addEventListener('click', function closeMenus(e) {
                if (!e.target.closest('.card-actions')) {
                    actionsMenu.classList.remove('show');
                    document.removeEventListener('click', closeMenus);
                }
            });
        });
    });
});