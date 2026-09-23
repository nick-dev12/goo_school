"""
Vague 1 — filtrage du schéma assistant directeur par type d’établissement,
typage des classes (cycle), et droits du personnel via check_permission.
"""
from __future__ import annotations

import copy
import logging

from school_admin.utils.context_processors import AFFICHER_MODULE_COMPTABILITE_GENERALE

logger = logging.getLogger(__name__)

TYPE_PRIMARY = frozenset({'primary', 'primaire'})
TYPE_COLLEGE = frozenset({'collège', 'college'})
TYPE_LYCEE = frozenset({'lycée', 'lycee'})
TYPE_DUAL = frozenset({'collège_lycée', 'college_lycee', 'mixte'})
TYPE_SUPERIEUR = frozenset({'superieur'})

CYCLE_ALIASES = {
    'college': 'college',
    'collège': 'college',
    'premier cycle': 'college',
    '1er cycle': 'college',
    'lycee': 'lycee',
    'lycée': 'lycee',
    'second cycle': 'lycee',
    '2nd cycle': 'lycee',
    '2e cycle': 'lycee',
    'primaire': 'primaire',
    'primary': 'primaire',
    'maternelle': 'maternelle',
    'superieur': 'superieur',
    'supérieur': 'superieur',
}

SUPERIEUR_ONLY_TOOLS = frozenset({
    'get_structure_superieur',
    'creer_filiere',
    'modifier_filiere',
    'supprimer_filiere',
    'creer_module',
    'supprimer_module',
    'get_ects_etudiant',
    'get_ects_classe',
    'get_modules_classe',
    'affecter_module_classe',
    'fixer_credits_module',
    'get_releve_ects',
})

NIVEAU_LMD_ENUM = [
    'L1', 'L2', 'L3',
    'BTS1', 'BTS2',
    'DUT1', 'DUT2',
    'M1', 'M2',
    'D1', 'D2', 'D3',
]

DUAL_ONLY_TOOLS = frozenset({
    'get_repartition_cycles',
})

# Tools CG à exclure tant que le module est masqué. Aucun n’existe encore en Vague 1.
CG_TOOLS = frozenset({
    'get_plan_comptable',
    'get_journaux',
    'get_ecritures',
    'get_grand_livre',
    'get_balance',
    'get_compte_resultat',
    'get_bilan_syscohada',
    'get_exercice',
    'creer_ecriture_od',
    'extourner_ecriture',
    'cloturer_periode',
    'cloturer_exercice',
    'get_fournisseurs',
    'creer_fournisseur',
    'saisir_facture_fournisseur',
    'regler_fournisseur',
    'get_tresorerie_cg',
    'enregistrer_virement_interne',
    'get_clients_411',
})

SUPERIEUR_PAGE_KEYS = frozenset({'filieres', 'modules'})
CG_PAGE_KEYS = frozenset({'comptabilite_generale'})

# None = autorisé pour tout personnel connecté (navigation / session).
# str | tuple = au moins une permission Django requise.
TOOL_PERMISSIONS = {
    'chercher_en_base': None,
    'lister_pages': None,
    'ouvrir_page': None,
    'changer_session': None,
    'get_notifications': None,
    'get_annees': None,
    'get_effectifs': 'eleves_liste',
    'rechercher_eleves': 'eleves_liste',
    'inscrire_eleve': 'eleves_inscrire',
    'modifier_eleve': 'eleves_modifier',
    'reinscrire_eleve': 'eleves_reinscrire',
    'activer_eleve': 'eleves_modifier',
    'desactiver_eleve': 'eleves_modifier',
    'get_preinscriptions': 'eleves_liste',
    'valider_preinscription': 'eleves_inscrire',
    'rejeter_preinscription': 'eleves_inscrire',
    'toggle_lien_preinscription': 'eleves_inscrire',
    'get_liaisons': 'eleves_liste',
    'approuver_liaison': 'eleves_modifier',
    'rejeter_liaison': 'eleves_modifier',
    'desapprouver_liaison': 'eleves_modifier',
    'rechercher_classes': 'classes_liste',
    'ouvrir_classe': 'classes_detail',
    'creer_classe': 'classes_modifier',
    'modifier_classe': 'classes_modifier',
    'desactiver_classe': 'classes_modifier',
    'supprimer_classe': 'classes_modifier',
    'get_emploi_du_temps': 'classes_detail',
    'creer_emploi_du_temps': 'classes_modifier',
    'ajouter_creneau_emploi': 'classes_modifier',
    'publier_emploi_du_temps': 'classes_modifier',
    'supprimer_creneau_emploi': 'classes_modifier',
    'get_salles': 'classes_liste',
    'creer_salle': 'classes_modifier',
    'modifier_salle': 'classes_modifier',
    'desactiver_salle': 'classes_modifier',
    'get_matieres': 'classes_liste',
    'creer_matiere': 'classes_modifier',
    'desactiver_matiere': 'classes_modifier',
    'get_notes_eleve': 'notes_detail',
    'get_notes_classe': 'notes_liste',
    'get_moyennes_classe': 'notes_liste',
    'get_bulletin_eleve': 'bulletins_voir',
    'imprimer_bulletins_classe': 'bulletins_voir',
    'get_eleves_difficulte': 'notes_liste',
    'get_justifications_notes': 'notes_justifications_voir',
    'traiter_justification': 'notes_justifications_voir',
    'get_coefficients': 'notes_liste',
    'configurer_coefficient': 'classes_modifier',
    'get_evaluations': 'notes_liste',
    'calculer_moyenne_annuelle': 'notes_liste',
    'publier_bulletins': 'bulletins_voir',
    'calculer_moyennes_classe': 'notes_liste',
    'configurer_visibilite_bulletins': 'bulletins_voir',
    'configurer_moyennes': 'config_modifier',
    'configurer_standards': 'config_modifier',
    'get_periodes': 'config_voir',
    'creer_periode': 'config_modifier',
    'activer_periode': 'config_modifier',
    'supprimer_periode': 'config_modifier',
    'creer_annee_scolaire': 'config_modifier',
    'activer_annee_scolaire': 'config_modifier',
    'desactiver_annee_scolaire': 'config_modifier',
    'get_presences': 'presences_liste',
    'justifier_absence': 'presences_detail',
    'get_sanctions': 'sanctions_liste',
    'donner_sanction': 'sanctions_creer',
    'rechercher_professeurs': 'professeurs_liste',
    'get_affectations': 'professeurs_liste',
    'creer_professeur': 'professeurs_modifier',
    'modifier_professeur': 'professeurs_modifier',
    'desactiver_professeur': 'professeurs_modifier',
    'affecter_professeur': 'professeurs_modifier',
    'enregistrer_absence_professeur': 'professeurs_modifier',
    'get_volume_horaire': 'professeurs_liste',
    'marquer_paie': 'professeurs_modifier',
    'get_dossier_employe': ('professeurs_liste', 'personnel_liste'),
    'modifier_dossier_employe': ('professeurs_modifier', 'personnel_modifier'),
    'get_absences_professeur': 'professeurs_liste',
    'supprimer_absence_professeur': 'professeurs_modifier',
    'ouvrir_fiche_paie': 'professeurs_liste',
    'rechercher_personnel': 'personnel_liste',
    'creer_personnel': 'personnel_modifier',
    'modifier_personnel': 'personnel_modifier',
    'desactiver_personnel': 'personnel_modifier',
    'get_annonces': 'annonces_voir',
    'creer_publier_annonce': 'annonces_voir',
    'publier_annonce': 'annonces_voir',
    'modifier_annonce': 'annonces_voir',
    'archiver_annonce': 'annonces_voir',
    'supprimer_annonce': 'annonces_voir',
    'get_examens': 'examens_voir',
    'creer_session_examen': 'examens_voir',
    'supprimer_session_examen': 'examens_voir',
    'generer_document': 'administrative_voir',
    'get_comptabilite': 'comptabilite_voir',
    'get_fiche_scolarite': 'comptabilite_voir',
    'get_bilan_scolarite': 'comptabilite_voir',
    'get_impayes': 'comptabilite_voir',
    'ouvrir_recu': 'comptabilite_voir',
    'get_moratoires': 'comptabilite_voir',
    'verifier_statuts_paiement': 'comptabilite_voir',
    'synchroniser_remises_fratrie': 'comptabilite_paiements',
    'get_statistiques_pilotage': 'eleves_liste',
    'get_taux_reussite': 'notes_liste',
    'get_taux_presence': 'presences_liste',
    'get_comparatif_periodes': 'notes_liste',
    'get_repartition_cycles': 'eleves_liste',
    'get_parametres_comptabilite': 'comptabilite_voir',
    'creer_parametres_comptabilite': 'comptabilite_bilans',
    'modifier_parametres_comptabilite': 'comptabilite_bilans',
    'supprimer_parametres_comptabilite': 'comptabilite_bilans',
    'enregistrer_paiement': 'comptabilite_paiements',
    'creer_moratoire': 'comptabilite_paiements',
    'payer_echeance_moratoire': 'comptabilite_paiements',
    'relancer_impaye': 'comptabilite_paiements',
    'get_caisse': 'comptabilite_voir',
    'ajouter_depense': 'comptabilite_paiements',
    'supprimer_depense': 'comptabilite_paiements',
    'get_structure_superieur': 'classes_liste',
    'creer_filiere': 'classes_modifier',
    'modifier_filiere': 'classes_modifier',
    'supprimer_filiere': 'classes_modifier',
    'creer_module': 'classes_modifier',
    'supprimer_module': 'classes_modifier',
    'get_ects_etudiant': 'notes_detail',
    'get_ects_classe': 'notes_liste',
    'get_modules_classe': 'classes_detail',
    'affecter_module_classe': 'classes_modifier',
    'fixer_credits_module': 'classes_modifier',
    'get_releve_ects': 'notes_detail',
}

CHERCHER_EN_BASE_SOURCES = {
    'effectifs': 'get_effectifs',
    'notes': 'get_notes_eleve',
    'notes_classe': 'get_notes_classe',
    'moyennes_classe': 'get_moyennes_classe',
    'bulletin': 'get_bulletin_eleve',
    'difficulte': 'get_eleves_difficulte',
    'justifications': 'get_justifications_notes',
    'coefficients': 'get_coefficients',
    'evaluations': 'get_evaluations',
    'presences': 'get_presences',
    'sanctions': 'get_sanctions',
    'caisse': 'get_caisse',
    'volume_horaire': 'get_volume_horaire',
    'dossier_employe': 'get_dossier_employe',
    'absences_professeur': 'get_absences_professeur',
    'fiche_paie': 'ouvrir_fiche_paie',
    'comptabilite': 'get_comptabilite',
    'pilotage': 'get_statistiques_pilotage',
    'reussite': 'get_taux_reussite',
    'presence_taux': 'get_taux_presence',
    'comparatif': 'get_comparatif_periodes',
    'cycles': 'get_repartition_cycles',
    'scolarite': 'get_fiche_scolarite',
    'bilan': 'get_bilan_scolarite',
    'impayes': 'get_impayes',
    'recu': 'ouvrir_recu',
    'moratoires': 'get_moratoires',
    'emploi': 'get_emploi_du_temps',
    'periodes': 'get_periodes',
    'annonces': 'get_annonces',
    'preinscriptions': 'get_preinscriptions',
    'liaisons': 'get_liaisons',
    'examens': 'get_examens',
    'annees': 'get_annees',
    'salles': 'get_salles',
    'matieres': 'get_matieres',
    'notifications': 'get_notifications',
    'structure': 'get_structure_superieur',
    'ects': 'get_ects_etudiant',
    'ects_classe': 'get_ects_classe',
    'modules_classe': 'get_modules_classe',
    'releve_ects': 'get_releve_ects',
    'affectations': 'get_affectations',
    'professeurs': 'rechercher_professeurs',
    'personnel': 'rechercher_personnel',
    'classes': 'rechercher_classes',
    'eleves': 'rechercher_eleves',
}


def normalize_type(etablissement):
    return (getattr(etablissement, 'type_etablissement', None) or '').strip().lower()


def classify_etablissement(etablissement):
    raw = normalize_type(etablissement)
    est_primaire = raw in TYPE_PRIMARY
    est_college = raw in TYPE_COLLEGE
    est_lycee = raw in TYPE_LYCEE
    est_college_lycee = raw in TYPE_DUAL
    est_superieur = raw in TYPE_SUPERIEUR
    return {
        'type': raw,
        'est_primaire': est_primaire,
        'est_college': est_college,
        'est_lycee': est_lycee,
        'est_college_lycee': est_college_lycee,
        'est_superieur': est_superieur,
        'cycle_requis': est_college_lycee,
    }


def schema_profile(ctx):
    if getattr(ctx, 'est_superieur', False):
        return 'superieur'
    if getattr(ctx, 'est_primaire', False):
        return 'primaire'
    if getattr(ctx, 'est_college_lycee', False):
        return 'dual'
    if getattr(ctx, 'est_college', False):
        return 'college'
    if getattr(ctx, 'est_lycee', False):
        return 'lycee'
    return 'secondaire'


def cg_visible():
    return bool(AFFICHER_MODULE_COMPTABILITE_GENERALE)


def normalize_cycle(raw):
    text = (raw or '').strip().lower()
    if not text:
        return None
    if text in CYCLE_ALIASES:
        return CYCLE_ALIASES[text]
    for alias, value in CYCLE_ALIASES.items():
        if alias in text:
            return value
    return None


def resolve_niveau_classe(ctx, args):
    """Retourne le niveau Classe (college/lycee/…) ou None s’il faut demander le cycle."""
    args = args if isinstance(args, dict) else {}
    mapped = normalize_cycle(args.get('cycle') or args.get('niveau'))
    if getattr(ctx, 'est_primaire', False):
        return mapped if mapped in ('primaire', 'maternelle') else 'primaire'
    if getattr(ctx, 'est_college', False):
        return 'college'
    if getattr(ctx, 'est_lycee', False):
        return 'lycee'
    if getattr(ctx, 'est_superieur', False):
        return 'superieur'
    if getattr(ctx, 'est_college_lycee', False):
        if mapped in ('college', 'lycee'):
            return mapped
        return None
    return mapped


def resolve_niveau_enseignement(etablissement, cycle=None):
    flags = classify_etablissement(etablissement)
    mapped = normalize_cycle(cycle)
    if flags['est_primaire']:
        return 'primaire'
    if flags['est_college']:
        return 'college'
    if flags['est_lycee']:
        return 'lycee'
    if flags['est_superieur']:
        return 'superieur'
    if mapped in ('college', 'lycee', 'primaire', 'maternelle', 'superieur'):
        return mapped
    return None


def hidden_tools_for(ctx):
    hidden = set()
    if not getattr(ctx, 'est_superieur', False):
        hidden.update(SUPERIEUR_ONLY_TOOLS)
    if not getattr(ctx, 'est_college_lycee', False):
        hidden.update(DUAL_ONLY_TOOLS)
    if not cg_visible():
        hidden.update(CG_TOOLS)
    return hidden


def _schema_names(schema):
    names = []
    for item in schema:
        name = (item.get('function') or {}).get('name')
        if name:
            names.append(name)
    return names


def _require_cycle_param(item):
    function = item.get('function') or {}
    params = function.setdefault('parameters', {'type': 'object', 'properties': {}})
    props = params.setdefault('properties', {})
    props['cycle'] = {
        'type': 'string',
        'enum': ['college', 'lycee'],
        'description': (
            'Cycle obligatoire pour un établissement collège+lycée ou mixte : '
            'college ou lycee.'
        ),
    }
    required = list(params.get('required') or [])
    if 'cycle' not in required:
        required.append('cycle')
    params['required'] = required
    description = function.get('description') or ''
    if 'cycle' not in description.lower():
        function['description'] = (
            description.rstrip('.')
            + '. Précise le cycle (college ou lycee) : obligatoire ici.'
        )


def _add_niveau_lmd_param(item, required=False):
    function = item.get('function') or {}
    params = function.setdefault('parameters', {'type': 'object', 'properties': {}})
    props = params.setdefault('properties', {})
    props['niveau_lmd'] = {
        'type': 'string',
        'enum': NIVEAU_LMD_ENUM,
        'description': (
            'Niveau LMD : L1, L2, L3, M1, M2, D1–D3, BTS1/BTS2, DUT1/DUT2. '
            + (
                'Obligatoire pour créer une période en supérieur.'
                if required
                else 'Filtre optionnel (semestres du niveau).'
            )
        ),
    }
    if required:
        required_list = list(params.get('required') or [])
        if 'niveau_lmd' not in required_list:
            required_list.append('niveau_lmd')
        params['required'] = required_list
    description = function.get('description') or ''
    if 'niveau_lmd' not in description.lower() and 'niveau lmd' not in description.lower():
        extra = (
            ' Le niveau LMD (L1, M1…) est obligatoire.'
            if required
            else ' Tu peux filtrer par niveau LMD.'
        )
        function['description'] = description.rstrip('.') + extra


def tools_schema_for_context(ctx, master_schema):
    """Sous-ensemble de TOOLS_SCHEMA adapté au type d’établissement."""
    hidden = hidden_tools_for(ctx)
    schema = []
    for item in master_schema:
        name = (item.get('function') or {}).get('name')
        if not name or name in hidden:
            continue
        cloned = copy.deepcopy(item)
        if getattr(ctx, 'est_college_lycee', False) and name in (
            'creer_classe',
            'creer_professeur',
        ):
            _require_cycle_param(cloned)
        if getattr(ctx, 'est_superieur', False):
            if name == 'creer_periode':
                _add_niveau_lmd_param(cloned, required=True)
            elif name == 'get_periodes':
                _add_niveau_lmd_param(cloned, required=False)
        schema.append(cloned)
    return schema


def pages_visibles(ctx, pages):
    hidden_keys = set()
    if not getattr(ctx, 'est_superieur', False):
        hidden_keys.update(SUPERIEUR_PAGE_KEYS)
    if not cg_visible():
        hidden_keys.update(CG_PAGE_KEYS)
    if not hidden_keys:
        return pages
    return [page for page in pages if page.get('key') not in hidden_keys]


def prompt_addendum_for(ctx):
    """Complément de prompt (type + CG). Concaténé au prompt directeur statique."""
    parts = []
    if getattr(ctx, 'est_primaire', False):
        parts.append(
            "\nType d’établissement : primaire.\n"
            "- Parle d’élèves, d’instituteurs, de trimestres et de notes du primaire.\n"
            "- Interdit : filières, modules LMD, ECTS, semestres universitaires, spécialités.\n"
        )
    elif getattr(ctx, 'est_superieur', False):
        parts.append(
            "\nType d’établissement : enseignement supérieur.\n"
            "- Parle d’étudiants, de promotions, de semestres LMD, de filières et de modules.\n"
            "- Les périodes sont des semestres rattachés à un niveau (L1, M1…).\n"
            "- ECTS : get_ects_etudiant, get_ects_classe. N’invente aucun crédit : "
            "inscrits = maquette, validés seulement s’ils sont déjà calculés.\n"
            "- Maquette : get_modules_classe, get_structure_superieur "
            "(crédits, UE, semestre, classes liées).\n"
            "- Affecter un module : affecter_module_classe. "
            "Fixer les crédits : fixer_credits_module. Confirmation obligatoire.\n"
            "- Relevé : get_releve_ects (ouvre le bulletin / relevé existant).\n"
            "- creer_periode exige le niveau LMD et un semestre officiel "
            "(Semestre 1–2 pour L1, 3–4 pour L2, etc.).\n"
        )
    elif getattr(ctx, 'est_college_lycee', False):
        parts.append(
            "\nType d’établissement : collège et lycée dans le même espace.\n"
            "- Un seul assistant, pas deux espaces vocaux.\n"
            "- Pour créer une classe ou un professeur, demande le cycle "
            "(collège ou lycée) et envoie-le dans le paramètre cycle. "
            "Ne l’invente jamais.\n"
            "- Pédagogie : notes /20, trimestres. Pas d’ECTS ni de modules LMD.\n"
        )
    elif getattr(ctx, 'est_college', False):
        parts.append(
            "\nType d’établissement : collège.\n"
            "- Élèves, trimestres, notes /20, une matière par affectation.\n"
            "- Interdit : ECTS, modules LMD, filières universitaires.\n"
        )
    elif getattr(ctx, 'est_lycee', False):
        parts.append(
            "\nType d’établissement : lycée.\n"
            "- Élèves, trimestres, notes /20, une matière par affectation.\n"
            "- Interdit : ECTS, modules LMD, filières universitaires.\n"
        )
    else:
        parts.append(
            "\nType d’établissement : secondaire.\n"
            "- Pas d’ECTS ni de modules LMD.\n"
        )
    if getattr(ctx, 'est_college_lycee', False):
        parts.append(
            "- Pour les effectifs collège vs lycée, utilise get_repartition_cycles.\n"
        )
    parts.append(
        "\nPilotage (lecture) :\n"
        "- Tableau de bord : get_statistiques_pilotage "
        "(effectifs, présence, recouvrement, sanctions).\n"
        "- Réussite : get_taux_reussite (seuil de passage, période active par défaut).\n"
        "- Présence : get_taux_presence (établissement, classe ou élève).\n"
        "- Comparer deux périodes : get_comparatif_periodes.\n"
        "- N’invente aucun chiffre : appelle l’outil avant de parler.\n"
        "\nScolarité (nav visible, pas la comptabilité générale) :\n"
        "- Fiche élève : get_fiche_scolarite (charges, reçu, moratoire, parent).\n"
        "- Totaux : get_bilan_scolarite. Liste : get_impayes "
        "(classe, statut, ancienneté 0-30 / 31-60 / 61+).\n"
        "- Reçu : ouvrir_recu (numéro REC-… ou dernier paiement).\n"
        "- Moratoires : get_moratoires (création déjà via creer_moratoire).\n"
        "- Recalcul statuts : verifier_statuts_paiement (confirmation).\n"
        "- Remises fratrie : synchroniser_remises_fratrie (confirmation).\n"
        "\nPédagogie :\n"
        "- Notes d’une classe : get_notes_classe. Moyennes : get_moyennes_classe.\n"
        "- Bulletin d’un élève : get_bulletin_eleve (ouvre l’URL, ne génère pas de PDF).\n"
        "- Impression classe : imprimer_bulletins_classe.\n"
        "- Élèves sous le seuil : get_eleves_difficulte.\n"
        "- Justifications en attente : get_justifications_notes ; "
        "traiter_justification (accepter / refuser, confirmation).\n"
        "- Coefficients : get_coefficients ; configurer_coefficient (confirmation).\n"
        "- Évaluations : get_evaluations. Moyenne annuelle : calculer_moyenne_annuelle.\n"
        "\nRH (vacataires, pas de bulletins permanents) :\n"
        "- Dossier : get_dossier_employe (contrat, salaire, CNSS, RIB, tarif horaire).\n"
        "- Modifier le dossier : modifier_dossier_employe (confirmation). "
        "N’invente jamais de charges CSS/IPRES.\n"
        "- Volume horaire : get_volume_horaire (semaine, mois ou année).\n"
        "- Absences prof : get_absences_professeur ; "
        "supprimer_absence_professeur (confirmation).\n"
        "- Fiche de paie vacataire déjà marquée : ouvrir_fiche_paie "
        "(ouvre l’URL existante). Pas de bulletin CDI.\n"
    )
    if getattr(ctx, 'est_superieur', False):
        parts.append(
            "- get_taux_reussite peut ajouter des crédits validés "
            "seulement s’ils sont déjà calculés. N’invente pas d’ECTS.\n"
            "- Pour les crédits d’un étudiant ou d’une promo, "
            "préfère get_ects_etudiant / get_ects_classe.\n"
        )
    if not cg_visible():
        parts.append(
            "\nComptabilité générale : indisponible.\n"
            "- Tu n’as aucun outil de plan comptable, journal, grand livre, "
            "bilan SYSCOHADA, fournisseur ou clôture.\n"
            "- La scolarité (paiements élèves, impayés, caisse du mois) reste autorisée "
            "si tes outils la proposent.\n"
            "- N’ouvre pas et ne promets pas le hub de comptabilité générale.\n"
        )
    return ''.join(parts)


def _permission_denied_payload():
    return {
        'erreur': (
            "Vous n’avez pas l’autorisation d’utiliser cette action. "
            "Demandez au directeur de vous l’accorder."
        )
    }


def tool_permission_error(ctx, name, source=None):
    """None si autorisé, sinon dict d’erreur. Le directeur (sans personnel) passe toujours."""
    if getattr(ctx, 'persona', 'directeur') != 'directeur':
        return None
    hidden = hidden_tools_for(ctx)
    if name in hidden:
        if name in CG_TOOLS:
            return {'erreur': 'La comptabilité générale n’est pas disponible.'}
        return {'erreur': 'Cet outil n’est pas proposé pour ce type d’établissement.'}
    personnel = getattr(ctx, 'personnel', None)
    if personnel is None:
        return None
    perm = TOOL_PERMISSIONS.get(name)
    if perm is None:
        return None
    from school_admin.utils.decorators_permissions import check_permission

    keys = perm if isinstance(perm, (list, tuple)) else (perm,)
    if any(check_permission(personnel, key) for key in keys):
        return None
    logger.info(
        "Assistant: refus permission tool=%s source=%s personnel=%s",
        name,
        source,
        getattr(personnel, 'pk', None),
    )
    return _permission_denied_payload()


def tool_permission_error_for_search(ctx, source):
    mapped = CHERCHER_EN_BASE_SOURCES.get(source)
    if not mapped:
        return None
    return tool_permission_error(ctx, mapped, source=source)
