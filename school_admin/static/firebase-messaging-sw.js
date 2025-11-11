// Service Worker pour Firebase Cloud Messaging

// Import Firebase scripts
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
firebase.initializeApp(firebaseConfig);

// Initialiser Firebase Messaging
const messaging = firebase.messaging();

// Gérer les notifications en arrière-plan
messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Message reçu en arrière-plan', payload);
  
  const notificationTitle = payload.notification?.title || 'Nouvelle notification';
  const notificationOptions = {
    body: payload.notification?.body || 'Vous avez une nouvelle notification',
    icon: '/static/school_admin/images/logo.png',
    badge: '/static/school_admin/images/badge.png',
    tag: payload.data?.tag || 'general',
    data: payload.data || {},
    requireInteraction: true,
    vibrate: [200, 100, 200],
  };

  return self.registration.showNotification(notificationTitle, notificationOptions);
});

// Gérer le clic sur la notification
self.addEventListener('notificationclick', (event) => {
  console.log('[firebase-messaging-sw.js] Clic sur la notification', event);
  
  event.notification.close();
  
  // Ouvrir l'URL spécifiée ou le dashboard
  const notificationData = event.notification.data || {};
  const urlToOpen = notificationData.url || notificationData.redirect_url || '/parent/notifications/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Vérifier si une fenêtre est déjà ouverte
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url === urlToOpen && 'focus' in client) {
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

