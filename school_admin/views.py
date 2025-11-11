from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from .controllers import CompteUserController, EtablissementController, CommercialCompteController, AdministrateurCompteController
import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Configurer le logger
logger = logging.getLogger(__name__)

# Create your views here.
def inscription_compte_user(request):
    """
    Gère l'inscription d'un nouvel utilisateur (public)
    """
    if request.method == 'POST':
        # Utiliser le contrôleur pour traiter l'inscription
        result = CompteUserController.compte_user_register_view(request)
        if isinstance(result, tuple) and len(result) == 2:
            context, response = result
            if response:
                return response
        else:
            # Si c'est juste le contexte
            context = result
    else:
        # Initialiser le contexte pour le formulaire vide
        context = {
            'field_errors': {},
            'form_data': {}
        }
    
    return render(request, 'school_admin/inscription.html', context)


def connexion_compte_user(request):
    """
    Gère la connexion d'un utilisateur (public)
    """
    if request.method == 'POST':
        # Utiliser le contrôleur pour traiter la connexion
        result = CompteUserController.compte_user_login_view(request)
        if isinstance(result, tuple) and len(result) == 2:
            context, response = result
            if response:
                return response
            # Si pas de redirection, utiliser le contexte
        else:
            # Si c'est juste le contexte
            context = result
    else:
        # Initialiser le contexte pour le formulaire vide
        context = {
            'field_errors': {},
            'form_data': {}
        }
    
    return render(request, 'school_admin/connexion.html', context)





# ===== SUPPORT =====
def dashboard_support(request):
    """
    Tableau de bord pour le support client
    """
    context = {
        'user_function': 'support',
        'page_title': 'Tableau de bord Support'
    }
    return render(request, 'school_admin/dashboards/dashboard_support.html', context)


# ===== DEVELOPPEUR =====
def dashboard_developpeur(request):
    """
    Tableau de bord pour les développeurs
    """
    context = {
        'user_function': 'developpeur',
        'page_title': 'Tableau de bord Développeur'
    }
    return render(request, 'school_admin/dashboards/dashboard_developpeur.html', context)


# ===== MARKETING =====
def dashboard_marketing(request):
    """
    Tableau de bord pour le marketing
    """
    context = {
        'user_function': 'marketing',
        'page_title': 'Tableau de bord Marketing'
    }
    return render(request, 'school_admin/dashboards/dashboard_marketing.html', context)


# ===== COMPTABLE =====
def dashboard_comptable(request):
    """
    Tableau de bord pour les comptables
    """
    context = {
        'user_function': 'comptable',
        'page_title': 'Tableau de bord Comptable'
    }
    return render(request, 'school_admin/dashboards/dashboard_comptable.html', context)


# ===== RH =====
def dashboard_rh(request):
    """
    Tableau de bord pour les ressources humaines
    """
    context = {
        'user_function': 'ressources humaines',
        'page_title': 'Tableau de bord Ressources Humaines'
    }
    return render(request, 'school_admin/dashboards/dashboard_rh.html', context)

# ===== DECONNEXION PAR FONCTION =====
# ===== COMMERCIAL =====
def deconnexion_compte_commercial(request):
    """
    Déconnexion d'un compte commercial
    """
    return CommercialCompteController.logout_user_commercial(request)

# ===== ADMINISTRATEUR =====
def deconnexion_compte_administrateur(request):
    """
    Déconnexion d'un compte administrateur
    """
    return AdministrateurCompteController.logout_user_administrateur(request)

# ===== SUPPORT =====

# ===== DEVELOPPEUR =====

# ===== MARKETING =====

# ===== COMPTABLE =====

# ===== RH =====


# ===== FIREBASE SERVICE WORKER =====
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_control

@require_http_methods(["GET"])
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def firebase_messaging_sw(request):
    """
    Sert le fichier Service Worker pour Firebase Cloud Messaging
    avec le bon Content-Type et depuis la racine du site
    """
    sw_content = """// Service Worker pour Firebase Cloud Messaging

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
  const urlToOpen = event.notification.data?.url || '/';
  
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
"""
    
    return HttpResponse(sw_content, content_type='application/javascript; charset=utf-8')


# ===== PAGE DE TEST FCM =====
from django.contrib.auth.decorators import login_required

@login_required
def test_fcm_page(request):
    """
    Page de test pour les notifications FCM
    """
    return render(request, 'school_admin/test_fcm.html')
