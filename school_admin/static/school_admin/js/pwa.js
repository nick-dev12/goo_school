// Script PWA pour Aria - Enregistrement et gestion du Service Worker

// Vérifier si le navigateur supporte les Service Workers
if ('serviceWorker' in navigator) {
  let registration;

  // Enregistrer le Service Worker
  window.addEventListener('load', () => {
    registerServiceWorker();
  });

  // Fonction d'enregistrement du Service Worker
  async function registerServiceWorker() {
    try {
      registration = await navigator.serviceWorker.register('/service-worker.js', {
        scope: '/'
      });

      console.log('[PWA] Service Worker enregistré avec succès:', registration.scope);

      // Vérifier les mises à jour périodiquement
      setInterval(() => {
        registration.update();
      }, 60000); // Vérifier toutes les minutes

      // Gérer les mises à jour du Service Worker (notification désactivée)
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;

        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // Nouvelle version disponible - mise à jour automatique silencieuse
            // La notification a été désactivée
            console.log('[PWA] Nouvelle version disponible, mise à jour automatique');
          }
        });
      });

      // Gérer les messages du Service Worker
      navigator.serviceWorker.addEventListener('message', (event) => {
        console.log('[PWA] Message reçu du Service Worker:', event.data);

        if (event.data && event.data.type === 'CACHE_UPDATED') {
          console.log('[PWA] Cache mis à jour');
        }
      });

      // Mettre en cache automatiquement toutes les pages visitées
      setupAutoCache();

    } catch (error) {
      console.error('[PWA] Erreur lors de l\'enregistrement du Service Worker:', error);
    }
  }

  // Fonction de notification de mise à jour désactivée
  // La notification automatique a été supprimée pour éviter les interruptions utilisateur
  // Les mises à jour se font automatiquement en arrière-plan

  // Détecter si l'application est installée
  window.addEventListener('beforeinstallprompt', (e) => {
    // Empêcher l'affichage automatique du prompt
    e.preventDefault();

    // Stocker l'événement pour l'utiliser plus tard
    // Les boutons d'installation sont gérés dans les headers spécifiques (élève, directeur, enseignant)
    window.deferredPrompt = e;

    console.log('[PWA] Prompt d\'installation disponible, stocké pour utilisation dans les headers');
  });

  // Supprimer tous les boutons PWA automatiques non autorisés
  function removeAutoPWAButtons() {
    // Supprimer les boutons avec des IDs suspects
    const autoButtonIds = [
      'pwa-install-button',
      'pwa-update-notification',
      'pwa-update-btn',
      'pwa-dismiss-btn'
    ];

    autoButtonIds.forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.remove();
        console.log('[PWA] Bouton automatique supprimé:', id);
      }
    });

    // Supprimer les boutons avec des textes suspects qui ne sont pas nos boutons manuels
    const allButtons = document.querySelectorAll('button, a[role="button"]');
    allButtons.forEach(btn => {
      const text = (btn.textContent || btn.innerText || '').toLowerCase();
      const id = btn.id;

      // Ignorer nos boutons manuels dans les headers
      if (id === 'pwa-install-btn') {
        return;
      }

      // Supprimer les boutons avec des textes liés à l'installation/mise à jour PWA
      if (
        (text.includes('installer l\'application') ||
          text.includes('installer') && text.includes('application')) ||
        (text.includes('nouvelle version') && text.includes('disponible')) ||
        (text.includes('mettre à jour') && (text.includes('application') || text.includes('version')))
      ) {
        // Vérifier si c'est un bouton flottant (position fixed)
        const style = window.getComputedStyle(btn);
        if (style.position === 'fixed' || btn.closest('[style*="position: fixed"]')) {
          btn.remove();
          console.log('[PWA] Bouton PWA automatique supprimé:', text);
        }
      }
    });

    // Supprimer les notifications de mise à jour
    const notifications = document.querySelectorAll('[id*="pwa-update"], [class*="pwa-update"], [id*="update-notification"]');
    notifications.forEach(notif => {
      const text = (notif.textContent || notif.innerText || '').toLowerCase();
      if (text.includes('nouvelle version') || text.includes('mise à jour') && text.includes('disponible')) {
        notif.remove();
        console.log('[PWA] Notification de mise à jour supprimée');
      }
    });
  }

  // Exécuter immédiatement et de manière répétée
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      removeAutoPWAButtons();
      // Observer les changements du DOM pour supprimer les nouveaux boutons
      const observer = new MutationObserver(() => {
        removeAutoPWAButtons();
      });
      observer.observe(document.body, {
        childList: true,
        subtree: true
      });
    });
  } else {
    removeAutoPWAButtons();
    // Observer les changements du DOM
    const observer = new MutationObserver(() => {
      removeAutoPWAButtons();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  // Détecter si l'application est déjà installée
  if (window.matchMedia('(display-mode: standalone)').matches) {
    console.log('[PWA] Application installée et en mode standalone');
    document.documentElement.setAttribute('data-pwa-installed', 'true');
  }

  // Gérer les erreurs du Service Worker
  navigator.serviceWorker.addEventListener('error', (error) => {
    console.error('[PWA] Erreur du Service Worker:', error);
  });

} else {
  console.warn('[PWA] Les Service Workers ne sont pas supportés par ce navigateur');
}

// Fonction utilitaire pour mettre à jour le cache manuellement
window.updatePWACache = async function (urls) {
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: 'CACHE_URLS',
      urls: urls
    });
  }
};

// Fonction pour mettre en cache une page spécifique
window.cachePage = function (url) {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: 'CACHE_PAGE',
      url: url
    });
    console.log('[PWA] Page mise en cache manuellement:', url);
  }
};

// Fonction pour mettre en cache automatiquement les pages visitées
function setupAutoCache() {
  // Mettre en cache la page actuelle après le chargement
  if (document.readyState === 'complete') {
    cacheCurrentPage();
  } else {
    window.addEventListener('load', () => {
      cacheCurrentPage();
    });
  }

  // Mettre en cache la page actuelle immédiatement si elle est déjà chargée
  if (document.readyState === 'interactive' || document.readyState === 'complete') {
    setTimeout(() => cacheCurrentPage(), 1000);
  }

  // Mettre en cache les pages lors des clics sur les liens
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (link && link.href && link.href.startsWith(window.location.origin)) {
      // Ignorer les liens avec des fragments ou des actions spéciales
      if (!link.href.includes('#') &&
        !link.href.includes('javascript:') &&
        !link.href.includes('mailto:') &&
        !link.href.includes('tel:')) {
        // Précharger et mettre en cache la page cible
        preloadAndCachePage(link.href);
      }
    }
  });

  // Mettre en cache les pages lors des soumissions de formulaire (GET)
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (form.method && form.method.toLowerCase() === 'get' && form.action) {
      const url = new URL(form.action, window.location.origin);
      // Ajouter les paramètres du formulaire
      const formData = new FormData(form);
      formData.forEach((value, key) => {
        url.searchParams.append(key, value);
      });
      preloadAndCachePage(url.toString());
    }
  });

  // Mettre en cache lors de la navigation (popstate pour le bouton retour)
  window.addEventListener('popstate', () => {
    setTimeout(() => cacheCurrentPage(), 500);
  });

  // Mettre en cache toutes les pages visitées via l'historique
  const originalPushState = history.pushState;
  history.pushState = function (...args) {
    originalPushState.apply(history, args);
    setTimeout(() => cacheCurrentPage(), 500);
  };

  const originalReplaceState = history.replaceState;
  history.replaceState = function (...args) {
    originalReplaceState.apply(history, args);
    setTimeout(() => cacheCurrentPage(), 500);
  };
}

// Mettre en cache la page actuelle
function cacheCurrentPage() {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    const currentUrl = window.location.href;
    navigator.serviceWorker.controller.postMessage({
      type: 'CACHE_PAGE',
      url: currentUrl
    });
    console.log('[PWA] Page actuelle mise en cache:', currentUrl);
  }
}

// Précharger et mettre en cache une page
function preloadAndCachePage(url) {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    // Ne pas mettre en cache les URLs avec des fragments ou des actions
    if (url.includes('#') || url.includes('javascript:') || url.includes('mailto:') || url.includes('tel:')) {
      return;
    }

    // Vérifier que c'est une URL de la même origine
    try {
      const urlObj = new URL(url);
      if (urlObj.origin !== window.location.origin) {
        return;
      }
    } catch (e) {
      return;
    }

    // Envoyer le message au service worker pour mettre en cache
    navigator.serviceWorker.controller.postMessage({
      type: 'CACHE_PAGE',
      url: url
    });
    console.log('[PWA] Page préchargée et mise en cache:', url);
  } else {
    // Si le service worker n'est pas encore prêt, essayer de mettre en cache directement
    fetch(url, { method: 'GET', cache: 'default' }).catch(() => {
      // Ignorer les erreurs silencieusement
    });
  }
}

// Fonction pour obtenir la liste des pages en cache
window.getCachedPages = async function () {
  return new Promise((resolve, reject) => {
    if (!navigator.serviceWorker || !navigator.serviceWorker.controller) {
      resolve([]);
      return;
    }

    const messageChannel = new MessageChannel();
    messageChannel.port1.onmessage = (event) => {
      if (event.data.type === 'CACHED_PAGES') {
        resolve(event.data.pages);
      } else {
        reject(new Error('Réponse inattendue du service worker'));
      }
    };

    navigator.serviceWorker.controller.postMessage(
      { type: 'GET_CACHED_PAGES' },
      [messageChannel.port2]
    );
  });
};

// Fonction pour vérifier la connexion
window.isOnline = function () {
  return navigator.onLine;
};

// Écouter les changements de statut de connexion
window.addEventListener('online', () => {
  console.log('[PWA] Connexion rétablie');
  // Optionnel : afficher une notification
  if (typeof showNotification === 'function') {
    showNotification('Connexion rétablie', 'Vous êtes de nouveau en ligne');
  }
});

window.addEventListener('offline', () => {
  console.log('[PWA] Mode hors ligne');
  // Optionnel : afficher une notification
  if (typeof showNotification === 'function') {
    showNotification('Mode hors ligne', 'Certaines fonctionnalités peuvent être limitées');
  }
});

