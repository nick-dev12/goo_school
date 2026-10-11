"""Navigation de l'espace élève (V3) : barre du bas et feuille « Menu »."""
from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()

# clé, nom d'URL, libellé, icône, teinte
_LIENS = [
    ('accueil', 'eleve:dashboard_eleve', 'Accueil', 'fa-house', 'blue'),
    ('edt', 'eleve:emploi_du_temps', 'Emploi du temps', 'fa-calendar-week', 'violet'),
    ('notes', 'eleve:notes_evaluations', 'Notes', 'fa-chart-line', 'green'),
    ('devoirs', 'eleve:devoirs_eleve', 'Devoirs', 'fa-pen-to-square', 'orange'),
    ('cahier', 'eleve:cahier_texte', 'Cahier de texte', 'fa-book-open', 'teal'),
    ('presence', 'eleve:absences_retards', 'Présence', 'fa-user-check', 'teal'),
    ('bulletin', 'eleve:bulletin_eleve', 'Bulletin', 'fa-file-lines', 'royal'),
    ('annonces', 'eleve:annonces_eleve', 'Annonces', 'fa-bullhorn', 'amber'),
    ('convocations', 'eleve:convocations_eleve', 'Convocations', 'fa-calendar-check', 'red'),
    ('sanctions', 'eleve:sanctions_eleve', 'Sanctions', 'fa-gavel', 'slate'),
    ('notifications', 'eleve:notifications_eleve', 'Notifications', 'fa-bell', 'sky'),
    ('historique', 'eleve:historique_annees', 'Mes années', 'fa-clock-rotate-left', 'slate'),
    ('profil', 'eleve:profil_eleve', 'Profil', 'fa-user', 'violet'),
]
_URL_ACTIVE = {
    'dashboard_eleve': 'accueil', 'emploi_du_temps': 'edt', 'notes_evaluations': 'notes',
    'devoirs_eleve': 'devoirs', 'cahier_texte': 'cahier', 'absences_retards': 'presence', 'bulletin_eleve': 'bulletin',
    'annonces_eleve': 'annonces', 'convocations_eleve': 'convocations', 'sanctions_eleve': 'sanctions',
    'notifications_eleve': 'notifications', 'historique_annees': 'historique',
    'historique_annee_detail': 'historique', 'profil_eleve': 'profil',
}
_COURTS = {'edt': 'Planning'}
_BARRE = ('accueil', 'edt', 'notes', 'devoirs', 'presence', 'bulletin', 'annonces', 'profil')
_MOBILE = ('accueil', 'edt', 'notes', 'devoirs')
_GROUPES = [
    ('Ma journée', ('accueil', 'edt', 'devoirs', 'cahier')),
    ('Mes résultats', ('notes', 'bulletin', 'historique')),
    ('Vie scolaire', ('presence', 'convocations', 'sanctions')),
    ('Infos', ('annonces', 'notifications', 'profil')),
]


@register.simple_tag(takes_context=True)
def eleve_nav(context):
    request = context.get('request')
    match = getattr(request, 'resolver_match', None)
    active = _URL_ACTIVE.get(getattr(match, 'url_name', ''), '')
    liens = {}
    for key, name, label, icon, tone in _LIENS:
        try:
            url = reverse(name)
        except NoReverseMatch:
            continue
        liens[key] = {'key': key, 'url': url, 'label': label, 'court': _COURTS.get(key, label),
                      'icon': icon, 'tone': tone, 'active': key == active}
    return {
        'bar': [liens[k] for k in _BARRE if k in liens],
        'mobile': [liens[k] for k in _MOBILE if k in liens],
        'groups': [{'title': t, 'items': [liens[k] for k in keys if k in liens]} for t, keys in _GROUPES],
        'more_active': active not in _MOBILE,
        'active': active,
    }


@register.filter
def matiere_icon(nom):
    from school_admin.services.dashboard.student import style_matiere

    return style_matiere(nom)[0]


@register.filter
def matiere_tone(nom):
    from school_admin.services.dashboard.student import style_matiere

    return style_matiere(nom)[1]


@register.filter
def lignes(texte):
    """Découpe un texte en lignes non vides, sans tiret ni puce de début."""
    out = []
    for ligne in str(texte or '').splitlines():
        ligne = ligne.strip().lstrip('-•*').strip()
        if ligne:
            out.append(ligne)
    return out
