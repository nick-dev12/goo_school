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
