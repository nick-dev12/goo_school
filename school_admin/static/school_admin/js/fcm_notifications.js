// Gestion des notifications Firebase Cloud Messaging

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-app.js";
import { getMessaging, getToken, onMessage, isSupported, deleteToken } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-messaging.js";

let firebaseConfig, VAPID_KEY;
let messaging;
let listenerReady = false;
const button = () => document.getElementById('fcm-enable-btn');
function csrf() { return document.cookie.split('; ').find(v => v.startsWith('csrftoken='))?.split('=').slice(1).join('=') || ''; }
function setButton(visible) { if (button()) button().style.setProperty('display', visible ? 'flex' : 'none', 'important'); }
async function save(token) {
  return fetch('/api/fcm/save-token/', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(csrf())}, body:JSON.stringify({token, device_type:'web', device_name:navigator.userAgent.slice(0,255)})});
}
async function register() {
  await navigator.serviceWorker.register('/service-worker.js', {scope:'/'});
  const registration = await navigator.serviceWorker.ready;
  let token = await getToken(messaging, {vapidKey:VAPID_KEY, serviceWorkerRegistration:registration});
  if (!token) throw new Error('Aucun appareil enregistré.');
  let response = await save(token);
  if (response.status === 403) {
    // Ancienne installation associée à un compte dont la session a expiré.
    await deleteToken(messaging);
    token = await getToken(messaging, {vapidKey:VAPID_KEY, serviceWorkerRegistration:registration});
    response = await save(token);
  }
  if (!response.ok || !(await response.json()).success) throw new Error("L'appareil n'a pas pu être enregistré. Réessayez.");
  setButton(false);
  if (!document.getElementById('fcm-test-own-btn') && button()) {
    const test = document.createElement('button');
    test.id = 'fcm-test-own-btn'; test.type = 'button';
    test.className = button().className; test.textContent = 'Tester les notifications';
    test.addEventListener('click', async () => {
      test.disabled = true;
      try {
        const response = await fetch('/api/push/test/', {method:'POST', credentials:'same-origin', headers:{'X-CSRFToken':decodeURIComponent(csrf())}});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Test indisponible.');
        test.textContent = 'Test envoyé — vérifie les notifications';
      } catch(error) {alert(error.message);} finally {test.disabled = false;}
    });
    button().after(test);
  }
  return registration;
}
function safeUrl(data) { const url = new URL(data?.url || data?.redirect_url || '/', location.origin); return url.origin === location.origin ? url.href : location.origin; }
function foreground(payload) {
  const data = payload.data || {};
  const title = data.title || payload.notification?.title || 'Aria';
  const body = data.body || payload.notification?.body || 'Nouvelle notification';
  navigator.serviceWorker.ready.then(registration => registration.showNotification(title, {body, icon:'/static/school_admin/images/logo.png', data:{...data,url:safeUrl(data)}, tag:data.tag || data.notification_id || undefined}));
  const toast = document.createElement('button');
  toast.type = 'button'; toast.className = 'fcm-toast-notification show';
  toast.textContent = title + ' — ' + body;
  toast.style.cssText='position:fixed;top:20px;right:20px;z-index:10000;max-width:350px;padding:1rem;background:white;border:1px solid #ddd;border-radius:12px;color:#172033';
  toast.addEventListener('click',()=>{ location.href=safeUrl(data); });
  document.body.append(toast); setTimeout(()=>toast.remove(),7000);
}
export async function initializeFCM() {
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !window.isSecureContext || !(await isSupported())) {setButton(false); return false;}
  if (!messaging) { const response = await fetch('/api/push/config/'); if (!response.ok) throw new Error('Configuration push indisponible.'); const config = await response.json(); firebaseConfig = config.firebase; VAPID_KEY = config.vapidKey; messaging = getMessaging(initializeApp(firebaseConfig)); }
  if (!listenerReady) {onMessage(messaging, foreground); listenerReady=true;}
  setButton(Notification.permission !== 'denied');
  if (Notification.permission === 'granted') {
    try {await register();} catch (error) {setButton(true); console.warn('[Push]',error.message);}
  }
  return true;
}
window.activerNotifications = async function() {
  try {
    if (!messaging && !(await initializeFCM())) throw new Error('Notifications indisponibles sur ce navigateur.');
    if (await Notification.requestPermission() !== 'granted') throw new Error('Autorisez les notifications dans les réglages du navigateur.');
    await register();
    const message=document.getElementById('fcm-success-message');
    if(message) {message.textContent='Notifications activées sur cet appareil.'; message.style.cssText='display:flex!important;visibility:visible!important;opacity:1!important'; setTimeout(()=>message.style.display='none',5000);}
  } catch(error) {setButton(true); alert(error.message);}
};
initializeFCM().catch(error=>console.warn('[Push]',error.message));
