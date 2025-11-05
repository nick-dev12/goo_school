from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def get_note(notes_dict, key):
    """
    Récupère une note depuis un dictionnaire imbriqué
    Usage: {{ notes_existantes|get_note:eleve_id|get_note:note_key }}
    """
    if notes_dict and key in notes_dict:
        return notes_dict[key]
    return None

@register.filter
def format_note(value):
    """
    Formate une note pour affichage dans un input de type number
    Convertit les Decimal en format avec point (8.50) au lieu de virgule (8,50)
    """
    if value is None or value == '':
        return ''
    try:
        # Convertir en float puis formater avec point
        float_value = float(value)
        # Formater avec 2 décimales et point comme séparateur
        return f"{float_value:.2f}".replace(',', '.')
    except (ValueError, TypeError):
        return ''

@register.filter
def get_note_color_class(note_value, bareme):
    """
    Retourne la classe CSS selon la performance de la note
    note_value : la note obtenue
    bareme : le barème de l'évaluation (10 ou 20)
    """
    if note_value is None or note_value == '' or bareme is None:
        return ''
    
    try:
        # Convertir en float
        note = float(note_value)
        bareme_float = float(bareme)
        
        # Calculer le pourcentage
        if bareme_float > 0:
            pourcentage = (note / bareme_float) * 100
        else:
            return ''
        
        # Déterminer la classe selon le pourcentage
        if pourcentage < 40:  # < 8/20
            return 'note-faible'
        elif pourcentage < 50:  # 8-10/20
            return 'note-moyenne-faible'
        elif pourcentage < 70:  # 10-14/20
            return 'note-bonne'
        else:  # >= 14/20
            return 'note-excellente'
            
    except (ValueError, TypeError):
        return ''

@register.filter
def group_classes(classes):
    """
    Regroupe les classes par niveau et retourne une liste de noms de groupes
    Par exemple: ["6eme A", "6eme B", "6eme C"] devient ["6eme"]
    """
    import re
    if not classes:
        return []
    
    groupes = {}
    for classe in classes:
        # Extraire le niveau de base
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            groupe_nom = match.group(1)
        else:
            groupe_nom = classe.nom
        
        if groupe_nom not in groupes:
            groupes[groupe_nom] = []
        groupes[groupe_nom].append(classe)
    
    # Retourner la liste des noms de groupes avec le nombre de classes
    result = []
    for groupe_nom, classes_list in sorted(groupes.items()):
        result.append({
            'nom': groupe_nom,
            'count': len(classes_list)
        })
    return result

# Dictionnaire de correspondance matière -> (icône, couleur)
MATIERES_CONFIG = {
    'Mathématiques': ('calculator', '#3b82f6'),
    'Mathématiques Approfondies': ('calculator', '#3b82f6'),
    'Français': ('book-open', '#10b981'),
    'Anglais': ('globe', '#8b5cf6'),
    'Histoire': ('landmark', '#f59e0b'),
    'Géographie': ('map-marked-alt', '#14b8a6'),
    'Physique-Chimie': ('flask', '#ec4899'),
    'Sciences Physiques': ('flask', '#ec4899'),
    'Sciences Naturelles': ('microscope', '#22c55e'),
    'SVT': ('leaf', '#22c55e'),
    'EPS': ('running', '#ef4444'),
    'Éducation Civique': ('balance-scale', '#6366f1'),
    'Philosophie': ('brain', '#6366f1'),
    'Sciences Économiques': ('chart-line', '#f43f5e'),
    'Arabe': ('language', '#84cc16'),
    'Wolof': ('language', '#84cc16'),
    'Pulaar': ('language', '#84cc16'),
    'Informatique': ('laptop-code', '#06b6d4'),
    'Musique': ('music', '#a855f7'),
    'Arts': ('palette', '#f97316'),
}

@register.filter
def get_matiere_icon(matiere_nom):
    """Retourne l'icône FontAwesome pour une matière"""
    if not matiere_nom:
        return 'book'
    
    # Recherche exacte d'abord
    if matiere_nom in MATIERES_CONFIG:
        return MATIERES_CONFIG[matiere_nom][0]
    
    # Recherche partielle (nom contient la clé OU clé contient le nom)
    for key, (icon, _) in MATIERES_CONFIG.items():
        if key.lower() in matiere_nom.lower() or matiere_nom.lower() in key.lower():
            return icon
    return 'book'

@register.filter
def get_matiere_color(matiere_nom):
    """Retourne la couleur hexadécimale pour une matière"""
    if not matiere_nom:
        return '#64748b'
    
    # Recherche exacte d'abord
    if matiere_nom in MATIERES_CONFIG:
        return MATIERES_CONFIG[matiere_nom][1]
    
    # Recherche partielle (nom contient la clé OU clé contient le nom)
    for key, (_, color) in MATIERES_CONFIG.items():
        if key.lower() in matiere_nom.lower() or matiere_nom.lower() in key.lower():
            return color
    return '#64748b'

@register.filter
def get_item(dictionary, key):
    """
    Récupère un élément d'un dictionnaire par sa clé
    Usage: {{ mon_dict|get_item:ma_cle }}
    """
    if dictionary is None:
        return None
    if isinstance(dictionary, list):
        # Si c'est une liste, utiliser l'index
        try:
            index = int(key)
            if 0 <= index < len(dictionary):
                return dictionary[index]
        except (ValueError, TypeError, IndexError):
            return None
    return dictionary.get(key) if hasattr(dictionary, 'get') else None


@register.filter
def sum_notes_sur_20(notes_list):
    """
    Calcule la somme des notes sur 20
    """
    if not notes_list:
        return 0
    total = 0
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            total += float(note['note_sur_20'])
    return total


@register.filter
def divide(value, divisor):
    """
    Divise une valeur par un diviseur
    """
    try:
        if divisor == 0:
            return 0
        return float(value) / float(divisor)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def max_note_sur_20(notes_list):
    """
    Retourne la note maximale sur 20
    """
    if not notes_list:
        return 0
    notes = []
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            notes.append(float(note['note_sur_20']))
    return max(notes) if notes else 0


@register.filter
def min_note_sur_20(notes_list):
    """
    Retourne la note minimale sur 20
    """
    if not notes_list:
        return 0
    notes = []
    for note in notes_list:
        if isinstance(note, dict) and 'note_sur_20' in note:
            notes.append(float(note['note_sur_20']))
    return min(notes) if notes else 0

