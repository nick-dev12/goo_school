// Cache limité aux ressources publiques statiques ; aucune page privée persistée.
const STATIC_CACHE = 'aria-static-v2';
const MAX_CACHE_ITEMS = 150;
// Import Firebase scripts pour les notifications push
try {
  importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-app-compat.js');
  importScripts('https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging-compat.js');
} catch (error) {
  // Une panne de Firebase ne doit pas empêcher la purge des anciens caches privés.
  console.warn('[Service Worker] Notifications indisponibles');
}

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


function publicStatic(url) {
  return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

async function purgeOldCaches() {
  for (const name of await caches.keys()) {
    if (name.startsWith('aria-') && name !== STATIC_CACHE) await caches.delete(name);
  }
}

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => {
  event.waitUntil(purgeOldCaches().then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || !publicStatic(new URL(request.url))) return;
  event.respondWith((async () => {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    const policy = response.headers.get('Cache-Control') || '';
    if (response.ok && !/no-store|private/i.test(policy)) {
      await cache.put(request, response.clone());
      const keys = await cache.keys();
      for (const key of keys.slice(0, Math.max(0, keys.length - MAX_CACHE_ITEMS))) {
        await cache.delete(key);
      }
    }
    return response;
  })());
});

self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
  if (event.data?.type === 'CLEAR_CACHE') {
    event.waitUntil(Promise.all([
      purgeOldCaches(), caches.delete(STATIC_CACHE),
    ]));
  }
  // Les anciens messages CACHE_PAGE/CACHE_URLS ne peuvent plus stocker de pages.
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const raw = event.notification.data?.url || '/';
  const url = new URL(raw, self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil(self.clients.openWindow(url.href));
});
