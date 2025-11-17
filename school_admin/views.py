import logging
import secrets
from datetime import timedelta
from typing import Optional

from django.contrib import messages
from django.contrib.auth import login
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .controllers import (
    AdministrateurCompteController,
    CommercialCompteController,
    CompteUserController,
    EtablissementController,
)
from .forms.professeur_otp_forms import (
    ProfesseurOtpRequestForm,
    ProfesseurOtpVerifyForm,
)
from .model.professeur_model import Professeur
from .model.professeur_otp_model import ProfesseurOtpCode
from .services.wasender_api import WasenderApiClient

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
    Si l'utilisateur est déjà connecté, il est redirigé vers son tableau de bord.
    """
    # Importer les modèles pour la vérification
    from .model.parent_model import Parent
    from .model.compte_user import CompteUser
    from .model.etablissement_model import Etablissement
    from .model.personnel_administratif_model import PersonnelAdministratif
    from .model.eleve_model import Eleve
    from .model.professeur_model import Professeur
    from django.contrib.auth.models import AnonymousUser
    
    # Vérifier si l'utilisateur est déjà authentifié
    # Vérifier aussi directement le type pour éviter les problèmes avec is_authenticated
    is_authenticated_user = (
        request.user.is_authenticated or
        isinstance(request.user, (Parent, CompteUser, Etablissement, PersonnelAdministratif, Eleve, Professeur))
    ) and not isinstance(request.user, AnonymousUser)
    
    if is_authenticated_user:
        logger.info(f"Utilisateur déjà connecté - Type: {type(request.user).__name__}, User: {request.user}, is_authenticated: {request.user.is_authenticated}")
        # Obtenir l'URL du tableau de bord approprié pour cet utilisateur
        dashboard_url = CompteUserController.get_user_dashboard_url(request.user)
        logger.info(f"Redirection vers: {dashboard_url}")
        return redirect(dashboard_url)
    
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
    
    response = render(request, 'school_admin/connexion.html', context)
    # Empêcher la mise en cache pour éviter qu'un utilisateur connecté puisse revoir cette page
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


OTP_RESEND_COOLDOWN_SECONDS = 60


def _normalize_phone_digits(phone_value: Optional[str]) -> str:
    if not phone_value:
        return ""
    return "".join(ch for ch in str(phone_value) if ch.isdigit())


def _find_professeur_by_phone(phone_number: str) -> Optional[Professeur]:
    """
    Recherche un professeur actif en comparant le numéro sous plusieurs formats.
    """

    professeur = Professeur.objects.filter(
        telephone__iexact=phone_number,
        actif=True,
    ).first()
    if professeur:
        return professeur

    stripped_plus = phone_number.lstrip("+")
    if stripped_plus != phone_number:
        professeur = Professeur.objects.filter(
            telephone__iexact=stripped_plus,
            actif=True,
        ).first()
        if professeur:
            return professeur

    normalized_input = _normalize_phone_digits(phone_number)
    if not normalized_input:
        return None

    for prof in Professeur.objects.filter(actif=True).only("id", "telephone", "actif"):
        if _normalize_phone_digits(prof.telephone) == normalized_input:
            return prof

    return None


def professeur_connexion_otp_request(request):
    """
    Affiche le formulaire de demande d'OTP pour les professeurs et gère l'envoi du code.
    """

    form = ProfesseurOtpRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        professeur = _find_professeur_by_phone(phone_number)

        recent_code = (
            ProfesseurOtpCode.objects.filter(
                phone_number=phone_number,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if (
            recent_code
            and not recent_code.is_expired()
            and (timezone.now() - recent_code.created_at).total_seconds()
            < OTP_RESEND_COOLDOWN_SECONDS
        ):
            wait_seconds = OTP_RESEND_COOLDOWN_SECONDS - int(
                (timezone.now() - recent_code.created_at).total_seconds()
            )
            messages.warning(
                request,
                (
                    "Veuillez patienter encore "
                    f"{wait_seconds} seconde(s) avant de redemander un code."
                ),
            )
        else:
            otp_code = f"{secrets.randbelow(1_000_000):06d}"
            otp_entry = ProfesseurOtpCode.objects.create(
                professeur=professeur,
                phone_number=phone_number,
                code=otp_code,
                expires_at=ProfesseurOtpCode.build_expiration(),
            )

            client = WasenderApiClient()
            message = (
                "Goo-school - Code de connexion: "
                f"{otp_code}. Ce code expire dans 5 minutes."
            )

            try:
                response = client.send_text_message(
                    phone_number=phone_number,
                    message=message,
                )
                if not response.is_success:
                    raise ValueError(response.body)
            except Exception as exc:
                otp_entry.delete()
                logger.exception("Erreur lors de l'envoi du code OTP")
                messages.error(
                    request,
                    (
                        "Impossible d'envoyer le code pour le moment. "
                        "Veuillez réessayer ultérieurement."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        "Un code de validation vous a été envoyé sur WhatsApp. "
                        "Veuillez le saisir pour poursuivre votre connexion."
                    ),
                )
                return redirect(
                    reverse(
                        "school_admin:prof_connexion_otp_verify",
                        kwargs={"token": str(otp_entry.token)},
                    )
                )

    context = {
        "form": form,
    }
    return render(
        request,
        "school_admin/professeurs/connexion_otp.html",
        context,
    )


def professeur_connexion_otp_verification(request, token):
    """
    Vérifie le code OTP saisi et connecte le professeur.
    """

    otp_entry = get_object_or_404(ProfesseurOtpCode, token=token)

    if otp_entry.is_used:
        messages.info(
            request,
            "Ce code a déjà été utilisé. Veuillez en générer un nouveau.",
        )
        return redirect("school_admin:prof_connexion_otp")

    if otp_entry.is_expired():
        messages.error(
            request,
            "Ce code a expiré. Merci de demander un nouveau code.",
        )
        return redirect("school_admin:prof_connexion_otp")

    form = ProfesseurOtpVerifyForm(
        request.POST or None,
        initial={"otp_token": otp_entry.token},
    )

    if request.method == "POST" and form.is_valid():
        posted_token = form.cleaned_data["otp_token"]
        if str(posted_token) != str(otp_entry.token):
            messages.error(
                request,
                "Le jeton de validation est invalide. Veuillez recommencer.",
            )
            return redirect("school_admin:prof_connexion_otp")

        if otp_entry.attempts >= ProfesseurOtpCode.MAX_ATTEMPTS:
            messages.error(
                request,
                "Nombre de tentatives dépassé. Veuillez redemander un code.",
            )
            otp_entry.is_used = True
            otp_entry.save(update_fields=["is_used", "updated_at"])
            return redirect("school_admin:prof_connexion_otp")

        if form.cleaned_data["otp_code"] != otp_entry.code:
            otp_entry.attempts += 1
            otp_entry.save(update_fields=["attempts", "updated_at"])
            remaining = ProfesseurOtpCode.MAX_ATTEMPTS - otp_entry.attempts
            messages.error(
                request,
                (
                    "Code incorrect. "
                    f"Il vous reste {max(remaining, 0)} tentative(s)."
                ),
            )
        else:
            professeur = otp_entry.professeur or _find_professeur_by_phone(
                otp_entry.phone_number
            )
            if not professeur:
                messages.error(
                    request,
                    (
                        "Votre numéro n'est pas associé à un compte professeur actif. "
                        "Veuillez contacter l'administration."
                    ),
                )
                return redirect("school_admin:prof_connexion_otp")

            if otp_entry.professeur is None:
                otp_entry.professeur = professeur

            otp_entry.is_used = True
            otp_entry.used_at = timezone.now()
            otp_entry.save(
                update_fields=["is_used", "used_at", "professeur", "updated_at"]
            )

            professeur._auth_user_type = "professeur"
            login(
                request,
                professeur,
                backend="school_admin.authentication_backends.MultiUserBackend",
            )

            if professeur.etablissement.type_etablissement == "primary":
                redirect_url = "enseignant_primaire:dashboard"
            else:
                redirect_url = "enseignant:dashboard_enseignant"

            messages.success(request, "Connexion réussie. Bienvenue !")
            return redirect(redirect_url)

    context = {
        "form": form,
        "expires_in": otp_entry.remaining_seconds(),
        "phone_number": otp_entry.phone_number,
        "token": otp_entry.token,
    }
    return render(
        request,
        "school_admin/professeurs/connexion_otp_verification.html",
        context,
    )





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
