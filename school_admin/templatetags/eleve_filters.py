"""
Filtres personnalisés pour les élèves
"""
from django import template

register = template.Library()


@register.filter
def premier_nom(value):
    """
    Extrait le premier nom d'une chaîne de noms.
    Exemple: "Dupont Martin" -> "Dupont"
    """
    if not value:
        return ""
    return value.split()[0] if value.split() else ""


@register.filter
def premier_prenom(value):
    """
    Extrait le premier prénom d'une chaîne de prénoms.
    Exemple: "Jean Pierre" -> "Jean"
    """
    if not value:
        return ""
    return value.split()[0] if value.split() else ""

