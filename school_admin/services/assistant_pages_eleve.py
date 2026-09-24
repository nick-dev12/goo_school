"""
Pages ouvrables par l'assistant élève (compte élève seul).
"""
from django.urls import NoReverseMatch, reverse

from school_admin.services.assistant_pages_parent import PAGE_CATALOG


def _resolve(route, kwargs=None):
    try:
        return reverse(route, kwargs=kwargs or {})
    except NoReverseMatch:
        return None


def _eleve_catalog_meta():
    """Pages espace enfant sans session parent."""
    for page in PAGE_CATALOG:
        if page.get('espace') != 'enfant':
            continue
        if page.get('route_kwargs'):
            continue
        yield page


def list_pages():
    items = []
    for page in _eleve_catalog_meta():
        url = _resolve(page['route'])
        if not url:
            continue
        items.append({
            'key': page['key'],
            'titre': page['titre'],
            'url': url,
            'mots': page['mots'],
            'espace': 'eleve',
        })
    return items


def find_page(page_key):
    key = (page_key or '').strip().lower()
    pages = list_pages()
    for page in pages:
        if page['key'] == key:
            return page
    for page in pages:
        haystack = f"{page['titre']} {page.get('mots') or ''}".lower()
        if key and key in haystack:
            return page
    for meta in _eleve_catalog_meta():
        haystack = f"{meta['titre']} {meta.get('mots') or ''}".lower()
        if key and key in haystack:
            url = _resolve(meta['route'])
            if url:
                return {
                    'key': meta['key'],
                    'titre': meta['titre'],
                    'mots': meta['mots'],
                    'espace': 'eleve',
                    'url': url,
                }
    return None


def page_url(page, _extra=None):
    if page.get('url'):
        return page['url']
    for meta in _eleve_catalog_meta():
        if meta['key'] == page.get('key'):
            return _resolve(meta['route'])
    return None


def related_pages(page_key, limit=2):
    current = find_page(page_key)
    if not current:
        return []
    words = set((current.get('mots') or '').split())
    scored = []
    for page in list_pages():
        if page['key'] == current['key']:
            continue
        score = len(words.intersection((page.get('mots') or '').split()))
        if score:
            scored.append((score, page))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {'key': page['key'], 'titre': page['titre'], 'url': page['url']}
        for _score, page in scored[:limit]
    ]
