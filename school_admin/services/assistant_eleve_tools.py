"""
Outils assistant élève — Elv0 : blocage périmètre (schéma vide).
"""
from __future__ import annotations

from school_admin.services.assistant_eleve_scope import assert_self_only
from school_admin.services.assistant_parent_schema import PARENT_TOOL_NAMES_ALL

ELEVE_TOOL_NAMES = frozenset()

_FORBIDDEN_PREFIXES = (
    'get_effectifs',
    'rechercher_eleves',
    'get_comptabilite',
    'get_caisse',
    'get_volume_horaire',
    'get_liaisons',
    'get_preinscriptions',
    'creer_',
    'modifier_',
    'supprimer_',
    'publier_',
    'enregistrer_paiement',
    'affecter_',
    'inscrire_',
    'get_plan_comptable',
    'get_notes_classe',
    'get_devoirs_classe',
    'get_absences_classe',
    'get_mes_classes',
    'get_statistiques',
    'get_structure_superieur',
    'get_examens',
    'justifier_absence',
    'noter_',
)


def get_eleve_tools_schema(_ctx=None):
    """Elv0 — aucun outil exposé à Gemini."""
    return []


def execute_eleve_tool(ctx, name, arguments):
    args = arguments if isinstance(arguments, dict) else {}
    lowered = (name or '').strip().lower()

    if lowered in PARENT_TOOL_NAMES_ALL:
        return {
            'erreur': 'Cet outil est réservé aux parents, pas à ton espace élève.',
            'statut': 'hors_perimetre',
        }

    for blocked in _FORBIDDEN_PREFIXES:
        if lowered == blocked or lowered.startswith(blocked):
            return {
                'erreur': "Cette action est réservée à l'établissement ou aux enseignants.",
                'statut': 'hors_perimetre',
            }

    eleve_id = args.get('eleve_id') or args.get('id')
    denied = assert_self_only(ctx, eleve_id)
    if denied:
        return denied

    if lowered in ELEVE_TOOL_NAMES:
        return {'erreur': f'Outil « {name} » indisponible pour le moment.'}

    return {
        'erreur': f'Outil « {name} » non disponible pour les élèves (Elv0).',
        'statut': 'outil_inconnu',
    }
