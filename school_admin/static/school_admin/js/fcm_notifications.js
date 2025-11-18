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

// Flag pour indiquer si l'activation est manuelle (via bouton)
let isManualActivation = false;

/**
 * Protection : Liste des IDs d'éléments que ce script est autorisé à modifier
 * Aucun autre élément ne doit être modifié par ce script
 */
const ALLOWED_ELEMENT_IDS = ['fcm-enable-btn', 'fcm-success-message'];

/**
 * Vérifier si un élément peut être modifié par ce script
 */
function isElementAllowed(element) {
  if (!element || !element.id) return false;
  return ALLOWED_ELEMENT_IDS.includes(element.id);
}

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
      // Passer true pour afficher le message lors de l'activation manuelle
      return await registerServiceWorkerAndGetToken(true);
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
async function registerServiceWorkerAndGetToken(showMessage = false) {
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
      await saveTokenToServer(token, showMessage);
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
async function saveTokenToServer(token, showMessage = false) {
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

      // Afficher le message de succès seulement si demandé (lors de l'activation manuelle)
      if (showMessage) {
        showSuccessMessage();
      }

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
 * Crée un nouvel élément, ne modifie PAS les éléments existants de la page
 */
function showToastNotification(title, message) {
  // Créer un élément toast avec position fixe pour ne pas affecter le layout
  const toast = document.createElement('div');
  toast.className = 'fcm-toast-notification';
  // Position fixe pour ne pas affecter le layout de la page
  toast.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; max-width: 350px;';
  toast.innerHTML = `
    <div class="fcm-toast-header">
      <i class="fas fa-bell"></i>
      <strong>${title}</strong>
      <button class="fcm-toast-close">&times;</button>
    </div>
    <div class="fcm-toast-body">${message}</div>
  `;

  // Ajouter au body (création d'un nouvel élément, ne modifie pas les existants)
  document.body.appendChild(toast);

  // Animer l'apparition
  setTimeout(() => {
    toast.classList.add('show');
  }, 100);

  // Gérer la fermeture
  const closeBtn = toast.querySelector('.fcm-toast-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      toast.classList.remove('show');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.remove();
        }
      }, 300);
    });
  }

  // Auto-fermeture après 5 secondes
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.remove();
      }
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

  // TOUJOURS cacher le message au chargement de la page
  // Il ne doit s'afficher QUE lors de l'activation manuelle
  hideSuccessMessage();

  // Vérifier si l'utilisateur a déjà donné la permission
  if (Notification.permission === 'granted') {
    console.log('[FCM] Permission déjà accordée, enregistrement du token...');
    // Ne JAMAIS afficher le message si la permission était déjà accordée
    await registerServiceWorkerAndGetToken(false);
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
 * Ne modifie QUE le style display du bouton spécifique
 */
function showNotificationButton() {
  const btn = document.getElementById('fcm-enable-btn');
  if (btn && isElementAllowed(btn)) {
    // Ne modifier QUE la propriété display, rien d'autre
    btn.style.setProperty('display', 'flex', 'important');
  }
}

/**
 * Cacher le bouton d'activation
 * Ne modifie QUE le style display du bouton spécifique
 */
function hideNotificationButton() {
  const btn = document.getElementById('fcm-enable-btn');
  if (btn && isElementAllowed(btn)) {
    // Ne modifier QUE la propriété display, rien d'autre
    btn.style.setProperty('display', 'none', 'important');
  }
}

/**
 * Afficher le message de succès
 * Cette fonction ne doit être appelée QUE lors de l'activation manuelle des notifications
 * Ne modifie QUE les styles du message spécifique, rien d'autre
 */
function showSuccessMessage() {
  // SÉCURITÉ : Ne jamais afficher si ce n'est pas une activation manuelle
  if (!isManualActivation) {
    console.log('[FCM] showSuccessMessage appelé mais isManualActivation est false - message non affiché');
    return;
  }

  const msg = document.getElementById('fcm-success-message');
  if (msg && isElementAllowed(msg)) {
    // Ne modifier QUE les propriétés du message spécifique
    msg.style.setProperty('display', 'flex', 'important');
    msg.style.setProperty('visibility', 'visible', 'important');

    // Afficher le message avec animation
    setTimeout(() => {
      msg.classList.add('show');
    }, 100);

    // Masquer automatiquement après 5 secondes
    setTimeout(() => {
      msg.classList.remove('show');
      setTimeout(() => {
        msg.style.setProperty('display', 'none', 'important');
        msg.style.setProperty('visibility', 'hidden', 'important');
        // Réinitialiser le flag après la fermeture
        isManualActivation = false;
      }, 500); // Attendre la fin de l'animation
    }, 5000);
  }
}

/**
 * Cacher le message de succès
 * Appelé au chargement de la page pour s'assurer qu'il ne s'affiche jamais automatiquement
 * Ne modifie QUE les styles du message spécifique, rien d'autre
 */
function hideSuccessMessage() {
  const msg = document.getElementById('fcm-success-message');
  if (msg && isElementAllowed(msg)) {
    // Ne modifier QUE les propriétés du message spécifique
    msg.classList.remove('show');
    msg.style.setProperty('display', 'none', 'important');
    msg.style.setProperty('visibility', 'hidden', 'important');
    msg.style.setProperty('opacity', '0', 'important');
    // Ne PAS toucher aux autres éléments de la page
  }
}

/**
 * Fonction appelée par le bouton d'activation
 * C'est la SEULE fonction qui doit afficher le message de succès
 */
window.activerNotifications = async function () {
  console.log('[FCM] Bouton activer notifications cliqué');

  // Marquer comme activation manuelle
  isManualActivation = true;

  const token = await requestNotificationPermission();

  if (token) {
    hideNotificationButton();
    // Afficher le message UNIQUEMENT lors de l'activation manuelle réussie
    // Le flag isManualActivation est déjà à true
    showSuccessMessage();
  } else {
    // Réinitialiser le flag si l'activation a échoué
    isManualActivation = false;
    // Ne pas afficher de message si l'activation a échoué
    alert('Impossible d\'activer les notifications. Veuillez autoriser les notifications dans les paramètres de votre navigateur.');
  }
};

// Cacher le message IMMÉDIATEMENT au chargement (avant même que le script ne s'exécute complètement)
// Ne modifier QUE le message spécifique, rien d'autre
(function () {
  const msg = document.getElementById('fcm-success-message');
  if (msg && msg.id === 'fcm-success-message') {
    // Ne modifier QUE les propriétés du message spécifique avec setProperty pour éviter les conflits
    msg.style.setProperty('display', 'none', 'important');
    msg.style.setProperty('visibility', 'hidden', 'important');
    msg.style.setProperty('opacity', '0', 'important');
    msg.classList.remove('show');
    // Ne PAS toucher aux autres éléments de la page
  }
})();

// Initialiser automatiquement au chargement de la page
// S'assurer que le message est caché dès le chargement
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () {
    // S'assurer que le flag est false (pas d'activation manuelle)
    isManualActivation = false;

    // Cacher le message immédiatement - Ne modifier QUE ce message spécifique
    const msg = document.getElementById('fcm-success-message');
    if (msg && msg.id === 'fcm-success-message') {
      msg.style.setProperty('display', 'none', 'important');
      msg.style.setProperty('visibility', 'hidden', 'important');
      msg.style.setProperty('opacity', '0', 'important');
      msg.classList.remove('show');
      // Ne PAS toucher aux autres éléments de la page
    }
    // Puis initialiser FCM
    initializeFCM();
  });
} else {
  // S'assurer que le flag est false (pas d'activation manuelle)
  isManualActivation = false;

  // Cacher le message immédiatement
  const msg = document.getElementById('fcm-success-message');
  if (msg) {
    msg.style.display = 'none';
    msg.style.visibility = 'hidden';
    msg.classList.remove('show');
    msg.style.opacity = '0';
  }
  // Puis initialiser FCM
  initializeFCM();
}

