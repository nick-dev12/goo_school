"""
Outils assistant parent — Par0/Par1 : blocage des tools direction ; Par2+ ajoutera la lecture.
"""
from school_admin.services.assistant_parent_scope import assert_eleve_autorise

# Tools direction / enseignant / CG — jamais exposés au persona parent (garde-fou Par0).
_FORBIDDEN_TOOL_PREFIXES = (
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
)


def get_parent_tools_schema():
    """Par1 : schéma vide — pas de tools lecture avant Par2."""
    return []


def execute_parent_tool(ctx, name, arguments):
    """Refuse tout appel outil côté parent jusqu'à Par2 (sauf vérif scope si eleve_id passé)."""
    args = arguments if isinstance(arguments, dict) else {}

    eleve_id = args.get('eleve_id') or args.get('id')
    parent = getattr(ctx, 'parent', None)
    if eleve_id and parent:
        denied = assert_eleve_autorise(parent, eleve_id)
        if denied:
            return denied

    lowered = (name or '').strip().lower()
    for blocked in _FORBIDDEN_TOOL_PREFIXES:
        if lowered == blocked or lowered.startswith(blocked):
            return {
                'erreur': "Cette action est réservée à l'établissement, pas aux parents.",
                'statut': 'hors_perimetre',
            }

    return {
        'erreur': (
            "Je peux déjà discuter avec vous en français et en wolof. "
            "La consultation des notes, absences et scolarité arrive très bientôt."
        ),
        'statut': 'par2_requis',
        'outil': name,
    }
