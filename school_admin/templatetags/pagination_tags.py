from django import template

register = template.Library()

@register.filter
def get_range(value):
    """
    Filtre pour générer une liste de nombres de 1 à value
    
    Usage:
    {% for i in total_pages|get_range %}
        {{ i }}
    {% endfor %}
    """
    try:
        value = int(value)
        return range(1, value + 1)
    except (ValueError, TypeError):
        return range(0)

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Filtre personnalisé pour accéder aux éléments d'un dictionnaire dans les templates
    Usage: {{ mon_dict|get_item:ma_cle }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)