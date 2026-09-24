"""
Pages parent / espace élève (consultation parent) ouvrables par l'assistant.
"""
from django.urls import NoReverseMatch, reverse

PAGE_CATALOG = (
    {
        'key': 'accueil_parent',
        'titre': 'Accueil parent',
        'route': 'school_admin:dashboard_parent',
        'mots': 'accueil dashboard parent enfants liste',
        'espace': 'parent',
    },
    {
        'key': 'scolarite',
        'titre': 'Scolarité et paiements',
        'route': 'school_admin:scolarite_parent',
        'mots': 'scolarité paiement reste dû échéance reçu',
        'espace': 'parent',
    },
    {
        'key': 'annonces_parent',
        'titre': 'Annonces (espace parent)',
        'route': 'school_admin:annonces_parent',
        'mots': 'annonces communication établissement parents',
        'espace': 'parent',
    },
    {
        'key': 'notifications_parent',
        'titre': 'Notifications parent',
        'route': 'school_admin:notifications_parent',
        'mots': 'notifications alertes parent',
        'espace': 'parent',
    },
    {
        'key': 'profil_parent',
        'titre': 'Mon profil parent',
        'route': 'school_admin:profil_parent',
        'mots': 'profil compte mot de passe parent',
        'espace': 'parent',
    },
    {
        'key': 'convocations_parent',
        'titre': 'Convocations (tous mes enfants)',
        'route': 'school_admin:convocations_parent',
        'mots': 'convocations rendez-vous école parent',
        'espace': 'parent',
    },
    {
        'key': 'retour_enfants',
        'titre': 'Choisir un autre enfant',
        'route': 'school_admin:retour_selection_enfant',
        'mots': 'retour sélection enfant changer',
        'espace': 'parent',
    },
    {
        'key': 'accueil_enfant',
        'titre': 'Tableau de bord de l’enfant',
        'route': 'eleve:dashboard_eleve',
        'mots': 'accueil enfant dashboard élève',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'devoirs',
        'titre': 'Devoirs',
        'route': 'eleve:devoirs_eleve',
        'mots': 'devoirs exercices maison',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'bulletin',
        'titre': 'Bulletin scolaire',
        'route': 'eleve:bulletin_eleve',
        'mots': 'bulletin notes trimestre',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'emploi_du_temps',
        'titre': 'Emploi du temps',
        'route': 'eleve:emploi_du_temps',
        'mots': 'emploi du temps edt horaires',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'notes',
        'titre': 'Notes et évaluations',
        'route': 'eleve:notes_evaluations',
        'mots': 'notes évaluations moyennes',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'absences',
        'titre': 'Absences et retards',
        'route': 'eleve:absences_retards',
        'mots': 'absences retards présence',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'profil_enfant',
        'titre': 'Profil de l’enfant',
        'route': 'eleve:profil_eleve',
        'mots': 'profil élève fiche',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'sanctions',
        'titre': 'Sanctions',
        'route': 'eleve:sanctions_eleve',
        'mots': 'sanctions discipline',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'convocations_enfant',
        'titre': 'Convocations de l’enfant',
        'route': 'eleve:convocations_eleve',
        'mots': 'convocations enfant',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'annonces_enfant',
        'titre': 'Annonces (espace enfant)',
        'route': 'eleve:annonces_eleve',
        'mots': 'annonces élève',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'notifications_enfant',
        'titre': 'Notifications élève',
        'route': 'eleve:notifications_eleve',
        'mots': 'notifications alertes élève',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'historique',
        'titre': 'Historique des années scolaires',
        'route': 'eleve:historique_annees',
        'mots': 'historique années archives passées',
        'espace': 'enfant',
        'requires_enfant_session': True,
    },
    {
        'key': 'selection_enfant',
        'titre': 'Ouvrir l’espace d’un enfant',
        'route': 'school_admin:dashboard_enfant',
        'route_kwargs': ('eleve_id',),
        'mots': 'choisir enfant ouvrir espace',
        'espace': 'parent',
    },
)


def _resolve(route, kwargs=None):
    try:
        return reverse(route, kwargs=kwargs or {})
    except NoReverseMatch:
        return None


def list_pages():
    items = []
    for page in PAGE_CATALOG:
        kwargs = {}
        if page.get('route_kwargs'):
            continue
        url = _resolve(page['route'])
        if not url:
            continue
        items.append({
            'key': page['key'],
            'titre': page['titre'],
            'url': url,
            'mots': page['mots'],
            'espace': page.get('espace'),
            'requires_enfant_session': bool(page.get('requires_enfant_session')),
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
    for meta in PAGE_CATALOG:
        if meta.get('route_kwargs'):
            if meta['key'] == key:
                return {
                    'key': meta['key'],
                    'titre': meta['titre'],
                    'mots': meta['mots'],
                    'espace': meta.get('espace'),
                    'route': meta['route'],
                    'route_kwargs': meta.get('route_kwargs'),
                }
        haystack = f"{meta['titre']} {meta.get('mots') or ''}".lower()
        if key and key in haystack:
            return {
                'key': meta['key'],
                'titre': meta['titre'],
                'mots': meta['mots'],
                'espace': meta.get('espace'),
                'route': meta['route'],
                'route_kwargs': meta.get('route_kwargs'),
                'requires_enfant_session': bool(meta.get('requires_enfant_session')),
            }
    return None


def page_url(page, extra=None):
    extra = extra or {}
    meta = None
    for item in PAGE_CATALOG:
        if item['key'] == page['key']:
            meta = item
            break
    if not meta:
        return page.get('url')
    kwargs = {}
    for arg in meta.get('route_kwargs') or ():
        value = extra.get(arg)
        if value is None:
            return None
        kwargs[arg] = value
    return _resolve(meta['route'], kwargs) or page.get('url')


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
