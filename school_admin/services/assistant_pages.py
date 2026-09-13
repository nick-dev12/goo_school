"""
Pages directeur que l'assistant peut ouvrir ou suggérer.
"""
from django.urls import NoReverseMatch, reverse

PAGE_CATALOG = (
    {
        'key': 'dashboard',
        'titre': 'Tableau de bord',
        'route': 'directeur:dashboard_directeur',
        'mots': 'accueil dashboard tableau de bord',
    },
    {
        'key': 'etablissement',
        'titre': 'Gestion de l’établissement',
        'route': 'directeur:gestion_etablissement',
        'mots': 'établissement structure',
    },
    {
        'key': 'classes',
        'titre': 'Classes',
        'route': 'administrateur_etablissement:liste_classes',
        'mots': 'classes promotions filières',
    },
    {
        'key': 'salles',
        'titre': 'Salles',
        'route': 'salle:liste_salles',
        'mots': 'salles locaux',
    },
    {
        'key': 'matieres',
        'titre': 'Matières et modules',
        'route': 'matiere:liste_matieres',
        'mots': 'matières modules pédagogie',
    },
    {
        'key': 'emplois_du_temps',
        'titre': 'Emplois du temps',
        'route': 'administrateur_etablissement:liste_emplois_du_temps',
        'mots': 'emploi du temps edt horaires',
    },
    {
        'key': 'pedagogie',
        'titre': 'Pédagogie',
        'route': 'directeur:gestion_pedagogique',
        'mots': 'pédagogie notes présence',
    },
    {
        'key': 'professeurs',
        'titre': 'Professeurs',
        'route': 'professeur:liste_professeurs',
        'mots': 'professeurs enseignants',
    },
    {
        'key': 'personnel',
        'titre': 'Personnel administratif',
        'route': 'personnel:liste_personnel',
        'mots': 'personnel administratif',
    },
    {
        'key': 'eleves',
        'titre': 'Élèves / étudiants',
        'route': 'secretaire:liste_eleves',
        'mots': 'élèves étudiants liste',
    },
    {
        'key': 'gestion_eleves',
        'titre': 'Gestion des élèves',
        'route': 'directeur:gestion_eleves',
        'mots': 'gestion élèves inscriptions',
    },
    {
        'key': 'notes',
        'titre': 'Notes et résultats',
        'route': 'directeur:notes_et_resultats',
        'mots': 'notes résultats évaluations',
    },
    {
        'key': 'presences',
        'titre': 'Suivi des présences',
        'route': 'directeur:suivi_presence',
        'mots': 'présences absences',
    },
    {
        'key': 'periodes',
        'titre': 'Périodes scolaires',
        'route': 'directeur:gestion_periodes_scolaires',
        'mots': 'périodes trimestres semestres',
    },
    {
        'key': 'bulletins',
        'titre': 'Bulletins',
        'route': 'directeur:bulletins_notes',
        'mots': 'bulletins',
    },
    {
        'key': 'annonces',
        'titre': 'Annonces',
        'route': 'directeur:annonces_directeur',
        'mots': 'annonces communication',
    },
    {
        'key': 'creer_annonce',
        'titre': 'Créer une annonce',
        'route': 'directeur:creer_annonce',
        'mots': 'nouvelle annonce créer publier',
    },
    {
        'key': 'examens',
        'titre': 'Gestion des examens',
        'route': 'directeur:gestion_examens',
        'mots': 'examens sessions',
    },
    {
        'key': 'emploi_examens',
        'titre': 'Emploi du temps des examens',
        'route': 'directeur:emploi_du_temps_examens',
        'mots': 'emploi examens planning',
    },
    {
        'key': 'comptabilite',
        'titre': 'Scolarité et comptabilité',
        'route': 'directeur:liste_comptabilite_eleves_directeur',
        'mots': 'scolarité comptabilité paiements frais',
    },
    {
        'key': 'administration',
        'titre': 'Administration',
        'route': 'directeur:gestion_administrative',
        'mots': 'administration documents',
    },
    {
        'key': 'convocations',
        'titre': 'Convocations',
        'route': 'directeur:convocation_liste',
        'mots': 'convocations',
    },
    {
        'key': 'certificats',
        'titre': 'Certificats de scolarité',
        'route': 'directeur:certificat_scolarite_liste',
        'mots': 'certificats scolarité',
    },
    {
        'key': 'preinscriptions',
        'titre': 'Préinscriptions',
        'route': 'directeur:liste_preinscriptions',
        'mots': 'préinscriptions candidatures',
    },
    {
        'key': 'liaisons',
        'titre': 'Demandes de liaison',
        'route': 'directeur:demandes_liaison_liste',
        'mots': 'liaison parents',
    },
    {
        'key': 'notifications',
        'titre': 'Notifications',
        'route': 'directeur:notifications_directeur',
        'mots': 'notifications',
    },
    {
        'key': 'profil',
        'titre': 'Profil de l’établissement',
        'route': 'directeur:profil_etablissement',
        'mots': 'profil établissement',
    },
    {
        'key': 'annees',
        'titre': 'Années scolaires',
        'route': 'directeur:liste_annees_scolaires',
        'mots': 'années scolaires sessions',
    },
)


def _resolve(route):
    try:
        return reverse(route)
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
