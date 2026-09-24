"""
Schéma Gemini assistant élève — filtrage par type d'établissement.
"""
from __future__ import annotations

from school_admin.services.assistant_schema import classify_etablissement

ELEVE_NAV_TOOLS = frozenset({
    'get_mon_resume',
    'lister_pages',
    'ouvrir_page',
})

ELEVE_SCOLAIRE_TOOLS = frozenset({
    'get_annonces',
    'get_mes_notes',
    'get_mon_bulletin',
    'get_mes_devoirs',
    'get_mes_absences',
    'get_mes_sanctions',
    'get_mes_convocations',
    'get_mon_emploi',
    'get_mon_profil',
})

ELEVE_HIST_NOTIF_TOOLS = frozenset({
    'get_notifications',
    'get_mon_historique',
})

ELEVE_TOOL_NAMES_ALL = ELEVE_NAV_TOOLS | ELEVE_SCOLAIRE_TOOLS | ELEVE_HIST_NOTIF_TOOLS

# Elv7 : pas de marquer_notification_lue (arbitrage produit)
ELEVE_WRITE_TOOLS = frozenset()


def _flags_for_eleve_ctx(ctx):
    if ctx is None:
        return classify_etablissement(None)
    eleve = getattr(ctx, 'eleve', None)
    if eleve and getattr(eleve, 'etablissement', None):
        return classify_etablissement(eleve.etablissement)
    return classify_etablissement(getattr(ctx, 'etablissement', None))


def allowed_tool_names(ctx):
    """Elv2 — navigation uniquement ; vagues suivantes élargissent le set."""
    return set(ELEVE_NAV_TOOLS)


def _notes_description(flags):
    base = (
        'Tes notes publiées et moyennes par matière. '
        'Toujours appeler avant de citer des chiffres — tutoiement.'
    )
    if flags.get('est_superieur'):
        return f'{base} (supérieur / LMD étudiant).'
    if flags.get('est_primaire'):
        return f'{base} (primaire).'
    if flags.get('est_college') or flags.get('est_lycee') or flags.get('est_college_lycee'):
        return f'{base} (collège/lycée).'
    return base


def _bulletin_description(flags):
    base = 'État de publication de ton bulletin et moyenne générale (pas le PDF).'
    if flags.get('est_superieur'):
        return f'{base} (étudiant supérieur).'
    return base


def _schema_definitions(flags):
    return {
        'get_mon_resume': {
            'description': (
                'Synthèse légère de ton espace : classe, absences, notifications non lues '
                '(pas le détail des notes).'
            ),
            'parameters': {'type': 'object', 'properties': {}},
        },
        'lister_pages': {
            'description': 'Pages disponibles dans ton espace élève (navigation).',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'ouvrir_page': {
            'description': (
                'Ouvre une page de ton espace (devoirs, notes, bulletin, annonces, etc.). '
                'Utilise page_key ou query.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'page_key': {'type': 'string'},
                    'query': {'type': 'string'},
                    'ouvrir': {'type': 'boolean'},
                },
            },
        },
        'get_annonces': {
            'description': 'Annonces publiées pour les élèves de ton établissement.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'description': 'semaine, mois ou vide'},
                },
            },
        },
        'get_notifications': {
            'description': (
                'Tes notifications élève (liste, non lues). '
                'Option notification_id pour le détail d’une alerte.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'notification_id': {'type': 'integer'},
                    'non_lues_seulement': {'type': 'boolean'},
                },
            },
        },
        'get_mes_notes': {
            'description': _notes_description(flags),
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mon_bulletin': {
            'description': _bulletin_description(flags),
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mes_devoirs': {
            'description': 'Tes devoirs et échéances (semaine par défaut).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string', 'description': 'semaine ou quinze_jours'},
                },
            },
        },
        'get_mes_absences': {
            'description': 'Tes absences et retards (totaux et récents).',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mes_sanctions': {
            'description': 'Tes sanctions disciplinaires récentes.',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mes_convocations': {
            'description': 'Tes convocations à venir.',
            'parameters': {
                'type': 'object',
                'properties': {'a_venir': {'type': 'boolean'}},
            },
        },
        'get_mon_emploi': {
            'description': 'Créneaux de ton emploi du temps (classe active).',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mon_profil': {
            'description': 'Infos de ton compte (sans mot de passe).',
            'parameters': {'type': 'object', 'properties': {}},
        },
        'get_mon_historique': {
            'description': 'Années scolaires passées où tu as été inscrit (archives).',
            'parameters': {'type': 'object', 'properties': {}},
        },
    }


def build_eleve_tool_schemas(ctx=None):
    flags = _flags_for_eleve_ctx(ctx)
    defs = _schema_definitions(flags)
    allowed = allowed_tool_names(ctx)
    out = []
    for name in sorted(allowed):
        spec = defs.get(name)
        if not spec:
            continue
        out.append({
            'type': 'function',
            'function': {
                'name': name,
                'description': spec['description'],
                'parameters': spec.get('parameters') or {'type': 'object', 'properties': {}},
            },
        })
    return out
