"""
Schéma Gemini parent — filtrage par type d'établissement de l'enfant (Par4).
"""
from __future__ import annotations

from school_admin.services.assistant_schema import classify_etablissement

# Outils Par2
_BASE_TOOLS = (
    'get_mes_enfants',
    'select_enfant',
    'get_resume_enfant',
    'get_annonces',
    'get_notifications',
    'lister_pages',
    'ouvrir_page',
)

# Par4 — suivi scolaire
_SCOLAIRE_TOOLS = (
    'get_notes_enfant',
    'get_bulletin_enfant',
    'get_devoirs_enfant',
    'get_absences_enfant',
    'get_sanctions_enfant',
    'get_convocations_enfant',
    'get_convocations_famille',
    'get_emploi_enfant',
)

_FINANCE_TOOLS = (
    'get_scolarite_enfant',
    'get_scolarite_famille',
    'ouvrir_recu',
)

_WRITE_TOOLS = (
    'marquer_notification_lue',
    'demande_liaison_enfant',
)

PARENT_TOOL_NAMES_ALL = frozenset(
    _BASE_TOOLS + _SCOLAIRE_TOOLS + _FINANCE_TOOLS + _WRITE_TOOLS
)

# Réservé aux établissements « classiques » (primaire + collège/lycée) : pas de bulletin LMD dédié
_BULLETIN_STANDARD_ONLY = frozenset()

# Réservé supérieur (extensions futures) — vide en Par4, bulletin LMD via même tool
_SUPERIEUR_EXTRA = frozenset()


def _flags_for_parent_ctx(ctx):
    if ctx is None:
        return classify_etablissement(None)
    if getattr(ctx, 'eleve_consulte', None):
        etab = ctx.eleve_consulte.etablissement
        return classify_etablissement(etab)
    flags = {
        'est_superieur': False,
        'est_primaire': False,
        'est_college': False,
        'est_lycee': False,
        'est_college_lycee': False,
        'cycle_requis': False,
    }
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return flags
    from school_admin.services.assistant_parent_scope import liens_valides_qs

    any_link = False
    for lien in liens_valides_qs(parent).filter(eleve__actif=True):
        any_link = True
        etab = lien.eleve.etablissement if lien.eleve_id else None
        f = classify_etablissement(etab)
        for key in flags:
            flags[key] = flags[key] or f.get(key, False)
    if not any_link:
        return classify_etablissement(getattr(ctx, 'etablissement', None))
    return flags


def allowed_tool_names(ctx):
    flags = _flags_for_parent_ctx(ctx)
    names = (
        set(_BASE_TOOLS)
        | set(_SCOLAIRE_TOOLS)
        | set(_FINANCE_TOOLS)
        | set(_WRITE_TOOLS)
    )
    if flags.get('est_superieur') and not (
        flags.get('est_primaire') or flags.get('est_college') or flags.get('est_lycee')
    ):
        names -= _BULLETIN_STANDARD_ONLY
    if not flags.get('est_superieur'):
        names -= _SUPERIEUR_EXTRA
    return names


def _mixed_type_flags(flags):
    kinds = sum(
        1
        for key in ('est_primaire', 'est_college', 'est_lycee', 'est_superieur')
        if flags.get(key)
    )
    return kinds > 1


def _notes_description(flags):
    base = (
        'Notes publiées et moyennes par matière pour un enfant lié. '
        'Toujours appeler avant de citer des chiffres.'
    )
    if _mixed_type_flags(flags):
        return (
            f'{base} Adapter au type d’établissement de l’enfant '
            '(primaire, collège/lycée ou supérieur/LMD étudiant — pas le pilotage direction).'
        )
    if flags.get('est_superieur'):
        return f'{base} (supérieur / LMD étudiant : moyennes semestre).'
    if flags.get('est_primaire'):
        return f'{base} (primaire : CM/CP, évaluations primaires).'
    if flags.get('est_college') or flags.get('est_lycee') or flags.get('est_college_lycee'):
        return f'{base} (collège/lycée : notes par matière et coefficients).'
    return base


def _bulletin_description(flags):
    base = 'État de publication du bulletin et moyenne générale (pas le PDF).'
    if _mixed_type_flags(flags):
        return f'{base} Bulletin élève/étudiant lié — pas publication direction.'
    if flags.get('est_superieur'):
        return f'{base} (bulletin étudiant supérieur / LMD).'
    return base


def _schema_definitions(flags=None):
    flags = flags or {}

    return {
        'get_notes_enfant': {
            'description': _notes_description(flags),
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_bulletin_enfant': {
            'description': _bulletin_description(flags),
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_devoirs_enfant': {
            'description': 'Exercices à rendre et évaluations à venir (semaine par défaut).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                    'periode': {'type': 'string', 'description': 'semaine ou quinze_jours'},
                },
            },
        },
        'get_absences_enfant': {
            'description': 'Totaux absences/retards et derniers événements.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_sanctions_enfant': {
            'description': 'Sanctions disciplinaires récentes de l’enfant.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_convocations_enfant': {
            'description': 'Convocations à venir pour un enfant (espace enfant ou eleve_id).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                    'a_venir': {'type': 'boolean'},
                },
            },
        },
        'get_convocations_famille': {
            'description': 'Convocations à venir pour tous les enfants liés (hub parent).',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_emploi_enfant': {
            'description': 'Créneaux de l’emploi du temps publié de la classe active.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_scolarite_enfant': {
            'description': (
                'Reste dû, échéances et reçus récents pour un enfant lié '
                '(resume_dette_eleve). Toujours appeler avant de citer un montant.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve_id': {'type': 'integer'},
                    'nom': {'type': 'string'},
                },
            },
        },
        'get_scolarite_famille': {
            'description': (
                'Hub parent : dette totale tous enfants liés + prochaine échéance la plus proche.'
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
        'ouvrir_recu': {
            'description': (
                'Ouvre le reçu officiel parent (lecture seule) si le paiement appartient à un enfant lié.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'paiement_id': {'type': 'integer'},
                    'ouvrir': {'type': 'boolean'},
                },
                'required': ['paiement_id'],
            },
        },
    }


def build_parent_tool_schemas(ctx=None):
    from school_admin.services.assistant_parent_actions import build_parent_action_schemas
    from school_admin.services.assistant_parent_tools import PAR2_GEMINI_TOOLS

    flags = _flags_for_parent_ctx(ctx)
    base = {item['function']['name']: item for item in PAR2_GEMINI_TOOLS}
    extras = _schema_definitions(flags)
    actions = {item['function']['name']: item for item in build_parent_action_schemas()}
    allowed = allowed_tool_names(ctx)
    out = []
    for name in sorted(allowed):
        if name in base:
            out.append(base[name])
        elif name in actions:
            out.append(actions[name])
        elif name in extras:
            spec = extras[name]
            out.append({
                'type': 'function',
                'function': {
                    'name': name,
                    'description': spec['description'],
                    'parameters': spec.get('parameters') or {'type': 'object', 'properties': {}},
                },
            })
    return out
