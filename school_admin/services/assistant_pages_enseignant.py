"""
Pages enseignant secondaire / supérieur ouvrables par l'assistant vocal.
"""
from django.urls import NoReverseMatch, reverse

PAGE_CATALOG = (
    {
        'key': 'dashboard',
        'titre': 'Tableau de bord',
        'route': 'enseignant:dashboard_enseignant',
        'mots': 'accueil dashboard tableau de bord',
    },
    {
        'key': 'classes',
        'titre': 'Mes classes',
        'route': 'enseignant:gestion_classes',
        'mots': 'classes mes classes',
    },
    {
        'key': 'eleves',
        'titre': 'Élèves',
        'route': 'enseignant:gestion_eleves',
        'mots': 'élèves liste élèves',
    },
    {
        'key': 'notes',
        'titre': 'Notes et évaluations',
        'route': 'enseignant:gestion_notes',
        'mots': 'notes évaluations relevé',
    },
    {
        'key': 'evaluations',
        'titre': 'Liste des évaluations',
        'route': 'enseignant:liste_evaluations',
        'mots': 'évaluations devoirs contrôles',
    },
    {
        'key': 'eleves_difficulte',
        'titre': 'Élèves en difficulté',
        'route': 'enseignant:eleves_en_difficulte',
        'mots': 'difficulté faible moyenne',
    },
    {
        'key': 'exercices',
        'titre': 'Exercices à la maison',
        'route': 'enseignant:exercices_maison',
        'mots': 'exercices devoirs maison',
    },
    {
        'key': 'presence',
        'titre': 'Présences',
        'route': 'enseignant:gestion_presence',
        'mots': 'présence absences appel',
    },
    {
        'key': 'emploi_du_temps',
        'titre': 'Emploi du temps',
        'route': 'enseignant:emploi_du_temps',
        'mots': 'emploi du temps edt horaires',
    },
    {
        'key': 'annonces',
        'titre': 'Annonces',
        'route': 'enseignant:annonces_enseignant',
        'mots': 'annonces communication',
    },
    {
        'key': 'justifications_notes',
        'titre': 'Justifications de notes',
        'route': 'enseignant:justifications_notes',
        'mots': 'justification correction note',
    },
    {
        'key': 'parametres_profil',
        'titre': 'Paramètres du profil',
        'route': 'enseignant:parametres_profil',
        'mots': 'profil paramètres compte',
    },
    {
        'key': 'historique_annees',
        'titre': 'Historique des années',
        'route': 'enseignant:historique_annees',
        'mots': 'historique années passées',
    },
    {
        'key': 'noter_eleves',
        'titre': 'Noter les élèves',
        'route': 'enseignant:noter_eleves',
        'route_kwargs': ('classe_id',),
        'mots': 'noter saisie notes',
    },
    {
        'key': 'detail_classe',
        'titre': 'Fiche classe',
        'route': 'enseignant:detail_classe',
        'route_kwargs': ('classe_id',),
        'mots': 'classe détail fiche',
    },
    {
        'key': 'liste_presence',
        'titre': 'Liste de présence du jour',
        'route': 'enseignant:liste_presence',
        'route_kwargs': ('classe_id',),
        'mots': 'appel présence classe',
    },
    {
        'key': 'notifications',
        'titre': 'Notifications',
        'route': 'enseignant:notifications_enseignant',
        'mots': 'notifications alertes',
    },
    {
        'key': 'noter_examen',
        'titre': 'Noter un examen',
        'route': 'enseignant:noter_examen',
        'route_kwargs': ('classe_id',),
        'mots': 'examen composition session noter',
    },
    {
        'key': 'voir_releve',
        'titre': 'Voir le relevé de notes',
        'route': 'enseignant:voir_releve',
        'route_kwargs': ('classe_id',),
        'mots': 'relevé notes classe',
    },
    {
        'key': 'imprimer_releve',
        'titre': 'Imprimer le relevé',
        'route': 'enseignant:imprimer_releve',
        'route_kwargs': ('classe_id',),
        'mots': 'impression relevé pdf',
    },
    {
        'key': 'imprimer_releve_enseignant',
        'titre': 'Imprimer relevé enseignant',
        'route': 'enseignant:imprimer_releve_enseignant',
        'route_kwargs': ('classe_id',),
        'mots': 'impression relevé professeur',
    },
    {
        'key': 'imprimer_tableau_presence',
        'titre': 'Imprimer tableau de présence',
        'route': 'enseignant:imprimer_tableau_presence',
        'route_kwargs': ('classe_id',),
        'mots': 'impression présence appel',
    },
    {
        'key': 'historique_annee_detail',
        'titre': 'Détail historique année',
        'route': 'enseignant:historique_annee_detail',
        'route_kwargs': ('annee_id',),
        'mots': 'archive année détail',
    },
    {
        'key': 'historique_presence',
        'titre': 'Historique présence élève',
        'route': 'enseignant:historique_presence',
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

