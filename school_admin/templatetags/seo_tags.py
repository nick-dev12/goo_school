"""Tags template pour le référencement (SEO) ARIA."""

from django import template

from school_admin.seo import resolve_seo

register = template.Library()


@register.inclusion_tag("school_admin/partials/seo_head.html", takes_context=True)
def seo_head(context, title=None, description=None, keywords=None, robots=None, canonical=None):
    """
    Affiche title, meta description, robots, Open Graph et PWA.
    Exemple : {% seo_head title="Ma page" description="..." %}
    """
    seo = dict(context.get("seo") or {})
    if title:
        seo["title"] = title
    if description:
        seo["description"] = description
    if keywords:
        seo["keywords"] = keywords
    if robots:
        seo["robots"] = robots
    if canonical:
        seo["canonical_url"] = canonical

    request = context.get("request")
    if request and not seo:
        seo = resolve_seo(request)

    return {
        "seo": seo,
        "request": request,
    }


@register.simple_tag(takes_context=True)
def seo_title(context, extra=""):
    """Retourne le titre SEO (pour pages avec <title> séparé legacy)."""
    seo = context.get("seo") or {}
    if extra:
        from school_admin.seo import SITE_NAME, _title

        return _title(extra, SITE_NAME)
    return seo.get("title", "ARIA")
