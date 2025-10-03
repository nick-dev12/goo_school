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
