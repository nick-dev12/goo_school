"""
Custom template filters for exam management
"""
import re

from django import template

register = template.Library()


@register.filter
def dict_value(dictionary, key):
    """
    Get a value from a dictionary using a key
    Usage: {{ my_dict|dict_value:my_key }}
    """
    if dictionary and key is not None:
        return dictionary.get(key, None)
    return None


@register.filter
def get_item(dictionary, key):
    """
    Alternative way to get dictionary item
    """
    if dictionary:
        return dictionary.get(key)
    return None


@register.filter
def has_classe_niveau(session, niveau):
    """
    Vérifie si une session a au moins une classe du niveau donné
    Usage: {% if session|has_classe_niveau:niveau %}
    """
    if not session or not niveau:
        return False
    
    niveau_compare = niveau[:4]  # Prendre les 4 premiers caractères (ex: "6eme")
    
    for classe in session.classes.all():
        if classe.nom[:4] == niveau_compare:
            return True
    
    return False


@register.filter
def has_classe_groupe_examen(session, groupe_key):
    """
    Indique si la session concerne au moins une classe du groupe d'affichage.

    - Supérieur : clé de filière ``dept_<id>`` ou ``sans_filiere``.
    - Autres : clé de regroupement (préfixe de nom de classe), alignée sur la création de session.
    """
    if not session or groupe_key is None or str(groupe_key).strip() == '':
        return False

    etab = getattr(session, 'etablissement', None)
    if etab and etab.type_etablissement == 'superieur':
        sk = str(groupe_key)
        if sk == 'sans_filiere':
            return session.classes.filter(department__isnull=True).exists()
        if sk.startswith('dept_'):
            try:
                did = int(sk.replace('dept_', '', 1))
                return session.classes.filter(department_id=did).exists()
            except ValueError:
                return False
        return False

    key = str(groupe_key)
    for classe in session.classes.all():
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        niveau = match.group(1) if match else classe.nom
        if niveau == key:
            return True
    return False


@register.filter
def get_matiere_css_class(matiere_nom):
    """
    Retourne la classe CSS appropriée selon le nom de la matière
    Usage: {{ matiere.nom|get_matiere_css_class }}
    """
    if not matiere_nom:
        return "default"
    
    matiere_lower = matiere_nom.lower()
    
    if 'mathématique' in matiere_lower:
        return "math"
    elif 'français' in matiere_lower or 'francais' in matiere_lower:
        return "francais"
    elif 'histoire' in matiere_lower:
        return "histoire"
    elif 'sport' in matiere_lower or 'éducation physique' in matiere_lower:
        return "sport"
    elif 'anglais' in matiere_lower:
        return "anglais"
    elif 'physique' in matiere_lower or 'chimie' in matiere_lower:
        return "physique"
    elif 'espagnol' in matiere_lower:
        return "espagnol"
    elif 'musique' in matiere_lower:
        return "musique"
    elif 'art' in matiere_lower:
        return "arts"
    else:
        return "default"


@register.filter
def get_matiere_icon(matiere_nom):
    """
    Retourne l'icône appropriée selon le nom de la matière
    Usage: {{ matiere.nom|get_matiere_icon }}
    """
    if not matiere_nom:
        return "fas fa-book"
    
    matiere_lower = matiere_nom.lower()
    
    if 'mathématique' in matiere_lower:
        return "fas fa-calculator"
    elif 'français' in matiere_lower or 'francais' in matiere_lower:
        return "fas fa-book-open"
    elif 'histoire' in matiere_lower:
        return "fas fa-landmark"
    elif 'sport' in matiere_lower or 'éducation physique' in matiere_lower:
        return "fas fa-running"
    elif 'anglais' in matiere_lower:
        return "fas fa-globe"
    elif 'physique' in matiere_lower or 'chimie' in matiere_lower:
        return "fas fa-flask"
    elif 'espagnol' in matiere_lower:
        return "fas fa-language"
    elif 'musique' in matiere_lower:
        return "fas fa-music"
    elif 'art' in matiere_lower:
        return "fas fa-palette"
    else:
        return "fas fa-book"

