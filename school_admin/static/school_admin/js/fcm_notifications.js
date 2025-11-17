// Gestion des notifications Firebase Cloud Messaging

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-app.js";
import { getMessaging, getToken, onMessage } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging.js";

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

// Clé VAPID
const VAPID_KEY = "BOcifkSIQA0dwy2S50hgj2uXz0DzPliCQZsNplPZCwNonprBCJdORq_T5VPYmophqkHkcZjeWYVhoBEKnlPDsgE";

// Initialiser Firebase
const app = initializeApp(firebaseConfig);
const messaging = getMessaging(app);

/**
 * Demander la permission pour les notifications
 */
export async function requestNotificationPermission() {
  try {
    console.log('[FCM] Demande de permission pour les notifications...');

    // Vérifier si les notifications sont supportées
    if (!('Notification' in window)) {
      console.error('[FCM] Les notifications ne sont pas supportées par ce navigateur');
      return null;
    }

    // Demander la permission
    const permission = await Notification.requestPermission();

    if (permission === 'granted') {
      console.log('[FCM] Permission accordée');
      return await registerServiceWorkerAndGetToken();
    } else if (permission === 'denied') {
      console.warn('[FCM] Permission refusée');
      return null;
    } else {
      console.warn('[FCM] Permission par défaut (non accordée)');
      return null;
    }
  } catch (error) {
    console.error('[FCM] Erreur lors de la demande de permission:', error);
    return null;
  }
}

/**
 * Enregistrer le service worker et obtenir le token FCM
 */
async function registerServiceWorkerAndGetToken() {
  try {
    // Enregistrer le service worker
    console.log('[FCM] Enregistrement du service worker...');
    const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js', {
      scope: '/'
    });

    console.log('[FCM] Service worker enregistré:', registration);

    // Attendre que le service worker soit actif
    await navigator.serviceWorker.ready;

    // Obtenir le token FCM
    console.log('[FCM] Obtention du token FCM...');
    const token = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: registration
    });

    if (token) {
      console.log('[FCM] Token obtenu:', token);
      await saveTokenToServer(token);
      return token;
    } else {
      console.warn('[FCM] Aucun token obtenu');
      return null;
    }
  } catch (error) {
    console.error('[FCM] Erreur lors de l\'obtention du token:', error);
    return null;
  }
}

/**
 * Sauvegarder le token sur le serveur
 */
async function saveTokenToServer(token) {
  try {
    console.log('[FCM] Sauvegarde du token sur le serveur...');

    const csrfToken = getCookie('csrftoken');

    const response = await fetch('/api/fcm/save-token/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({
        token: token,
        device_type: 'web',
        device_name: navigator.userAgent
      })
    });

    if (response.ok) {
      const data = await response.json();
      console.log('[FCM] Token sauvegardé avec succès:', data);

      // Afficher le message de succès
      showSuccessMessage();

      return true;
    } else {
      console.error('[FCM] Erreur lors de la sauvegarde du token:', response.status);
      return false;
    }
  } catch (error) {
    console.error('[FCM] Erreur lors de la sauvegarde du token:', error);
    return false;
  }
}

/**
 * Gérer les messages en avant-plan (quand l'app est ouverte)
 */
export function handleForegroundMessages() {
  onMessage(messaging, (payload) => {
    console.log('[FCM] Message reçu en avant-plan:', payload);

    // Afficher une notification personnalisée
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

    // Afficher la notification
    if (Notification.permission === 'granted') {
      new Notification(notificationTitle, notificationOptions);
    }

    // Afficher aussi une alerte toast dans l'interface
    showToastNotification(notificationTitle, notificationOptions.body);
  });
}

/**
 * Afficher une notification toast dans l'interface
 */
function showToastNotification(title, message) {
  // Créer un élément toast
  const toast = document.createElement('div');
  toast.className = 'fcm-toast-notification';
  toast.innerHTML = `
    <div class="fcm-toast-header">
      <i class="fas fa-bell"></i>
      <strong>${title}</strong>
      <button class="fcm-toast-close">&times;</button>
    </div>
    <div class="fcm-toast-body">${message}</div>
  `;

  // Ajouter au body
  document.body.appendChild(toast);

  // Animer l'apparition
  setTimeout(() => {
    toast.classList.add('show');
  }, 100);

  // Gérer la fermeture
  const closeBtn = toast.querySelector('.fcm-toast-close');
  closeBtn.addEventListener('click', () => {
    toast.classList.remove('show');
    setTimeout(() => {
      toast.remove();
    }, 300);
  });

  // Auto-fermeture après 5 secondes
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 5000);
}

/**
 * Obtenir le cookie CSRF
 */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * Initialiser les notifications FCM
 */
export async function initializeFCM() {
  console.log('[FCM] Initialisation...');

  // Vérifier si l'utilisateur a déjà donné la permission
  if (Notification.permission === 'granted') {
    console.log('[FCM] Permission déjà accordée, enregistrement du token...');
    await registerServiceWorkerAndGetToken();
    hideNotificationButton();
  } else if (Notification.permission === 'default') {
    console.log('[FCM] Permission non définie, affichage du bouton');
    showNotificationButton();
  } else {
    console.log('[FCM] Permission refusée');
    hideNotificationButton();
  }

  // Écouter les messages en avant-plan
  handleForegroundMessages();
}

/**
 * Afficher le bouton pour activer les notifications
 */
function showNotificationButton() {
  const btn = document.getElementById('fcm-enable-btn');
  if (btn) {
    btn.style.display = 'flex';
  }
}

/**
 * Cacher le bouton d'activation
 */
function hideNotificationButton() {
  const btn = document.getElementById('fcm-enable-btn');
  if (btn) {
    btn.style.display = 'none';
  }
}

/**
 * Afficher le message de succès
 */
function showSuccessMessage() {
  const msg = document.getElementById('fcm-success-message');
  if (msg) {
    // Afficher le message avec animation
    msg.classList.add('show');

    // Masquer automatiquement après 5 secondes
    setTimeout(() => {
      msg.classList.remove('show');
    }, 5000);
  }
}

/**
 * Fonction appelée par le bouton d'activation
 */
window.activerNotifications = async function () {
  console.log('[FCM] Bouton activer notifications cliqué');
  const token = await requestNotificationPermission();

  if (token) {
    hideNotificationButton();
    showSuccessMessage();
  } else {
    alert('Impossible d\'activer les notifications. Veuillez autoriser les notifications dans les paramètres de votre navigateur.');
  }
};

// Initialiser automatiquement au chargement de la page
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeFCM);
} else {
  initializeFCM();
}

