from django import template

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

