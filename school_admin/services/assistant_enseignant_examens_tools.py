"""
Tools examens (college / lycee) pour l'assistant enseignant — lecture seule + actions separees.
"""
from __future__ import annotations

from django.db.models import Count, Q

from school_admin.services.assistant_enseignant_scope import (
    classe_ids_for_prof,
    ensure_classe_access,
    ensure_eleve_access,
    find_classe_prof,
    find_eleve_prof,
    matiere_ids_for_prof,
)
from school_admin.services.assistant_examens import (
    NOTES_LIMIT,
    _clean_query,
    _ELEVE_NOISE,
    _note_item,
    _session_item,
)
from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION

SEARCH_LIMIT = 24


def _examens_allowed(ctx):
    if getattr(ctx, 'persona', '') != 'enseignant':
        return False
    if getattr(ctx, 'est_superieur', False) or getattr(ctx, 'est_primaire', False):
        return False
    return True


def _require_examens(ctx):
    if not _examens_allowed(ctx):
        return {
            'erreur': 'Les outils examens ne sont pas disponibles pour ce profil.',
        }
    return None


def _sessions_qs_prof(ctx):
    from school_admin.model.session_examen_model import SessionExamen

    denied = _require_examens(ctx)
    if denied:
        return SessionExamen.objects.none()
    class_ids = classe_ids_for_prof(ctx)
    if not class_ids:
        return SessionExamen.objects.none()
    matiere_ids = matiere_ids_for_prof(ctx)
    qs = SessionExamen.objects.filter(
        etablissement=ctx.etablissement,
        actif=True,
        classes__id__in=class_ids,
    ).distinct()
    if matiere_ids:
        qs = qs.filter(matieres__id__in=matiere_ids).distinct()
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire)
            | Q(annee_scolaire__isnull=True)
        )
    return qs


def _find_session_prof(ctx, query):
    raw = (query or '').strip()
    if not raw:
        return None
    qs = _sessions_qs_prof(ctx)
    found = qs.filter(nom_examen__icontains=raw).order_by('-date_creation').first()
    if found:
        return found
    from school_admin.services.assistant_examens import _SESSION_NOISE

    cleaned = _clean_query(raw, _SESSION_NOISE)
    if cleaned and cleaned != raw:
        return qs.filter(nom_examen__icontains=cleaned).order_by('-date_creation').first()
    return None


def _notes_qs_prof(ctx):
    from school_admin.model.note_examen_model import NoteExamen

    class_ids = classe_ids_for_prof(ctx)
    matiere_ids = matiere_ids_for_prof(ctx)
    if not class_ids or not matiere_ids:
        return NoteExamen.objects.none()
    qs = NoteExamen.objects.filter(
        session_examen__etablissement=ctx.etablissement,
        actif=True,
        classe_id__in=class_ids,
        matiere_id__in=matiere_ids,
        professeur=ctx.professeur,
    ).select_related('eleve', 'session_examen', 'matiere', 'classe')
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    return qs


def tool_get_examens_prof(ctx, args):
    denied = _require_examens(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    qs = _sessions_qs_prof(ctx).select_related('periode').prefetch_related('classes')
    query = (args.get('query') or args.get('nom') or args.get('session') or '').strip()
    if query:
        session = _find_session_prof(ctx, query)
        if not session:
            return {'nb': 0, 'sessions': [], 'message': f'Aucune session « {query} » dans votre périmètre.'}
        qs = qs.filter(pk=session.pk)
    qs = qs.annotate(
        nb_creneaux=Count('creneaux', filter=Q(creneaux__actif=True)),
    ).order_by('-date_debut')[:SEARCH_LIMIT]
    items = []
    for session in qs:
        item = _session_item(session)
        item['classes'] = [
            c.nom for c in session.classes.all() if c.id in classe_ids_for_prof(ctx)
        ]
        items.append(item)
    return {
        'nb': len(items),
        'sessions': items,
        'message': f"{len(items)} session(s) d'examen pour vos classes." if items else None,
    }


def tool_get_notes_examen(ctx, args):
    denied = _require_examens(ctx)
    if denied:
        return denied
    from school_admin.model.note_examen_model import NoteExamen

    args = args if isinstance(args, dict) else {}
    session_query = (args.get('session') or args.get('nom_session') or '').strip()
    eleve_query = (args.get('eleve') or args.get('query') or '').strip()
    classe_query = (args.get('classe') or '').strip()

    session = _find_session_prof(ctx, session_query) if session_query else None
    if session_query and not session:
        return {'erreur': f'Session « {session_query} » introuvable.', 'nb': 0, 'notes': []}

    classe = None
    if classe_query:
        classe = find_classe_prof(ctx, classe_query)
        if not classe:
            return {
                'erreur': f'Classe « {classe_query} » introuvable dans vos affectations.',
                'nb': 0,
                'notes': [],
            }
        if err := ensure_classe_access(ctx, classe):
            return {**err, 'nb': 0, 'notes': []}

    eleve = None
    if eleve_query:
        eleve = find_eleve_prof(ctx, eleve_query, classe=classe)
        if not eleve:
            cleaned = _clean_query(eleve_query, _ELEVE_NOISE)
            if cleaned:
                eleve = find_eleve_prof(ctx, cleaned, classe=classe)
        if not eleve and eleve_query:
            return {
                'erreur': f'Élève « {eleve_query} » introuvable dans vos classes.',
                'nb': 0,
                'notes': [],
            }
        if eleve and (err := ensure_eleve_access(ctx, eleve)):
            return err

    qs = _notes_qs_prof(ctx)
    if session:
        qs = qs.filter(session_examen=session)
    if eleve:
        qs = qs.filter(eleve=eleve)
    if classe:
        qs = qs.filter(classe=classe)

    items = [_note_item(n) for n in qs.order_by('eleve__nom', 'matiere__nom')[:NOTES_LIMIT]]
    return {
        'nb': qs.count(),
        'notes': items,
        'session': session.nom_examen if session else None,
        'eleve': eleve.nom_complet if eleve else None,
        'classe': classe.nom if classe else None,
        'message': (
            None
            if items
            else 'Aucune note d\'examen pour ce filtre. N\'invente aucun chiffre.'
        ),
    }


def tool_ouvrir_noter_examen(ctx, args):
    denied = _require_examens(ctx)
    if denied:
        return denied
    from django.urls import reverse

    args = args if isinstance(args, dict) else {}
    classe = find_classe_prof(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indiquez une de vos classes.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    session = _find_session_prof(ctx, args.get('session') or args.get('nom') or '')
    if args.get('session') or args.get('nom'):
        if not session:
            return {'erreur': 'Session d\'examen introuvable pour vous.'}
    if session:
        url = reverse(
            'enseignant:noter_examen_session',
            args=[classe.id, session.id],
        )
        titre = f"Noter {classe.nom} — {session.nom_examen}"
    else:
        url = reverse('enseignant:noter_examen', args=[classe.id])
        titre = f"Noter examen — {classe.nom}"
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    return {
        'statut': 'ok',
        'url': url,
        'ouvrir': bool(ouvrir),
        'titre': titre,
        'classe': classe.nom,
        'session': session.nom_examen if session else None,
    }


ENSEIGNANT_EXAMENS_TOOL_HANDLERS = {
    'get_examens_prof': tool_get_examens_prof,
    'get_notes_examen': tool_get_notes_examen,
    'ouvrir_noter_examen': tool_ouvrir_noter_examen,
}

ENSEIGNANT_EXAMENS_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_examens_prof',
            'description': (
                'Sessions d\'examen concernant vos classes et matieres '
                '(nombre de creneaux, dates).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'session': {'type': 'string'},
                    'nom': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_examen',
            'description': (
                'Notes d\'examen deja saisies (vos matieres, vos classes). '
                'Ne jamais inventer de note.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'session': {'type': 'string'},
                    'eleve': {'type': 'string'},
                    'query': {'type': 'string'},
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_noter_examen',
            'description': (
                'Ouvre la page de saisie des notes d\'examen pour une classe '
                '(et optionnellement une session).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string'},
                    'session': {'type': 'string'},
                    'nom': {'type': 'string'},
                    'ouvrir': {'type': 'boolean'},
                },
                'required': ['classe'],
            },
        },
    },
]


EXAMEN_SCHEMA_NAMES = frozenset(
    {
        'get_examens_prof',
        'get_notes_examen',
        'ouvrir_noter_examen',
        'enregistrer_note_examen',
    }
)


def filter_enseignant_schema_examens(schema, ctx):
    """Retire les outils examens déjà injectés via les actions si profil non éligible."""
    if ctx is None or _examens_allowed(ctx):
        return schema
    return [
        item
        for item in schema
        if item.get('function', {}).get('name') not in EXAMEN_SCHEMA_NAMES
    ]


def extend_enseignant_schema_for_examens(schema, ctx):
    if not _examens_allowed(ctx):
        return filter_enseignant_schema_examens(schema, ctx)
    names = {
        item.get('function', {}).get('name')
        for item in schema
        if item.get('function')
    }
    extra = [
        item
        for item in ENSEIGNANT_EXAMENS_TOOLS_SCHEMA
        if item.get('function', {}).get('name') not in names
    ]
    return schema + extra if extra else schema
