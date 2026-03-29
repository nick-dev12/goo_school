from decimal import Decimal, InvalidOperation

from django import template

from ..model.classe_model import libelle_cle_niveau_superieur

register = template.Library()


@register.filter
def libelle_niveau_lmd_key(value):
    """Convertit une clé LMD (L1, BTS…) en libellé long pour les titres de section."""
    return libelle_cle_niveau_superieur(value)


@register.filter
def dict_get(d, key):
    """Valeur d'un dict par clé ; chaîne vide si absent (évite les faux « 0 » des autres filtres)."""
    if d is None or not isinstance(d, dict):
        return ''
    v = d.get(str(key))
    if v is None:
        v = d.get(key)
    return '' if v is None else v


@register.filter
def credits_input_display(value):
    """
    Valeur pour champ <input type="number"> : entier sans « .00 », sinon décimale sans zéros de queue.
    """
    if value is None or value == '':
        return ''
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if d != d:
        return ''
    if d == d.to_integral():
        return str(int(d))
    normalized = d.normalize()
    s = format(normalized, 'f').rstrip('0').rstrip('.')
    return s if s else '0'
