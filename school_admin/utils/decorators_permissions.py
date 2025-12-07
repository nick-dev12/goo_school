# school_admin/utils/decorators_permissions.py
"""
Décorateurs et utilitaires pour vérifier les permissions du personnel administratif
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from .permissions_personnel import has_permission


def require_permission(permission_key):
    """
    Décorateur pour vérifier qu'un utilisateur a une permission donnée
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            # Si c'est un établissement (directeur), il a toutes les permissions
            if isinstance(user, Etablissement):
                return view_func(request, *args, **kwargs)
            
            # Si c'est un personnel administratif, vérifier la permission
            if isinstance(user, PersonnelAdministratif):
                # Rafraîchir les permissions depuis la base de données pour s'assurer qu'elles sont à jour
                user.refresh_from_db()
                if has_permission(user, permission_key):
                    return view_func(request, *args, **kwargs)
                else:
                    messages.error(
                        request, 
                        "Vous n'avez pas l'autorisation d'accéder à cette fonctionnalité."
                    )
                    return redirect('directeur:dashboard_directeur')
            
            # Sinon, rediriger vers la connexion
            messages.error(request, "Accès non autorisé.")
            return redirect('school_admin:connexion_compte_user')
        
        return wrapper
    return decorator


def check_permission(user, permission_key):
    """
    Vérifie si un utilisateur a une permission donnée
    Retourne True si l'utilisateur a la permission, False sinon
    """
    # Si c'est un établissement (directeur), il a toutes les permissions
    if isinstance(user, Etablissement):
        return True
    
    # Si c'est un personnel administratif, vérifier la permission
    if isinstance(user, PersonnelAdministratif):
        # Rafraîchir les permissions depuis la base de données pour s'assurer qu'elles sont à jour
        # Note: refresh_from_db() peut être coûteux, mais garantit la cohérence
        # On pourrait optimiser en ne le faisant que si nécessaire
        try:
            user.refresh_from_db(fields=['permissions'])
        except Exception:
            # Si le refresh échoue, continuer avec les permissions actuelles
            pass
        return has_permission(user, permission_key)
    
    return False


def get_user_permissions(user):
    """
    Retourne toutes les permissions d'un utilisateur
    """
    from .permissions_personnel import get_permissions_personnel
    return get_permissions_personnel(user)


def _get_user_etablissement(request, required_permission=None):
    """
    Fonction utilitaire pour récupérer l'établissement et vérifier les permissions
    Retourne (etablissement, is_directeur, personnel) ou None si accès refusé
    """
    user = request.user
    
    # Si c'est un établissement (directeur), il a toutes les permissions
    if isinstance(user, Etablissement):
        return (user, True, None)
    
    # Si c'est un personnel administratif, vérifier la permission si nécessaire
    if isinstance(user, PersonnelAdministratif):
        # Rafraîchir les permissions depuis la base de données pour s'assurer qu'elles sont à jour
        user.refresh_from_db()
        
        # Si une permission est requise, vérifier qu'elle est accordée
        if required_permission:
            if not has_permission(user, required_permission):
                return (None, False, None)
        
        # Récupérer l'établissement du personnel
        etablissement = user.etablissement
        if not etablissement:
            return (None, False, None)
        
        return (etablissement, False, user)
    
    # Sinon, accès refusé
    return (None, False, None)

