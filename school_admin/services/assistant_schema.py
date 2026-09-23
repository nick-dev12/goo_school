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
}

CHERCHER_EN_BASE_SOURCES = {
    'effectifs': 'get_effectifs',
    'notes': 'get_notes_eleve',
    'presences': 'get_presences',
    'sanctions': 'get_sanctions',
    'caisse': 'get_caisse',
    'volume_horaire': 'get_volume_horaire',
    'comptabilite': 'get_comptabilite',
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
            "- Les périodes sont des semestres, souvent rattachés à un niveau (L1, M1…).\n"
            "- N’invente pas de crédits ECTS : tu n’as pas encore d’outil pour les lire.\n"
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
