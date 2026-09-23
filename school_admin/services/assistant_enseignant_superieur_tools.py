"""
Tools LMD lecture seule pour l'assistant enseignant (promotions affectees).
"""
from __future__ import annotations

from decimal import Decimal

from school_admin.services.assistant_enseignant_scope import (
    ensure_classe_access,
    ensure_eleve_access,
    find_classe_prof,
    find_eleve_prof,
)
from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION
from school_admin.services.assistant_superieur import (
    NIVEAU_LMD_ENUM,
    _ects_par_semestre,
    _ects_pour_eleve,
    _find_periode,
    _maquette_qs,
    _require_superieur,
    _safe,
    _serialize_module_classe,
    normalize_niveau_lmd,
)

MODULES_LIMIT = 40


def tool_get_modules_classe(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    classe = find_classe_prof(ctx, args.get('classe') or args.get('query') or '')
    if not classe:
        return {'erreur': 'Indiquez une de vos promotions.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    periode = None
    if args.get('periode'):
        niveau = normalize_niveau_lmd(args.get('niveau_lmd')) or classe.niveau_lmd
        periode = _find_periode(ctx, args.get('periode'), niveau_lmd=niveau)
    qs = _maquette_qs(classe)
    if periode:
        qs = qs.filter(periode=periode)
    items = [
        _serialize_module_classe(mc)
        for mc in qs.order_by('numero_ue', 'module__nom')[:MODULES_LIMIT]
    ]
    return {
        'classe': classe.nom,
        'niveau_lmd': classe.niveau_lmd or None,
        'nb': len(items),
        'credits_total': _safe(
            sum(Decimal(str(item['credits'] or 0)) for item in items)
        ),
        'modules': items,
        'message': f"{len(items)} module(s) pour {classe.nom}.",
    }


def tool_get_credits_etudiant(ctx, args):
    denied = _require_superieur(ctx)
    if denied:
        return denied
    args = args if isinstance(args, dict) else {}
    query = (args.get('query') or args.get('etudiant') or args.get('eleve') or '').strip()
    if not query:
        return {'erreur': 'Indiquez l’étudiant dont vous voulez les crédits.'}
    eleve = find_eleve_prof(ctx, query)
    if not eleve:
        return {'erreur': f'Étudiant « {query} » introuvable dans vos promotions.'}
    if err := ensure_eleve_access(ctx, eleve):
        return err
    classe = eleve.classe
    niveau = normalize_niveau_lmd(args.get('niveau_lmd')) or (
        classe.niveau_lmd if classe else None
    )
    periode = None
    if args.get('periode'):
        periode = _find_periode(ctx, args.get('periode'), niveau_lmd=niveau)
        if not periode:
            return {'erreur': f'Période introuvable pour « {args.get("periode")} ».'}
    totaux = _ects_pour_eleve(ctx, eleve, periode=periode)
    return {
        'etudiant': eleve.nom_complet,
        'classe': classe.nom if classe else None,
        'niveau_lmd': niveau,
        'periode': periode.nom_periode if periode else None,
        'invente': False,
        **totaux,
        'par_semestre': _ects_par_semestre(ctx, eleve),
        'message': (
            f"{eleve.nom_complet} : {totaux.get('credits_valides') or 0} crédits validés "
            f"sur {totaux.get('credits_inscrits') or 0} inscrits."
        ),
    }


ENSEIGNANT_SUPERIEUR_TOOL_HANDLERS = {
    'get_modules_classe': tool_get_modules_classe,
    'get_credits_etudiant': tool_get_credits_etudiant,
}

ENSEIGNANT_SUPERIEUR_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_modules_classe',
            'description': (
                'Modules LMD d’une de vos promotions : nom, crédits ECTS, '
                'numéro d’UE, semestre. Lecture seule, périmètre professeur.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                    'periode': {
                        'type': 'string',
                        'description': 'Semestre (ex. Semestre 1) — optionnel.',
                    },
                    'niveau_lmd': {'type': 'string', 'enum': NIVEAU_LMD_ENUM},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_credits_etudiant',
            'description': (
                'Crédits ECTS d’un étudiant de vos promotions : inscrits, validés, '
                'restants, détail par semestre. Ne jamais inventer de crédits.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Nom ou matricule'},
                    'etudiant': {'type': 'string'},
                    'eleve': {'type': 'string'},
                    'periode': {'type': 'string'},
                    'niveau_lmd': {'type': 'string', 'enum': NIVEAU_LMD_ENUM},
                },
                'required': ['query'],
            },
        },
    },
]


def extend_enseignant_schema_for_superieur(schema, ctx):
    if not getattr(ctx, 'est_superieur', False):
        return schema
    names = {
        item.get('function', {}).get('name')
        for item in schema
        if item.get('function')
    }
    extra = [
        item
        for item in ENSEIGNANT_SUPERIEUR_TOOLS_SCHEMA
        if item.get('function', {}).get('name') not in names
    ]
    return schema + extra if extra else schema
