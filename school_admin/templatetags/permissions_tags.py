# school_admin/templatetags/permissions_tags.py
"""
Template tags pour vérifier les permissions dans les templates
"""

from django import template
from ..model.etablissement_model import Etablissement
from ..model.personnel_administratif_model import PersonnelAdministratif
from ..utils.permissions_personnel import has_permission

register = template.Library()


@register.filter
def has_perm(user, permission_key):
    """
    Vérifie si un utilisateur a une permission donnée
    Usage dans template: {% if user|has_perm:"eleves_liste" %}
    """
    if not user or not user.is_authenticated:
        return False
    
    # Si c'est un établissement (directeur), il a toutes les permissions
    if isinstance(user, Etablissement):
        return True
    
    # Si c'est un personnel administratif, vérifier la permission
    if isinstance(user, PersonnelAdministratif):
        return has_permission(user, permission_key)
    
    return False


@register.simple_tag
def check_permission(user, permission_key):
    """
    Vérifie si un utilisateur a une permission donnée
    Usage dans template: {% check_permission user "eleves_liste" as can_view_eleves %}
    """
    if not user or not user.is_authenticated:
        return False
    
    # Si c'est un établissement (directeur), il a toutes les permissions
    if isinstance(user, Etablissement):
        return True
    
    # Si c'est un personnel administratif, vérifier la permission
    if isinstance(user, PersonnelAdministratif):
        return has_permission(user, permission_key)
    
    return False


@register.simple_tag
def is_directeur(user):
    """
    Vérifie si l'utilisateur est un directeur (établissement)
    Usage dans template: {% is_directeur user as is_dir %}
    """
    return isinstance(user, Etablissement)


@register.simple_tag
def is_personnel_administratif(user):
    """
    Vérifie si l'utilisateur est un personnel administratif
    Usage dans template: {% is_personnel_administratif user as is_pers %}
    """
    return isinstance(user, PersonnelAdministratif)

