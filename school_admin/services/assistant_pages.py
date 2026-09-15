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
        'key': 'affectations',
        'titre': 'Affectation des professeurs',
        'route': 'affectation:affectation_professeurs',
        'mots': 'affectations professeurs classes matières enseigne',
    },
    {
        'key': 'volume_horaire',
        'titre': 'Volume horaire à payer',
        'route': 'directeur:liste_volume_horaire',
        'mots': 'volume horaire paie vacataires heures tarif professeur',
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
        'key': 'caisse',
        'titre': 'Caisse du mois',
        'route': 'directeur:caisse_mois_directeur',
        'mots': 'caisse dépenses solde recettes sorties',
    },
    {
        'key': 'comptabilite_generale',
        'titre': 'Comptabilité générale',
        'route': 'directeur:cg_hub_directeur',
        'mots': 'syscohada grand livre bilan journal exercice trésorerie fournisseurs',
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
    {
        'key': 'creer_annee',
        'titre': 'Créer une année scolaire',
        'route': 'directeur:creer_annee_scolaire',
        'mots': 'nouvelle année scolaire créer session',
    },
    {
        'key': 'facturation',
        'titre': 'Facturation établissement',
        'route': 'directeur:facturation_directeur',
        'mots': 'facturation abonnement',
    },
    {
        'key': 'reinscription',
        'titre': 'Réinscription des élèves',
        'route': 'directeur:liste_reinscription',
        'mots': 'réinscription',
    },
    {
        'key': 'justifications_notes',
        'titre': 'Justifications de notes',
        'route': 'directeur:justifications_notes',
        'mots': 'justifications notes',
    },
    {
        'key': 'config_moyennes',
        'titre': 'Configuration des moyennes',
        'route': 'directeur:configuration_moyennes_generales',
        'mots': 'configuration moyennes',
    },
    {
        'key': 'config_standards',
        'titre': 'Standards de réussite',
        'route': 'directeur:configuration_standards_reussite',
        'mots': 'standards réussite',
    },
    {
        'key': 'attestations_reussite',
        'titre': 'Attestations de réussite',
        'route': 'directeur:attestation_reussite_liste',
        'mots': 'attestations réussite',
    },
    {
        'key': 'attestations_conduite',
        'titre': 'Attestations de conduite',
        'route': 'directeur:attestation_conduite_liste',
        'mots': 'attestations conduite',
    },
    {
        'key': 'fiches_inscription',
        'titre': 'Fiches d’inscription',
        'route': 'directeur:fiche_inscription_liste',
        'mots': 'fiches inscription',
    },
    {
        'key': 'certificats_radiation',
        'titre': 'Certificats de radiation',
        'route': 'directeur:certificat_radiation_liste',
        'mots': 'certificats radiation transfert',
    },
    {
        'key': 'bilan_comptable',
        'titre': 'Bilan comptable',
        'route': 'directeur:bilan_comptable_directeur',
        'mots': 'bilan comptable recettes',
    },
    {
        'key': 'parametres_comptabilite',
        'titre': 'Paramètres de comptabilité',
        'route': 'directeur:parametres_comptabilite_directeur',
        'mots': 'paramètres comptabilité frais',
    },
    {
        'key': 'parametres_groupes',
        'titre': 'Paramètres par groupe de classes',
        'route': 'directeur:liste_parametres_groupes_directeur',
        'mots': 'paramètres groupes classes',
    },
    {
        'key': 'liens_preinscription',
        'titre': 'Liens de préinscription',
        'route': 'directeur:gerer_liens_preinscription',
        'mots': 'liens préinscription',
    },
    {
        'key': 'ajouter_classe',
        'titre': 'Ajouter une classe',
        'route': 'administrateur_etablissement:ajouter_classe',
        'mots': 'nouvelle classe ajouter',
    },
    {
        'key': 'filieres',
        'titre': 'Filières',
        'route': 'administrateur_etablissement:liste_filieres',
        'mots': 'filières spécialités',
    },
    {
        'key': 'ajouter_salle',
        'titre': 'Ajouter une salle',
        'route': 'salle:ajouter_salle',
        'mots': 'nouvelle salle',
    },
    {
        'key': 'ajouter_matiere',
        'titre': 'Ajouter une matière',
        'route': 'matiere:ajouter_matiere',
        'mots': 'nouvelle matière',
    },
    {
        'key': 'modules',
        'titre': 'Modules LMD',
        'route': 'matiere:liste_modules',
        'mots': 'modules LMD supérieur',
    },
    {
        'key': 'ajouter_professeur',
        'titre': 'Ajouter un professeur',
        'route': 'professeur:ajouter_professeur',
        'mots': 'nouveau professeur enseignant',
    },
    {
        'key': 'ajouter_personnel',
        'titre': 'Ajouter du personnel',
        'route': 'personnel:ajouter_personnel',
        'mots': 'nouveau personnel',
    },
    {
        'key': 'inscription_eleves',
        'titre': 'Inscrire un élève',
        'route': 'secretaire:inscription_eleves',
        'mots': 'inscription nouvel élève',
    },
    {
        'key': 'cartes_identite',
        'titre': 'Cartes d’identité élèves',
        'route': 'secretaire:cartes_identite_eleves',
        'mots': 'cartes identité',
    },
    {
        'key': 'configuration_horaires',
        'titre': 'Configuration des horaires',
        'route': 'administrateur_etablissement:configuration_horaires',
        'mots': 'horaires configuration créneaux',
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
