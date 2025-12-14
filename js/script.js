// Navigation mobile toggle
const menuToggle = document.getElementById('menuToggle');
const navMenu = document.getElementById('navMenu');

if (menuToggle && navMenu) {
    menuToggle.addEventListener('click', () => {
        navMenu.classList.toggle('active');
        
        // Animation du menu hamburger
        const spans = menuToggle.querySelectorAll('span');
        if (navMenu.classList.contains('active')) {
            spans[0].style.transform = 'rotate(45deg) translateY(8px)';
            spans[1].style.opacity = '0';
            spans[2].style.transform = 'rotate(-45deg) translateY(-8px)';
        } else {
            spans[0].style.transform = 'none';
            spans[1].style.opacity = '1';
            spans[2].style.transform = 'none';
        }
    });

    // Fermer le menu au clic sur un lien
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            navMenu.classList.remove('active');
            const spans = menuToggle.querySelectorAll('span');
            spans[0].style.transform = 'none';
            spans[1].style.opacity = '1';
            spans[2].style.transform = 'none';
        });
    });
}

// Smooth scroll pour les liens de navigation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            const headerOffset = 80;
            const elementPosition = target.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }
    });
});

// Header scroll effect
const header = document.getElementById('header');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;
    
    if (currentScroll > 100) {
        header.style.background = 'rgba(255, 255, 255, 0.15)';
        header.style.backdropFilter = 'blur(20px)';
        header.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.08)';
    } else {
        header.style.background = 'rgba(255, 255, 255, 0.1)';
        header.style.backdropFilter = 'blur(20px)';
        header.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.06)';
    }
    
    lastScroll = currentScroll;
});

// Intersection Observer pour les animations au scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Observer tous les éléments avec data-aos
document.addEventListener('DOMContentLoaded', () => {
    const animatedElements = document.querySelectorAll('[data-aos]');
    
    animatedElements.forEach(el => {
        // Initialiser l'état invisible
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
        
        // Observer l'élément
        observer.observe(el);
    });
});

// Animation d'apparition progressive pour les cartes
const cardObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry, index) => {
        if (entry.isIntersecting) {
            setTimeout(() => {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }, index * 100);
            cardObserver.unobserve(entry.target);
        }
    });
}, {
    threshold: 0.1,
    rootMargin: '0px 0px -30px 0px'
});

// Observer les cartes dans les grilles
document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('.glass-card');
    
    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
        cardObserver.observe(card);
    });
});

// Effet parallaxe léger pour la section hero
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const hero = document.querySelector('.hero');
    if (hero) {
        const heroContent = hero.querySelector('.hero-content');
        if (heroContent && scrolled < window.innerHeight) {
            heroContent.style.transform = `translateY(${scrolled * 0.5}px)`;
            heroContent.style.opacity = 1 - (scrolled / window.innerHeight) * 0.5;
        }
    }
});

// Animation au survol des cartes avec effet de scale
document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('.glass-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px) scale(1.02)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
});

// Compteur animé pour les statistiques (si nécessaire)
function animateCounter(element, target, duration = 2000) {
    let start = 0;
    const increment = target / (duration / 16);
    
    const timer = setInterval(() => {
        start += increment;
        if (start >= target) {
            element.textContent = target;
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(start);
        }
    }, 16);
}

// Fonction pour afficher/masquer des éléments (exemple pour FAQ ou détails)
function toggleElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        if (element.style.display === 'none' || !element.style.display) {
            element.style.display = 'block';
            element.style.opacity = '0';
            element.style.transform = 'translateY(-10px)';
            setTimeout(() => {
                element.style.opacity = '1';
                element.style.transform = 'translateY(0)';
            }, 10);
        } else {
            element.style.opacity = '0';
            element.style.transform = 'translateY(-10px)';
            setTimeout(() => {
                element.style.display = 'none';
            }, 300);
        }
    }
}

// Gestion du formulaire de contact (sans validation JS, juste animation)
const contactForm = document.querySelector('.contact-form form');
if (contactForm) {
    contactForm.addEventListener('submit', function(e) {
        // Pas de validation JS, la validation sera faite côté Django
        // Juste une animation de soumission
        const submitButton = this.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.style.opacity = '0.7';
            submitButton.textContent = 'Envoi en cours...';
            submitButton.disabled = true;
        }
    });
}

// Lazy loading des images (amélioration des performances)
if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    imageObserver.unobserve(img);
                }
            }
        });
    });

    document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
    });
}

// Animation de typing pour le titre hero (optionnel)
function typeWriter(element, text, speed = 100) {
    let i = 0;
    element.textContent = '';
    
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }
    
    type();
}

// Détection de la réduction de mouvement (accessibilité)
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

if (prefersReducedMotion.matches) {
    // Désactiver les animations si l'utilisateur préfère moins de mouvement
    document.querySelectorAll('[data-aos]').forEach(el => {
        el.style.transition = 'none';
        el.style.opacity = '1';
        el.style.transform = 'none';
    });
}

// Gestion du scroll actif dans la navigation
window.addEventListener('scroll', () => {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');
    
    let current = '';
    
    sections.forEach(section => {
        const sectionTop = section.offsetTop;
        const sectionHeight = section.clientHeight;
        if (window.pageYOffset >= sectionTop - 100) {
            current = section.getAttribute('id');
        }
    });
    
    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${current}`) {
            link.classList.add('active');
        }
    });
});

// Gestion des modals pour les fonctionnalités
document.addEventListener('DOMContentLoaded', () => {
    // Ajouter une classe pour les animations CSS
    document.body.classList.add('loaded');
    
    // Animation d'entrée pour le hero
    const heroContent = document.querySelector('.hero-content');
    if (heroContent) {
        setTimeout(() => {
            heroContent.style.opacity = '1';
            heroContent.style.transform = 'translateY(0)';
        }, 100);
    }

    // Gestion des boutons "Voir toutes les fonctionnalités"
    const viewAllButtons = document.querySelectorAll('.btn-view-all');
    viewAllButtons.forEach(button => {
        button.addEventListener('click', function() {
            const modalId = this.getAttribute('data-modal');
            const modal = document.getElementById(`modal-${modalId}`);
            if (modal) {
                openModal(modal);
            }
        });
    });

    // Gestion de la fermeture des modals
    const closeButtons = document.querySelectorAll('.modal-close');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            const modal = this.closest('.modal-fullscreen');
            if (modal) {
                closeModal(modal);
            }
        });
    });

    // Fermer le modal en cliquant sur le fond
    const modals = document.querySelectorAll('.modal-fullscreen');
    modals.forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal(this);
            }
        });
    });

    // Fermer le modal avec la touche Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const activeModal = document.querySelector('.modal-fullscreen.active');
            if (activeModal) {
                closeModal(activeModal);
            }
        }
    });
});

// Fonction pour ouvrir un modal
function openModal(modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // Animation d'entrée
    setTimeout(() => {
        modal.style.opacity = '1';
    }, 10);
}

// Fonction pour fermer un modal
function closeModal(modal) {
    modal.style.opacity = '0';
    setTimeout(() => {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }, 300);
}

