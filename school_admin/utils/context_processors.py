# school_admin/utils/context_processors.py
"""
Context processors pour ajouter les permissions aux templates
"""

from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from .permissions_personnel import get_permissions_personnel, has_permission


def permissions(request):
    """
    Ajoute les permissions de l'utilisateur au contexte de tous les templates
    """
    user = request.user
    
    # Si l'utilisateur n'est pas authentifié, retourner un contexte vide
    if not user or not user.is_authenticated:
        return {
            'user_permissions': [],
            'user_has_permission': lambda perm: False,
            'is_directeur': False,
            'is_personnel_administratif': False,
        }
    
    # Si c'est un établissement (directeur), il a toutes les permissions
    if isinstance(user, Etablissement):
        from .permissions_personnel import PERMISSIONS_DISPONIBLES
        all_permissions = list(PERMISSIONS_DISPONIBLES.keys())
        return {
            'user_permissions': all_permissions,
            'user_has_permission': lambda perm: True,
            'is_directeur': True,
            'is_personnel_administratif': False,
        }
    
    # Si c'est un personnel administratif, récupérer ses permissions
    if isinstance(user, PersonnelAdministratif):
        permissions_list = get_permissions_personnel(user)
        return {
            'user_permissions': permissions_list,
            'user_has_permission': lambda perm: has_permission(user, perm),
            'is_directeur': False,
            'is_personnel_administratif': True,
            'personnel_fonction': user.get_fonction_display(),
        }
    
    # Pour les autres types d'utilisateurs, pas de permissions
    return {
        'user_permissions': [],
        'user_has_permission': lambda perm: False,
        'is_directeur': False,
        'is_personnel_administratif': False,
    }

