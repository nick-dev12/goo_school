"""
Pages enseignant primaire ouvrables par l'assistant vocal.
"""
from django.urls import NoReverseMatch, reverse

PAGE_CATALOG = (
    {
        'key': 'dashboard',
        'titre': 'Tableau de bord',
        'route': 'enseignant_primaire:dashboard',
        'mots': 'accueil dashboard tableau de bord',
    },
    {
        'key': 'classes',
        'titre': 'Mes classes',
        'route': 'enseignant_primaire:gestion_classes',
        'mots': 'classes mes classes',
    },
    {
        'key': 'eleves',
        'titre': 'Élèves',
        'route': 'enseignant_primaire:gestion_eleves',
        'mots': 'élèves liste élèves',
    },
    {
        'key': 'notes',
        'titre': 'Notes et évaluations',
        'route': 'enseignant_primaire:gestion_notes',
        'mots': 'notes évaluations relevé',
    },
    {
        'key': 'evaluations',
        'titre': 'Liste des évaluations',
        'route': 'enseignant_primaire:liste_evaluations',
        'mots': 'évaluations devoirs contrôles',
    },
    {
        'key': 'eleves_difficulte',
        'titre': 'Élèves en difficulté',
        'route': 'enseignant_primaire:eleves_en_difficulte',
        'mots': 'difficulté faible moyenne',
    },
    {
        'key': 'exercices',
        'titre': 'Exercices à la maison',
        'route': 'enseignant_primaire:exercices_maison',
        'mots': 'exercices devoirs maison',
    },
    {
        'key': 'presence',
        'titre': 'Présences',
        'route': 'enseignant_primaire:gestion_presence',
        'mots': 'présence absences appel',
    },
    {
        'key': 'emploi_du_temps',
        'titre': 'Emploi du temps',
        'route': 'enseignant_primaire:emploi_du_temps',
        'mots': 'emploi du temps edt horaires',
    },
    {
        'key': 'annonces',
        'titre': 'Annonces',
        'route': 'enseignant_primaire:annonces_enseignant',
        'mots': 'annonces communication',
    },
    {
        'key': 'justifications_notes',
        'titre': 'Justifications de notes',
        'route': 'enseignant_primaire:justifications_notes',
        'mots': 'justification correction note',
    },
    {
        'key': 'parametres_profil',
        'titre': 'Paramètres du profil',
        'route': 'enseignant_primaire:parametres_profil',
        'mots': 'profil paramètres compte',
    },
    {
        'key': 'historique_annees',
        'titre': 'Historique des années',
        'route': 'enseignant_primaire:historique_annees',
        'mots': 'historique années passées',
    },
    {
        'key': 'noter_eleves',
        'titre': 'Noter les élèves',
        'route': 'enseignant_primaire:noter_eleves',
        'route_kwargs': ('classe_id',),
        'mots': 'noter saisie notes',
    },
    {
        'key': 'detail_classe',
        'titre': 'Fiche classe',
        'route': 'enseignant_primaire:detail_classe',
        'route_kwargs': ('classe_id',),
        'mots': 'classe détail fiche',
    },
    {
        'key': 'liste_presence',
        'titre': 'Liste de présence du jour',
        'route': 'enseignant_primaire:liste_presence',
        'route_kwargs': ('classe_id',),
        'mots': 'appel présence classe',
    },
    {
        'key': 'voir_releve',
        'titre': 'Voir le relevé de notes',
        'route': 'enseignant_primaire:voir_releve',
        'route_kwargs': ('classe_id',),
        'mots': 'relevé notes classe',
    },
    {
        'key': 'imprimer_releve',
        'titre': 'Imprimer le relevé',
        'route': 'enseignant_primaire:imprimer_releve',
        'route_kwargs': ('classe_id',),
        'mots': 'impression relevé pdf',
    },
    {
        'key': 'imprimer_tableau_presence',
        'titre': 'Imprimer tableau de présence',
        'route': 'enseignant_primaire:imprimer_tableau_presence',
        'route_kwargs': ('classe_id',),
        'mots': 'impression présence appel',
    },
    {
        'key': 'historique_annee_detail',
        'titre': 'Détail historique année',
        'route': 'enseignant_primaire:historique_annee_detail',
        'route_kwargs': ('annee_id',),
        'mots': 'archive année détail',
    },
    {
        'key': 'historique_presence',
        'titre': 'Historique présence élève',
        'route': 'enseignant_primaire:historique_presence',
        'route_kwargs': ('eleve_id',),
        'mots': 'absences élève historique',
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
        url = _resolve(page['route'])
        if not url:
            continue
        items.append({
            'key': page['key'],
            'titre': page['titre'],
            'url': url,
            'mots': page['mots'],
            'route_kwargs': page.get('route_kwargs') or (),
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
    return None


def page_url(page, extra=None):
    extra = extra or {}
    meta = None
    for item in PAGE_CATALOG:
        if item['key'] == page['key']:
            meta = item
            break
    kwargs = {}
    if meta:
        for arg in meta.get('route_kwargs') or ():
            value = extra.get(arg)
            if value is None:
                return None
            kwargs[arg] = value
    return _resolve(meta['route'] if meta else page.get('route'), kwargs) or page.get('url')


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
