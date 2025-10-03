
document.addEventListener('DOMContentLoaded', function () {
    // Elements
    const createBtn = document.getElementById('createAnnouncementBtn')
    const modal = document.getElementById('announcementModal')
    const closeModal = document.getElementById('closeModal')
    const announcementForm = document.getElementById('announcementForm')
    const saveDraftBtn = document.getElementById('saveDraft')
    const publishBtn = document.getElementById('publishAnnouncementsBtn')
    const statusSelect = document.querySelector('[name="status"]')
    const scheduledDate = document.querySelector('.scheduled-date')
    const toast = document.getElementById('toastNotification')
    const closeToast = document.getElementById('closeToast')
    const applyFiltersBtn = document.getElementById('applyFilters')
    const resetFiltersBtn = document.getElementById('resetFilters')
    const searchInput = document.getElementById('searchInput')
    const filtersToggle = document.getElementById('filtersToggle')

    // Show modal
    createBtn.addEventListener('click', function () {
        modal.classList.add('active')
    })

    // Close modal
    closeModal.addEventListener('click', function () {
        modal.classList.remove('active')
    })

    // Close modal when clicking outside
    modal.addEventListener('click', function (e) {
        if (e.target === modal) {
            modal.classList.remove('active')
        }
    })

    // Handle status change
    const statusSelects = document.querySelectorAll('[name="status"]')
    statusSelects.forEach((select) => {
        select.addEventListener('change', function () {
            if (this.value === 'scheduled') {
                scheduledDate.style.display = 'block'
            } else {
                scheduledDate.style.display = 'none'
            }
        })
    })

    // Save draft
    saveDraftBtn.addEventListener('click', function (e) {
        e.preventDefault()
        showToast("L'annonce a été enregistrée en brouillon.", 'success')
        modal.classList.remove('active')
    })

    // Publish announcement
    document.getElementById('publishAnnouncement').addEventListener('click', function (e) {
        e.preventDefault()
        showToast("L'annonce a été publiée avec succès !", 'success')
        modal.classList.remove('active')

        // In a real app, you would submit the form data to the server here
        // For demo purposes, we'll just show the toast notification
    })

    // Close toast
    closeToast.addEventListener('click', function () {
        toast.classList.remove('show')
    })

    // Show toast function
    function showToast(message, type = 'success') {
        const toast = document.getElementById('toastNotification')
        const toastMessage = toast.querySelector('.toast-message')
        const toastIcon = toast.querySelector('.toast-icon')

        // Set message
        toastMessage.textContent = message

        // Set type
        toast.className = 'toast'
        if (type === 'success') {
            toast.classList.add('toast-success')
            toastIcon.className = 'fas fa-check-circle toast-icon'
        } else {
            toast.classList.add('toast-error')
            toastIcon.className = 'fas fa-exclamation-circle toast-icon'
        }

        // Show toast
        toast.classList.add('show')

        // Hide after 5 seconds
        setTimeout(() => {
            toast.classList.remove('show')
        }, 5000)
    }

    // Apply filters
    applyFiltersBtn.addEventListener('click', function () {
        const searchTerm = searchInput.value.toLowerCase()
        const status = document.querySelector('[name="status"]:checked').id.replace('status-', '')
        const type = document.querySelector('[name="type"]:checked').id.replace('type-', '')

        // In a real app, you would filter the announcements based on these criteria
        // For demo purposes, we'll just show a toast notification
        showToast('Filtres appliqués avec succès', 'success')
    })

    // Reset filters
    resetFiltersBtn.addEventListener('click', function () {
        // Reset all filters to default values
        document.querySelectorAll('[name="status"]').forEach((radio) => {
            if (radio.id === 'status-all') radio.checked = true
        })

        document.querySelectorAll('[name="type"]').forEach((radio) => {
            if (radio.id === 'type-all') radio.checked = true
        })

        document.querySelectorAll('[name="period"]').forEach((radio) => {
            if (radio.id === 'period-all') radio.checked = true
        })

        document.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
            checkbox.checked = false
        })

        searchInput.value = ''
        document.getElementById('startDate').value = ''
        document.getElementById('endDate').value = ''

        showToast('Filtres réinitialisés', 'success')
    })

    // Search functionality
    searchInput.addEventListener('input', function () {
        const searchTerm = this.value.toLowerCase()
        const announcements = document.querySelectorAll('.announcement-card')

        announcements.forEach((announcement) => {
            const title = announcement.querySelector('.announcement-title').textContent.toLowerCase()
            const content = announcement.querySelector('.announcement-content').textContent.toLowerCase()

            if (title.includes(searchTerm) || content.includes(searchTerm)) {
                announcement.style.display = 'block'
                announcement.style.animation = 'fadeIn 0.5s ease forwards'
            } else {
                announcement.style.display = 'none'
            }
        })
    })

    // Toggle filters panel on mobile
    filtersToggle.addEventListener('click', function () {
        const filtersPanel = document.querySelector('.filters-panel')
        if (window.innerWidth <= 992) {
            filtersPanel.style.display = filtersPanel.style.display === 'none' ? 'block' : 'none'
        }
    })

    // Target selection functionality
    const targetTags = document.querySelectorAll('.target-tag')
    targetTags.forEach((tag) => {
        tag.addEventListener('click', function () {
            // If this is in the "all establishments" section
            if (this.parentElement.parentElement.classList.contains('target-selection') && this.parentElement.parentElement.querySelector('.target-title').textContent === 'Tous les établissements') {
                // Remove active class from all tags in this section
                const tagsInSection = this.parentElement.querySelectorAll('.target-tag')
                tagsInSection.forEach((t) => t.classList.remove('active'))
                // Add active class to clicked tag
                this.classList.add('active')
            } else {
                // Toggle active class for role selection
                this.classList.toggle('active')
            }
        })
    })

    // Rich text editor functionality
    const editorBtns = document.querySelectorAll('.editor-btn')
    const editorContent = document.querySelector('.editor-content')

    editorBtns.forEach((btn) => {
        btn.addEventListener('click', function () {
            const command = this.title.toLowerCase()

            // Focus the editor
            editorContent.focus()

            // Execute the command
            if (command === 'gras') {
                document.execCommand('bold', false, null)
            } else if (command === 'italique') {
                document.execCommand('italic', false, null)
            } else if (command === 'souligné') {
                document.execCommand('underline', false, null)
            } else if (command === 'liste à puces') {
                document.execCommand('insertUnorderedList', false, null)
            } else if (command === 'liste numérotée') {
                document.execCommand('insertOrderedList', false, null)
            } else if (command === 'lien') {
                const url = prompt("Entrez l'URL du lien:")
                if (url) {
                    document.execCommand('createLink', false, url)
                }
            } else if (command === 'image') {
                const url = prompt("Entrez l'URL de l'image:")
                if (url) {
                    document.execCommand('insertImage', false, url)
                }
            }
        })
    })

    // Announcement actions
    const announcementActionBtns = document.querySelectorAll('.announcement-action-btn')
    announcementActionBtns.forEach((btn) => {
        btn.addEventListener('click', function () {
            const icon = this.querySelector('i')
            const announcementCard = this.closest('.announcement-card')
            const announcementTitle = announcementCard.querySelector('.announcement-title').textContent

            if (icon.classList.contains('fa-edit')) {
                // Open modal in edit mode
                modal.classList.add('active')
                // In a real app, you would populate the form with the announcement data
                document.querySelector('.modal-title').textContent = "Modifier l'annonce"
            } else if (icon.classList.contains('fa-copy')) {
                showToast(`L'annonce "${announcementTitle}" a été dupliquée.`, 'success')
            } else if (icon.classList.contains('fa-trash')) {
                if (confirm(`Êtes-vous sûr de vouloir supprimer l'annonce "${announcementTitle}" ?`)) {
                    // Animate deletion
                    announcementCard.style.opacity = '0'
                    announcementCard.style.transform = 'translateX(100px)'
                    setTimeout(() => {
                        announcementCard.remove()
                        showToast("L'annonce a été supprimée avec succès.", 'success')
                    }, 300)
                }
            }
        })
    })

    // Add fade-in animation to elements
    const fadeElements = document.querySelectorAll('.fade-in')
    fadeElements.forEach((element, index) => {
        element.style.opacity = '0'
        element.style.transform = 'translateY(20px)'
        element.style.transition = 'opacity 0.5s ease, transform 0.5s ease'

        // Staggered animation
        setTimeout(() => {
            element.style.opacity = '1'
            element.style.transform = 'translateY(0)'
        }, 100 * index)
    })
})
