// Service Worker pour Aria - Plateforme Éducative
// Version du cache - Mis à jour pour le cache complet des pages + FCM
const CACHE_NAME = 'aria-pwa-v1.0.3';
const RUNTIME_CACHE = 'aria-runtime-v1.0.3';
const PAGES_CACHE = 'aria-pages-v1.0.3';

// Import Firebase scripts pour les notifications push
importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging-compat.js');

// Configuration Firebase
const firebaseConfig = {
  apiKey: "AIzaSyCSvm0VNdvnLqdIFPdDs4DPYDjHvDsO4_Q",
  authDomain: "gestion-scolaire-6945a.firebaseapp.com",
  projectId: "gestion-scolaire-6945a",
  storageBucket: "gestion-scolaire-6945a.firebasestorage.app",
  messagingSenderId: "983006440407",
  appId: "1:983006440407:web:8cbfc916f43b745a7e7992",
  measurementId: "G-1SHG5PC5T7"
};

// Initialiser Firebase
try {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();
  
  // Gérer les notifications en arrière-plan
  messaging.onBackgroundMessage((payload) => {
    console.log('[Service Worker] Message FCM reçu en arrière-plan', payload);
    
    const notificationTitle = payload.notification?.title || 'Nouvelle notification';
    const notificationOptions = {
      body: payload.notification?.body || 'Vous avez une nouvelle notification',
      icon: '/static/school_admin/images/logo.png',
      badge: '/static/school_admin/images/badge.png',
      tag: payload.data?.tag || payload.data?.type || 'general',
      data: payload.data || {},
      requireInteraction: true,
      vibrate: [200, 100, 200],
    };

    return self.registration.showNotification(notificationTitle, notificationOptions);
  });
  
  console.log('[Service Worker] Firebase Messaging initialisé');
} catch (error) {
  console.error('[Service Worker] Erreur initialisation Firebase:', error);
}

// Limite de taille du cache (en nombre d'éléments) - Augmenté pour plus de pages
const MAX_CACHE_ITEMS = 500;

// Fichiers à mettre en cache immédiatement (assets critiques)
const STATIC_CACHE_URLS = [
  '/',
  '/static/school_admin/css/header.css',
  '/static/school_admin/css/dashboard.css',
  '/static/school_admin/img/logo.png',
  '/static/school_admin/js/script.js',
];

// Stratégies de cache
const CACHE_STRATEGIES = {
  // Cache First : pour les assets statiques (CSS, JS, images)
  CACHE_FIRST: 'cache-first',
  // Network First : pour les pages HTML et API
  NETWORK_FIRST: 'network-first',
  // Stale While Revalidate : pour les ressources qui peuvent être mises à jour
  STALE_WHILE_REVALIDATE: 'stale-while-revalidate',
};

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installation en cours...');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Mise en cache des fichiers statiques');
        return cache.addAll(STATIC_CACHE_URLS);
      })
      .then(() => {
        console.log('[Service Worker] Installation terminée');
        return self.skipWaiting(); // Activer immédiatement le nouveau service worker
      })
      .catch((error) => {
        console.error('[Service Worker] Erreur lors de l\'installation:', error);
      })
  );
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activation en cours...');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            // Supprimer les anciens caches
            if (cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE && cacheName !== PAGES_CACHE) {
              console.log('[Service Worker] Suppression de l\'ancien cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('[Service Worker] Activation terminée');
        return self.clients.claim(); // Prendre le contrôle de toutes les pages
      })
  );
});

// Interception des requêtes
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorer les requêtes non-GET
  if (request.method !== 'GET') {
    return;
  }

  // Ignorer les requêtes vers l'API Django admin (sauf les pages HTML)
  if (url.pathname.startsWith('/admin/') && !isHTMLRequest(request)) {
    return;
  }

  // Ignorer les requêtes vers les fichiers média (uploadés par les utilisateurs)
  if (url.pathname.startsWith('/media/')) {
    return;
  }

  // Ignorer les requêtes vers des domaines externes
  if (url.origin !== self.location.origin) {
    return;
  }

  // Stratégie selon le type de ressource
  if (isHTMLRequest(request)) {
    // Network First pour les pages HTML - TOUTES les pages visitées seront mises en cache
    event.respondWith(networkFirst(request));
  } else if (isStaticAsset(request.url)) {
    // Cache First pour les assets statiques
    event.respondWith(cacheFirst(request));
  } else {
    // Stale While Revalidate pour les autres ressources
    event.respondWith(staleWhileRevalidate(request));
  }
});

// Vérifier si c'est un asset statique
function isStaticAsset(url) {
  return (
    url.includes('/static/') ||
    url.includes('/staticfiles/') ||
    url.match(/\.(css|js|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot|ico)$/)
  );
}

// Vérifier si c'est une requête HTML
function isHTMLRequest(request) {
  const url = new URL(request.url);
  const acceptHeader = request.headers.get('accept') || '';

  // Vérifier l'en-tête Accept
  if (acceptHeader.includes('text/html')) {
    return true;
  }

  // Vérifier l'extension du fichier
  if (url.pathname.match(/\.(html|htm)$/i)) {
    return true;
  }

  // Vérifier si c'est une route Django (pas de point dans le chemin, sauf à la fin)
  const hasExtension = url.pathname.match(/\.([^/]+)$/);
  const isStaticFile = url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/media/') ||
    url.pathname.startsWith('/admin/static/') ||
    url.pathname.startsWith('/admin/media/');

  // Si c'est la même origine et que ce n'est pas un fichier statique avec extension
  if (url.origin === self.location.origin &&
    !isStaticFile &&
    (!hasExtension || url.pathname.endsWith('/'))) {
    return true;
  }

  // Vérifier les routes Django typiques (pas d'extension, pas de static/media)
  if (url.origin === self.location.origin &&
    !url.pathname.startsWith('/static/') &&
    !url.pathname.startsWith('/media/') &&
    !url.pathname.startsWith('/admin/') &&
    !hasExtension) {
    return true;
  }

  return false;
}

// Stratégie Cache First
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    return cached;
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.error('[Service Worker] Erreur fetch:', error);
    // Retourner une page hors ligne si disponible
    const offlinePage = await cache.match('/');
    if (offlinePage) {
      return offlinePage;
    }
    throw error;
  }
}

// Stratégie Network First avec cache automatique de toutes les pages
async function networkFirst(request) {
  const pagesCache = await caches.open(PAGES_CACHE);

  try {
    // Essayer d'abord le réseau
    const response = await fetch(request);

    // Si la réponse est OK, la mettre en cache (toutes les pages HTML)
    if (response.ok && response.status === 200 && isHTMLRequest(request)) {
      // Cloner la réponse car elle ne peut être utilisée qu'une fois
      const responseToCache = response.clone();

      // Mettre en cache la page immédiatement
      await pagesCache.put(request, responseToCache);
      console.log('[Service Worker] Page mise en cache:', request.url);

      // Limiter la taille du cache si nécessaire (en arrière-plan, non bloquant)
      limitCacheSize(PAGES_CACHE, MAX_CACHE_ITEMS).catch(err => {
        console.error('[Service Worker] Erreur lors de la limitation du cache:', err);
      });
    }

    return response;
  } catch (error) {
    console.log('[Service Worker] Mode hors ligne, recherche dans le cache pour:', request.url);

    // Chercher dans le cache avec l'URL exacte
    let cached = await pagesCache.match(request);
    if (cached) {
      console.log('[Service Worker] Page trouvée dans le cache (URL exacte):', request.url);
      return cached;
    }

    // Essayer de trouver une version sans paramètres de requête
    const urlWithoutParams = new URL(request.url);
    urlWithoutParams.search = '';
    urlWithoutParams.hash = '';
    cached = await pagesCache.match(urlWithoutParams.toString());
    if (cached) {
      console.log('[Service Worker] Page trouvée (sans params):', urlWithoutParams.toString());
      return cached;
    }

    // Essayer de trouver une version avec différents paramètres mais même chemin
    const urlPath = urlWithoutParams.pathname;
    const allCachedKeys = await pagesCache.keys();
    for (const key of allCachedKeys) {
      const keyUrl = new URL(key.url);
      if (keyUrl.pathname === urlPath && keyUrl.origin === urlWithoutParams.origin) {
        cached = await pagesCache.match(key);
        if (cached) {
          console.log('[Service Worker] Page trouvée (même chemin, params différents):', key.url);
          return cached;
        }
      }
    }

    // Si c'est une page HTML et qu'on n'a pas de cache, retourner la page d'accueil
    if (isHTMLRequest(request)) {
      const homePage = await pagesCache.match('/');
      if (homePage) {
        console.log('[Service Worker] Redirection vers la page d\'accueil (hors ligne)');
        return homePage;
      }
    }

    // Retourner une réponse d'erreur hors ligne
    return new Response('Hors ligne - Cette page n\'est pas disponible hors connexion', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
}

// Fonction pour limiter la taille du cache
async function limitCacheSize(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();

  if (keys.length > maxItems) {
    // Supprimer les éléments les plus anciens
    const itemsToDelete = keys.length - maxItems;
    for (let i = 0; i < itemsToDelete; i++) {
      await cache.delete(keys[i]);
      console.log('[Service Worker] Élément supprimé du cache:', keys[i].url);
    }
  }
}

// Stratégie Stale While Revalidate
async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);

  // Lancer la mise à jour en arrière-plan
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => {
    // Ignorer les erreurs de fetch en arrière-plan
  });

  // Retourner le cache immédiatement s'il existe
  if (cached) {
    return cached;
  }

  // Sinon attendre la réponse réseau
  try {
    return await fetchPromise;
  } catch (error) {
    throw error;
  }
}

// Gestion des messages depuis le client
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.addAll(event.data.urls);
      })
    );
  }

  // Message pour mettre en cache une page spécifique
  if (event.data && event.data.type === 'CACHE_PAGE') {
    event.waitUntil(
      fetch(event.data.url, {
        method: 'GET',
        cache: 'no-cache', // Toujours récupérer depuis le réseau pour avoir la dernière version
        credentials: 'same-origin'
      }).then((response) => {
        if (response.ok && response.status === 200) {
          // Cloner la réponse car elle ne peut être utilisée qu'une fois
          const responseToCache = response.clone();
          return caches.open(PAGES_CACHE).then((cache) => {
            return cache.put(event.data.url, responseToCache).then(() => {
              console.log('[Service Worker] Page mise en cache manuellement:', event.data.url);
              // Limiter la taille du cache si nécessaire
              return limitCacheSize(PAGES_CACHE, MAX_CACHE_ITEMS);
            });
          });
        } else {
          console.warn('[Service Worker] Impossible de mettre en cache la page (réponse non OK):', event.data.url);
        }
      }).catch((error) => {
        console.error('[Service Worker] Erreur lors de la mise en cache de la page:', event.data.url, error);
      })
    );
  }

  // Message pour obtenir la liste des pages en cache
  if (event.data && event.data.type === 'GET_CACHED_PAGES') {
    event.waitUntil(
      caches.open(PAGES_CACHE).then((cache) => {
        return cache.keys().then((keys) => {
          event.ports[0].postMessage({
            type: 'CACHED_PAGES',
            pages: keys.map(key => key.url)
          });
        });
      })
    );
  }
});

// Notification de mise à jour disponible
self.addEventListener('updatefound', () => {
  console.log('[Service Worker] Nouvelle version disponible');
});

// ============================================
// GESTION DES NOTIFICATIONS FCM
// ============================================

// Gérer le clic sur la notification
self.addEventListener('notificationclick', (event) => {
  console.log('[Service Worker] Clic sur la notification', event);
  
  event.notification.close();
  
  // Ouvrir l'URL spécifiée ou le dashboard
  const notificationData = event.notification.data || {};
  const urlToOpen = notificationData.url || notificationData.redirect_url || '/eleve/dashboard/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Vérifier si une fenêtre est déjà ouverte
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url.includes(urlToOpen) && 'focus' in client) {
            return client.focus();
          }
        }
        // Ouvrir une nouvelle fenêtre
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

