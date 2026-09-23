"""
Outils lecture P7 — justifications de notes (consultation prof).
"""
from __future__ import annotations

from django.db.models import Q

from school_admin.services.assistant_enseignant_scope import classe_ids_for_prof

ENSEIGNANT_COMPLEMENTS_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'get_justifications_notes',
            'description': (
                'Liste vos demandes de justification / correction de notes '
                '(lecture seule, périmètre affectations).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'statut': {'type': 'string'},
                    'eleve': {'type': 'string'},
                    'classe': {'type': 'string'},
                },
            },
        },
    },
]


def tool_get_justifications_notes(ctx, args):
    from school_admin.model.justification_note_model import JustificationNote
    from school_admin.services.assistant_enseignant_scope import (
        find_classe_prof,
        find_eleve_prof,
    )

    qs = JustificationNote.objects.filter(
        professeur=ctx.professeur,
        etablissement=ctx.etablissement,
    ).select_related('eleve', 'classe', 'matiere')
    class_ids = classe_ids_for_prof(ctx)
    if class_ids:
        qs = qs.filter(classe_id__in=class_ids)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    statut = (args.get('statut') or '').strip().lower()
    if statut:
        qs = qs.filter(statut__icontains=statut)
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if classe:
        qs = qs.filter(classe=classe)
    eleve = find_eleve_prof(ctx, args.get('eleve') or args.get('query') or '', classe)
    if eleve:
        qs = qs.filter(eleve=eleve)
    items = [
        {
            'eleve': j.eleve.nom_complet if j.eleve_id else '',
            'classe': j.classe.nom if j.classe_id else '',
            'matiere': j.matiere.nom if j.matiere_id else '',
            'statut': j.statut,
            'motif': (j.motif or '')[:120],
            'ancienne_note': str(j.ancienne_note) if j.ancienne_note is not None else None,
            'nouvelle_note': str(j.nouvelle_note) if j.nouvelle_note is not None else None,
        }
        for j in qs.order_by('-date_creation')[:12]
    ]
    return {'justifications': items, 'nb': len(items)}


def extend_enseignant_schema_for_complements(schema, ctx):
    if not ctx or getattr(ctx, 'professeur', None) is None:
        return schema
    names = {
        item.get('function', {}).get('name')
        for item in schema
        if item.get('function')
    }
    extra = [
        item
        for item in ENSEIGNANT_COMPLEMENTS_TOOLS_SCHEMA
        if item.get('function', {}).get('name') not in names
    ]
    return schema + extra if extra else schema


def register_complements_tool_handlers(handlers: dict):
    handlers['get_justifications_notes'] = tool_get_justifications_notes
