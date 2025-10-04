/**
 * Dashboard Administrateur d'Établissement - JavaScript
 * Fonctionnalités interactives pour le tableau de bord
 */

document.addEventListener('DOMContentLoaded', function () {
    // ===== ANIMATIONS D'ENTRÉE =====
    const animateOnScroll = () => {
        const elements = document.querySelectorAll('.indicator-card, .structure-card, .activity-card, .shortcut-card');

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry, index) => {
                if (entry.isIntersecting) {
                    setTimeout(() => {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }, index * 100);
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        elements.forEach(element => {
            element.style.opacity = '0';
            element.style.transform = 'translateY(30px)';
            element.style.transition = 'all 0.6s ease';
            observer.observe(element);
        });
    };

    // ===== COMPTEURS ANIMÉS =====
    const animateCounters = () => {
        const counters = document.querySelectorAll('.indicator-value, .stat-value');

        const animateCounter = (element) => {
            const target = parseInt(element.textContent.replace(/,/g, ''));
            const duration = 2000;
            const increment = target / (duration / 16);
            let current = 0;

            const timer = setInterval(() => {
                current += increment;
                if (current >= target) {
                    current = target;
                    clearInterval(timer);
                }
                element.textContent = Math.floor(current).toLocaleString();
            }, 16);
        };

        const counterObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    animateCounter(entry.target);
                    counterObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        counters.forEach(counter => {
            counterObserver.observe(counter);
        });
    };

    // ===== EFFETS DE HOVER AVANCÉS =====
    const initHoverEffects = () => {
        const cards = document.querySelectorAll('.indicator-card, .structure-card, .activity-card, .shortcut-card');

        cards.forEach(card => {
            card.addEventListener('mouseenter', function () {
                this.style.transform = 'translateY(-8px) scale(1.02)';
                this.style.boxShadow = '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)';

                // Effet de brillance
                const shine = document.createElement('div');
                shine.style.position = 'absolute';
                shine.style.top = '0';
                shine.style.left = '-100%';
                shine.style.width = '100%';
                shine.style.height = '100%';
                shine.style.background = 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent)';
                shine.style.transition = 'left 0.5s ease';
                shine.style.pointerEvents = 'none';
                this.style.position = 'relative';
                this.style.overflow = 'hidden';
                this.appendChild(shine);

                setTimeout(() => {
                    shine.style.left = '100%';
                }, 10);

                setTimeout(() => {
                    if (shine.parentNode) {
                        shine.parentNode.removeChild(shine);
                    }
                }, 500);
            });

            card.addEventListener('mouseleave', function () {
                this.style.transform = 'translateY(0) scale(1)';
                this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.08)';
            });
        });
    };

    // ===== GESTION DES NOTIFICATIONS =====
    const initNotifications = () => {
        const alertCard = document.querySelector('.indicator-card.alert');
        if (alertCard) {
            // Animation de pulsation pour les alertes
            setInterval(() => {
                alertCard.style.animation = 'pulse 1.5s ease-in-out';
                setTimeout(() => {
                    alertCard.style.animation = '';
                }, 1500);
            }, 5000);
        }
    };

    // ===== RACCOURCIS CLAVIER =====
    const initKeyboardShortcuts = () => {
        document.addEventListener('keydown', function (e) {
            // Ctrl + 1 : Gestion des Classes
            if (e.ctrlKey && e.key === '1') {
                e.preventDefault();
                const classesCard = document.querySelector('.shortcut-card:nth-child(1)');
                if (classesCard) classesCard.click();
            }

            // Ctrl + 2 : Gestion des Enseignants
            if (e.ctrlKey && e.key === '2') {
                e.preventDefault();
                const teachersCard = document.querySelector('.shortcut-card:nth-child(2)');
                if (teachersCard) teachersCard.click();
            }

            // Ctrl + 3 : Gestion des Matières
            if (e.ctrlKey && e.key === '3') {
                e.preventDefault();
                const subjectsCard = document.querySelector('.shortcut-card:nth-child(3)');
                if (subjectsCard) subjectsCard.click();
            }

            // Ctrl + 4 : Codes d'accès
            if (e.ctrlKey && e.key === '4') {
                e.preventDefault();
                const accessCard = document.querySelector('.shortcut-card:nth-child(4)');
                if (accessCard) accessCard.click();
            }
        });
    };

    // ===== GESTION DES DONNÉES TEMPORELLES =====
    const updateTimeStamps = () => {
        const timeElements = document.querySelectorAll('.activity-time');

        timeElements.forEach(element => {
            const timeText = element.textContent;
            if (timeText.includes('Il y a')) {
                // Mise à jour des timestamps (simulation)
                setInterval(() => {
                    const randomMinutes = Math.floor(Math.random() * 60);
                    element.textContent = `Il y a ${randomMinutes} minutes`;
                }, 60000);
            }
        });
    };

    // ===== EFFETS DE PARTICULES =====
    const initParticleEffect = () => {
        const createParticle = () => {
            const particle = document.createElement('div');
            particle.style.position = 'fixed';
            particle.style.width = '4px';
            particle.style.height = '4px';
            particle.style.background = 'rgba(67, 97, 238, 0.6)';
            particle.style.borderRadius = '50%';
            particle.style.pointerEvents = 'none';
            particle.style.zIndex = '1000';
            particle.style.left = Math.random() * window.innerWidth + 'px';
            particle.style.top = window.innerHeight + 'px';
            particle.style.animation = 'floatUp 3s linear forwards';

            document.body.appendChild(particle);

            setTimeout(() => {
                if (particle.parentNode) {
                    particle.parentNode.removeChild(particle);
                }
            }, 3000);
        };

        // Créer des particules occasionnellement
        setInterval(createParticle, 5000);
    };

    // ===== GESTION DES THÈMES =====
    const initThemeToggle = () => {
        const themeToggle = document.createElement('button');
        themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        themeToggle.style.position = 'fixed';
        themeToggle.style.top = '20px';
        themeToggle.style.right = '20px';
        themeToggle.style.width = '50px';
        themeToggle.style.height = '50px';
        themeToggle.style.borderRadius = '50%';
        themeToggle.style.border = 'none';
        themeToggle.style.background = 'var(--primary)';
        themeToggle.style.color = 'white';
        themeToggle.style.cursor = 'pointer';
        themeToggle.style.zIndex = '1000';
        themeToggle.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
        themeToggle.style.transition = 'all 0.3s ease';

        themeToggle.addEventListener('click', function () {
            document.body.classList.toggle('dark-theme');
            const isDark = document.body.classList.contains('dark-theme');
            this.innerHTML = isDark ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
        });

        document.body.appendChild(themeToggle);
    };

    // ===== ANIMATION DE CHARGEMENT =====
    const showLoadingAnimation = () => {
        const loadingOverlay = document.createElement('div');
        loadingOverlay.style.position = 'fixed';
        loadingOverlay.style.top = '0';
        loadingOverlay.style.left = '0';
        loadingOverlay.style.width = '100%';
        loadingOverlay.style.height = '100%';
        loadingOverlay.style.background = 'rgba(255, 255, 255, 0.9)';
        loadingOverlay.style.display = 'flex';
        loadingOverlay.style.alignItems = 'center';
        loadingOverlay.style.justifyContent = 'center';
        loadingOverlay.style.zIndex = '9999';
        loadingOverlay.innerHTML = `
            <div style="text-align: center;">
                <div style="width: 50px; height: 50px; border: 4px solid #f3f3f3; border-top: 4px solid var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px;"></div>
                <p style="color: var(--text-primary); font-weight: 500;">Chargement du tableau de bord...</p>
            </div>
        `;

        document.body.appendChild(loadingOverlay);

        setTimeout(() => {
            loadingOverlay.style.opacity = '0';
            loadingOverlay.style.transition = 'opacity 0.5s ease';
            setTimeout(() => {
                if (loadingOverlay.parentNode) {
                    loadingOverlay.parentNode.removeChild(loadingOverlay);
                }
            }, 500);
        }, 1000);
    };

    // ===== CSS ANIMATIONS =====
    const addCSSAnimations = () => {
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0% { box-shadow: 0 0 0 0 rgba(67, 97, 238, 0.4); }
                70% { box-shadow: 0 0 0 10px rgba(67, 97, 238, 0); }
                100% { box-shadow: 0 0 0 0 rgba(67, 97, 238, 0); }
            }
            
            @keyframes floatUp {
                0% { transform: translateY(0) rotate(0deg); opacity: 1; }
                100% { transform: translateY(-100vh) rotate(360deg); opacity: 0; }
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .dark-theme {
                --text-primary: #f9fafb;
                --text-secondary: #d1d5db;
                --white: #1f2937;
                --gray-50: #111827;
                --gray-100: #1f2937;
                --gray-200: #374151;
            }
        `;
        document.head.appendChild(style);
    };

    // ===== INITIALISATION =====
    const init = () => {
        showLoadingAnimation();
        addCSSAnimations();

        setTimeout(() => {
            animateOnScroll();
            animateCounters();
            initHoverEffects();
            initNotifications();
            initKeyboardShortcuts();
            updateTimeStamps();
            initParticleEffect();
            initThemeToggle();
        }, 1000);
    };

    // Démarrer l'application
    init();
});
