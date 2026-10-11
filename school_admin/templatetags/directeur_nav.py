"""Navigation commune de l'espace direction (barre latérale, barre mobile, feuille « Plus »).

Les liens sont filtrés ici selon les autorisations du personnel connecté : les gabarits
n'ont qu'à les afficher.
"""
from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()

_ETABLISSEMENT_PATHS = (
    '/gestion-etablissement', '/classes', '/salles', '/matieres', '/affectations-salles',
    '/configuration-horaires',
)
_ETABLISSEMENT_NAMES = {
    'gestion_etablissement', 'liste_salles', 'liste_affectations', 'liste_classes', 'configuration_horaires',
}
_PEDAGOGIE_PATHS = (
    '/gestion-pedagogique', '/personnel', '/professeurs', '/affectation/', '/emplois-du-temps',
    '/notes-et-resultats', '/suivi-presence', '/volume-horaire',
)
_PEDAGOGIE_NAMES = {
    'gestion_pedagogique', 'gestion_periodes_scolaires', 'configuration_moyennes_generales',
    'configuration_standards_reussite', 'notes_et_resultats', 'justifications_notes',
    'justifications_notes_classe', 'suivi_presence', 'liste_volume_horaire', 'detail_volume_horaire',
}
_ELEVES_NAMES = {'gestion_eleves', 'demandes_liaison_liste', 'bulletins_notes', 'voir_bulletin_eleve'}
_ADMIN_NAMES = {
    'gestion_administrative', 'certificat_scolarite_liste', 'certificat_radiation_liste',
    'attestation_reussite_liste', 'attestation_conduite_liste', 'fiche_inscription_liste',
}
_EXAMENS_NAMES = {
    'gestion_examens', 'emploi_du_temps_examens', 'configurer_creneaux_examen',
    'modifier_session_examen', 'supprimer_session_examen',
}
_SCOLARITE_NAMES = {
    'liste_comptabilite_eleves_directeur', 'details_comptabilite_eleve_directeur',
    'enregistrer_paiement_directeur', 'parametres_comptabilite_directeur', 'bilan_comptable_directeur',
    'bilan_comptable_classe_directeur', 'liste_impayes_directeur', 'recu_paiement_directeur',
    'creer_moratoire_directeur', 'caisse_mois_directeur',
}


# Couleur unie de chaque section dans la barre du bas.
_TONES = {
    'accueil': 'blue', 'etablissement': 'royal', 'pedagogie': 'violet', 'eleves': 'teal',
    'cahiers': 'green', 'pointage': 'orange',
    'administration': 'sky', 'annonces': 'orange', 'examens': 'amber', 'profil': 'red',
    'scolarite': 'royal', 'finances': 'green', 'notifications': 'slate',
}


def _section(request):
    match = getattr(request, 'resolver_match', None)
    name = (match.url_name if match else '') or ''
    path = request.path or ''
    if name == 'dashboard_directeur':
        return 'accueil'
    if name.startswith('finances_') or name.startswith('cg_'):
        return 'finances'
    if name in _SCOLARITE_NAMES or '/comptabilite/' in path:
        return 'scolarite'
    if name in _EXAMENS_NAMES:
        return 'examens'
    if name == 'annonces_directeur':
        return 'annonces'
    if name == 'cahiers_texte':
        return 'cahiers'
    if name in ('pointage_controle', 'liste_volume_horaire', 'detail_volume_horaire', 'fiche_paie_directeur'):
        return 'pointage'
    if name == 'profil_etablissement':
        return 'profil'
    if name == 'notifications_directeur':
        return 'notifications'
    if name in _ADMIN_NAMES:
        return 'administration'
    if name in _ELEVES_NAMES:
        return 'eleves'
    if name in _PEDAGOGIE_NAMES or any(p in path for p in _PEDAGOGIE_PATHS):
        return 'pedagogie'
    if name in _ETABLISSEMENT_NAMES or any(p in path for p in _ETABLISSEMENT_PATHS):
        return 'etablissement'
    return ''


def _url(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return ''


@register.simple_tag(takes_context=True)
def directeur_nav(context):
    """
    Retourne {'groups': [...], 'mobile': [...], 'active': key}.
    Chaque item : key, label, icon, url, active.
    """
    request = context.get('request')
    if request is None:
        return {'groups': [], 'mobile': [], 'active': ''}
    user = request.user
    is_directeur = bool(context.get('is_directeur'))
    is_caissier = bool(context.get('is_caissier'))

    if is_directeur:
        def can(_perm):
            return True
    else:
        from school_admin.utils.permissions_personnel import has_permission

        def can(perm):
            try:
                return bool(has_permission(user, perm))
            except Exception:
                return False

    libelle_eleves = context.get('libelle_eleves') or 'Élèves'
    etablissement = context.get('etablissement') or getattr(user, 'etablissement', None) or user
    module_compta = bool(getattr(etablissement, 'module_comptabilite', False))
    active = _section(request)

    def item(key, label, icon, url_name):
        url = _url(url_name)
        if not url:
            return None
        return {
            'key': key, 'label': label, 'icon': icon, 'url': url, 'active': key == active,
            'tone': _TONES.get(key, 'blue'),
        }

    pilotage, gestion, finances, compte = [], [], [], []
    pilotage.append(item('accueil', 'Tableau de bord', 'fa-house', 'directeur:dashboard_directeur'))
    if not is_caissier and (
        is_directeur or can('classes_liste') or can('professeurs_liste') or can('personnel_liste')
    ):
        gestion.append(item('etablissement', 'Établissement', 'fa-school', 'directeur:gestion_etablissement'))
    if is_directeur or can('notes_liste') or can('presences_liste'):
        gestion.append(item('pedagogie', 'Pédagogie', 'fa-graduation-cap', 'directeur:gestion_pedagogique'))
    if is_directeur or can('professeurs_detail') or can('pointage_controle'):
        gestion.append(item('cahiers', 'Cahiers de texte', 'fa-book-open', 'directeur:cahiers_texte'))
    if is_directeur or can('pointage_controle'):
        gestion.append(item('pointage', 'Pointage enseignants', 'fa-clipboard-check', 'directeur:pointage_controle'))
    if is_directeur or can('eleves_liste'):
        gestion.append(item('eleves', libelle_eleves, 'fa-user-graduate', 'directeur:gestion_eleves'))
    if is_directeur or can('administrative_voir'):
        gestion.append(item('administration', 'Administration', 'fa-folder-open', 'directeur:gestion_administrative'))
    if is_directeur or can('examens_voir'):
        gestion.append(item('examens', 'Examens', 'fa-clipboard-list', 'directeur:gestion_examens'))
    if is_directeur or can('annonces_voir'):
        gestion.append(item('annonces', 'Annonces', 'fa-bullhorn', 'directeur:annonces_directeur'))
    if is_directeur or can('comptabilite_voir'):
        finances.append(item('scolarite', 'Scolarité', 'fa-receipt', 'directeur:liste_comptabilite_eleves_directeur'))
        if module_compta:
            finances.append(item('finances', 'Finances', 'fa-wallet', 'directeur:finances_situation'))
    compte.append(item('notifications', 'Notifications', 'fa-bell', 'directeur:notifications_directeur'))
    if not is_caissier:
        compte.append(item('profil', 'Profil', 'fa-gear', 'directeur:profil_etablissement'))

    groups = []
    for title, items in (('Pilotage', pilotage), ('Gestion', gestion), ('Finances', finances), ('Compte', compte)):
        items = [i for i in items if i]
        if items:
            groups.append({'title': title, 'items': items})

    flat = [i for group in groups for i in group['items']]
    by_key = {i['key']: i for i in flat}
    # Barre du bas (ordinateur) : toutes les sections, dans l'ordre historique de l'espace.
    bar_order = ['accueil', 'etablissement', 'pedagogie', 'eleves', 'administration', 'annonces',
                 'examens', 'profil', 'scolarite', 'finances']
    bar = [by_key[k] for k in bar_order if k in by_key]
    # Téléphone : 4 raccourcis, le reste dans la feuille « Menu ».
    preferred = ['accueil', 'etablissement', 'pedagogie', 'eleves', 'scolarite', 'administration']
    mobile = [by_key[k] for k in preferred if k in by_key][:4]
    mobile_keys = {i['key'] for i in mobile}
    more_active = active and active not in mobile_keys
    return {'groups': groups, 'bar': bar, 'mobile': mobile, 'active': active, 'more_active': bool(more_active)}


_PETITS_MOTS = {'de', 'du', 'des', 'la', 'le', 'les', "l'", "d'", 'et', 'en'}


@register.filter
def initiales(value, max_letters=2):
    """« Groupe Scolaire Les Almadies » → « GS »."""
    mots = [m for m in str(value or '').replace('’', "'").split() if m.lower() not in _PETITS_MOTS]
    lettres = ''.join(m[0] for m in mots if m and m[0].isalnum())
    return (lettres[: int(max_letters)] or str(value or '?')[:1]).upper()


@register.filter
def depuis(value):
    """Durée écoulée sur une seule unité : « il y a 3 heures » plutôt que « 1 jour, 3 heures »."""
    from django.utils.timesince import timesince

    if not value:
        return ''
    try:
        return timesince(value, depth=1)
    except TypeError:
        return timesince(value).split(',')[0]


# Navigation interne de la comptabilité générale : (groupe, [(clé, url, libellé, icône, teinte)]).
_CG_NAV = [
    ('Pilotage', [
        ('hub', 'directeur:cg_hub_directeur', 'Tableau de bord', 'fa-gauge-high', 'blue'),
        ('etats', 'directeur:cg_etats', 'États financiers', 'fa-chart-pie', 'violet'),
    ]),
    ('Écritures', [
        ('journaux', 'directeur:cg_journaux', 'Journaux et saisie', 'fa-book', 'royal'),
        ('grand_livre', 'directeur:cg_grand_livre', 'Grand livre', 'fa-book-open', 'teal'),
        ('balance', 'directeur:cg_balance', 'Balance', 'fa-scale-balanced', 'sky'),
    ]),
    ('Tiers', [
        ('clients', 'directeur:cg_clients', 'Familles (clients)', 'fa-users', 'green'),
        ('fournisseurs', 'directeur:cg_fournisseurs', 'Fournisseurs', 'fa-file-invoice', 'orange'),
    ]),
    ('Trésorerie', [
        ('tresorerie', 'directeur:cg_tresorerie', 'Trésorerie', 'fa-vault', 'teal'),
        ('rapprochement', 'directeur:cg_rapprochement', 'Rapprochement', 'fa-check-double', 'green'),
        ('caisse', 'directeur:caisse_mois_directeur', 'Caisse', 'fa-cash-register', 'amber'),
    ]),
    ('Opérations', [
        ('recettes', 'directeur:cg_recettes', 'Recettes', 'fa-hand-holding-dollar', 'green'),
        ('prets', 'directeur:cg_prets', 'Prêts', 'fa-landmark', 'violet'),
        ('paie', 'directeur:cg_paie', 'Paie', 'fa-user-clock', 'red'),
        ('immobilisations', 'directeur:cg_immobilisations', 'Immobilisations', 'fa-building', 'slate'),
    ]),
    ('Paramètres', [
        ('plan', 'directeur:cg_plan_comptable', 'Plan comptable', 'fa-sitemap', 'royal'),
        ('exercices', 'directeur:cg_exercices', 'Exercices et clôture', 'fa-lock', 'slate'),
    ]),
]


_CG_URL_KEYS = {
    'cg_hub_directeur': 'hub', 'cg_plan_comptable': 'plan', 'caisse_mois_directeur': 'caisse',
}


@register.simple_tag(takes_context=True)
def cg_nav_items(context, active=''):
    from django.urls import NoReverseMatch, reverse

    if not active:
        match = getattr(context.get('request'), 'resolver_match', None)
        name = getattr(match, 'url_name', '') or ''
        active = _CG_URL_KEYS.get(name, name[3:] if name.startswith('cg_') else '')
    groupes = []
    for titre, items in _CG_NAV:
        liens = []
        for key, name, label, icon, tone in items:
            try:
                url = reverse(name)
            except NoReverseMatch:
                continue
            liens.append({'key': key, 'url': url, 'label': label, 'icon': icon, 'tone': tone, 'active': key == active})
        groupes.append({'titre': titre, 'items': liens})
    return groupes
