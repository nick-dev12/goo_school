"""Valeurs CSS strictement validées pour les cartes et leur aperçu."""
import re
from django import template

register = template.Library()


@register.filter
def modele_carte(value):
    return value if value in ('classique', 'moderne', 'horizon', 'signature', 'elan', 'campus', 'prisme',
                              'rivage', 'academie', 'equateur') else 'classique'


@register.filter
def couleur_carte(value, fallback='#3b82f6'):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback


@register.filter
def contraste_carte(value):
    value = couleur_carte(value)
    rgb = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    rgb = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    luminance = sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722)))
    return '#111827' if luminance > .179 else '#ffffff'


@register.filter
def qr_carte(eleve):
    """Rendu net des cartes existantes, sans regeneration en base."""
    if not eleve.qr_code_identifier:
        return ''
    from school_admin.services.carte_qr import qr_svg_data_uri
    return qr_svg_data_uri(eleve._build_qr_payload())


@register.filter
def telephone_parent_carte(eleve):
    from school_admin.services.carte_contacts import telephone_parent_carte as telephone
    return telephone(eleve)


@register.filter
def telephone_international_carte(numero, pays):
    from school_admin.services.carte_contacts import telephone_international_carte as formater
    return formater(numero, pays)
