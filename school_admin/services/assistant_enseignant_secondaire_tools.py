"""
Outils ORM pour l'assistant vocal enseignant secondaire et superieur.
"""
import json
import logging
import re
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone

from school_admin.services.assistant_enseignant_secondaire_actions import (
    ENSEIGNANT_SECONDAIRE_ACTION_SPECS,
    build_enseignant_secondaire_action_tool_schemas,
)
from school_admin.services.assistant_enseignant_scope import (
    affectations_qs,
    affectations_summary,
    classe_ids_for_prof,
    eleves_qs_for_prof,
    ensure_classe_access,
    ensure_eleve_access,
    find_classe_prof,
    find_eleve_prof,
    matiere_ids_for_prof,
)
from school_admin.services.assistant_search import CLASSE_PARAM_DESCRIPTION
from school_admin.services.assistant_tools import (
    NOTES_LIMIT,
    SEARCH_LIMIT,
    _safe_decimal,
    tool_emploi_du_temps,
    tool_periodes,
    tool_proposer_actions,
)

logger = logging.getLogger(__name__)


def tool_get_mes_classes(ctx, _args):
    items = affectations_summary(ctx)
    if not items:
        return {
            'message': 'Vous n’avez aucune classe affectée pour cette année.',
            'classes': [],
        }
    return {
        'message': f"Vous enseignez dans {len(items)} classe(s).",
        'classes': items,
    }


def tool_get_effectifs(ctx, args):
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    classe = find_classe_prof(ctx, args.get('classe') or '')
    class_ids = [classe.id] if classe else classe_ids_for_prof(ctx)
    if not class_ids:
        return {'erreur': 'Aucune classe affectée.'}
    if classe and (err := ensure_classe_access(ctx, classe)):
        return err
    qs = eleves_qs_for_prof(ctx, classe)
    stats = qs.aggregate(
        total=Count('id'),
        filles=Count('id', filter=Q(sexe='F')),
        garcons=Count('id', filter=Q(sexe='M')),
    )
    if classe:
        return {
            'classe': classe.nom,
            'total': stats['total'],
            'filles': stats['filles'],
            'garcons': stats['garcons'],
            'message': (
                f"{classe.nom} : {stats['total']} élèves, "
                f"{stats['filles']} filles et {stats['garcons']} garçons."
            ),
        }
    if ctx.annee_scolaire:
        total = InscriptionEleve.objects.filter(
            classe_id__in=class_ids,
            annee_scolaire=ctx.annee_scolaire,
        ).count()
    else:
        total = qs.count()
    return {
        'nb_classes': len(class_ids),
        'total_eleves': total,
        'message': f"{total} élèves répartis dans {len(class_ids)} classes.",
    }


def tool_rechercher_eleves(ctx, args):
    query = (args.get('query') or '').strip()
    classe = find_classe_prof(ctx, args.get('classe') or '')
    qs = eleves_qs_for_prof(ctx, classe).select_related('classe')
    if query:
        from school_admin.services.assistant_tools import _eleve_name_filter

        qs = qs.filter(_eleve_name_filter(query))
    items = [
        {
            'nom': e.nom_complet,
            'matricule': e.matricule_eleve,
            'classe': e.classe.nom if e.classe_id else None,
        }
        for e in qs.order_by('nom', 'prenom')[:SEARCH_LIMIT]
    ]
    return {'eleves': items, 'trouve': bool(items)}


def tool_get_evaluations_classe(ctx, args):
    from school_admin.model.evaluation_model import Evaluation

    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return {'erreur': 'Précisez la classe.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    periode = None
    periode_q = (args.get('periode') or '').strip()
    if periode_q:
        from school_admin.model.periode_model import PeriodeScolaire

        periode = PeriodeScolaire.objects.filter(
            etablissement=ctx.etablissement,
            nom_periode__icontains=periode_q,
        ).first()
    qs = Evaluation.objects.filter(
        classe=classe,
        professeur=ctx.professeur,
        actif=True,
    ).select_related('matiere', 'periode_scolaire')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    if periode:
        qs = qs.filter(periode_scolaire=periode)
    items = [
        {
            'id': ev.id,
            'titre': ev.titre,
            'matiere': ev.matiere.nom if ev.matiere_id else None,
            'date': ev.date_evaluation.isoformat() if ev.date_evaluation else None,
            'bareme': _safe_decimal(ev.bareme),
            'periode': ev.periode_scolaire.nom_periode if ev.periode_scolaire_id else None,
        }
        for ev in qs.order_by('-date_evaluation')[:SEARCH_LIMIT]
    ]
    return {'classe': classe.nom, 'evaluations': items}


def tool_get_notes_eleve(ctx, args):
    from school_admin.model.evaluation_model import Note

    eleve = find_eleve_prof(ctx, args.get('query') or args.get('eleve') or '')
    if not eleve:
        return {'erreur': 'Élève introuvable dans vos classes.'}
    qs = Note.objects.filter(
        eleve=eleve,
        evaluation__professeur=ctx.professeur,
    ).select_related('evaluation', 'evaluation__matiere')
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(evaluation__annee_scolaire=ctx.annee_scolaire)
            | Q(evaluation__annee_scolaire__isnull=True)
        )
    notes = [
        {
            'evaluation': n.evaluation.titre if n.evaluation_id else None,
            'matiere': (
                n.evaluation.matiere.nom
                if n.evaluation_id and n.evaluation.matiere_id
                else None
            ),
            'note': _safe_decimal(n.note),
            'statut': n.statut_publication,
        }
        for n in qs.order_by('-id')[:NOTES_LIMIT]
    ]
    return {'eleve': eleve.nom_complet, 'notes': notes}


def tool_get_notes_classe(ctx, args):
    from school_admin.model.evaluation_model import Note

    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return {'erreur': 'Précisez la classe.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    eval_q = (args.get('evaluation') or '').strip()
    qs = Note.objects.filter(
        evaluation__classe=classe,
        evaluation__professeur=ctx.professeur,
    ).select_related('eleve', 'evaluation')
    if eval_q:
        qs = qs.filter(evaluation__titre__icontains=eval_q)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(evaluation__annee_scolaire=ctx.annee_scolaire)
            | Q(evaluation__annee_scolaire__isnull=True)
        )
    items = [
        {
            'eleve': n.eleve.nom_complet,
            'evaluation': n.evaluation.titre,
            'note': _safe_decimal(n.note),
        }
        for n in qs.order_by('eleve__nom')[:SEARCH_LIMIT]
    ]
    return {'classe': classe.nom, 'notes': items}


def tool_get_eleves_difficulte(ctx, args):
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    periode = None
    if args.get('periode_id'):
        from school_admin.model.periode_model import PeriodeScolaire

        periode = PeriodeScolaire.objects.filter(pk=args['periode_id']).first()
    seuil = float(args.get('seuil') or 9)
    matiere_ids = matiere_ids_for_prof(ctx)
    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        est_moyenne_generale=False,
        matiere_id__in=matiere_ids,
        moyenne_matiere__lt=seuil,
        moyenne_matiere__isnull=False,
    ).select_related('eleve', 'matiere')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    if periode:
        qs = qs.filter(periode=periode)
    eleve_ids = set(eleves_qs_for_prof(ctx).values_list('id', flat=True))
    qs = qs.filter(eleve_id__in=eleve_ids)
    items = [
        {
            'eleve': m.eleve.nom_complet,
            'matiere': m.matiere.nom if m.matiere_id else None,
            'moyenne': _safe_decimal(m.moyenne_matiere),
        }
        for m in qs.order_by('moyenne_matiere')[:SEARCH_LIMIT]
    ]
    label = ctx.libelle_eleve or 'eleve'
    return {
        'seuil': seuil,
        'nb_eleves': len(items),
        'eleves': items,
        'message': f"{len(items)} {label}(s) avec moyenne inferieure a {seuil}.",
    }


def tool_get_exercices_maison(ctx, args):
    from school_admin.model.exercice_maison_model import ExerciceMaison

    classe = find_classe_prof(ctx, args.get('classe') or '')
    qs = ExerciceMaison.objects.filter(
        professeur=ctx.professeur,
        actif=True,
        classe_id__in=classe_ids_for_prof(ctx),
    ).select_related('classe', 'matiere')
    if classe:
        if err := ensure_classe_access(ctx, classe):
            return err
        qs = qs.filter(classe=classe)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    items = [
        {
            'titre': ex.titre,
            'classe': ex.classe.nom if ex.classe_id else None,
            'matiere': ex.matiere.nom if ex.matiere_id else None,
            'date_rendu': ex.date_rendu.isoformat() if ex.date_rendu else None,
        }
        for ex in qs.order_by('-date_rendu')[:SEARCH_LIMIT]
    ]
    return {'exercices': items, 'nb': len(items)}


def tool_get_presences(ctx, args):
    from school_admin.model.presence_model import Presence

    jours = int(args.get('jours') or 7)
    jours = max(1, min(jours, 31))
    since = timezone.now().date() - timedelta(days=jours)
    class_ids = classe_ids_for_prof(ctx)
    qs = Presence.objects.filter(
        etablissement=ctx.etablissement,
        classe_id__in=class_ids,
        date__gte=since,
    )
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = find_eleve_prof(ctx, query)
        if not eleve:
            return {'erreur': f'Élève « {query} » introuvable.'}
        qs = qs.filter(eleve=eleve)
        details = [
            {
                'date': p.date.isoformat(),
                'statut': p.get_statut_display(),
            }
            for p in qs.order_by('-date')[:20]
        ]
        return {'eleve': eleve.nom_complet, 'details': details}
    stats = list(qs.values('statut').annotate(nb=Count('id')))
    return {
        'periode_jours': jours,
        'totaux': {row['statut']: row['nb'] for row in stats},
    }


def tool_get_sanctions(ctx, args):
    from school_admin.model.sanction_model import Sanction

    class_ids = classe_ids_for_prof(ctx)
    qs = Sanction.objects.filter(
        etablissement=ctx.etablissement,
        classe_id__in=class_ids,
        professeur=ctx.professeur,
    ).select_related('eleve', 'classe')
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    query = (args.get('query') or args.get('eleve') or '').strip()
    if query:
        eleve = find_eleve_prof(ctx, query)
        if not eleve:
            return {'erreur': 'Élève introuvable.'}
        qs = qs.filter(eleve=eleve)
    items = [
        {
            'eleve': s.eleve.nom_complet,
            'type': s.get_type_sanction_display(),
            'date': s.date_sanction.isoformat() if s.date_sanction else None,
            'raison': s.raison,
        }
        for s in qs.order_by('-date_sanction')[:SEARCH_LIMIT]
    ]
    return {'sanctions': items, 'nb': len(items)}


def tool_get_annonces(ctx, _args):
    from school_admin.model.annonce_model import Annonce

    qs = Annonce.objects.filter(
        etablissement=ctx.etablissement,
        statut='publiee',
    )
    if ctx.annee_scolaire:
        qs = qs.filter(Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True))
    items = [
        {'titre': a.titre, 'date': a.date_publication.isoformat() if a.date_publication else None}
        for a in qs.order_by('-date_publication')[:8]
    ]
    return {'annonces': items}


def tool_get_notifications(ctx, _args):
    from school_admin.model.notification_enseignant_model import NotificationEnseignant

    base_qs = NotificationEnseignant.objects.filter(professeur=ctx.professeur)
    nb_non_lues = base_qs.filter(est_lu=False).count()
    items = [
        {
            'titre': n.titre,
            'message': (n.message or '')[:200],
            'lu': n.est_lu,
        }
        for n in base_qs.order_by('-date_creation')[:10]
    ]
    return {'notifications': items, 'non_lues': nb_non_lues}


def tool_get_emploi_du_temps_prof(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    if not classe:
        return {'erreur': 'Précisez une de vos classes.'}
    if err := ensure_classe_access(ctx, classe):
        return err
    return tool_emploi_du_temps(ctx, {'classe': classe.nom})


def tool_ouvrir_classe(ctx, args):
    from django.urls import reverse

    query = (args.get('query') or args.get('classe') or '').strip()
    classe = find_classe_prof(ctx, query)
    if not classe:
        classes = list(affectations_qs(ctx)[:SEARCH_LIMIT])
        if len(classes) > 1:
            return {
                'statut': 'plusieurs',
                'suggestions': [
                    {
                        'nom': aff.classe.nom,
                        'url': reverse('enseignant:detail_classe', args=[aff.classe_id]),
                    }
                    for aff in classes
                ],
                'message': 'Plusieurs classes possibles.',
            }
        return {'erreur': 'Classe introuvable parmi vos affectations.'}
    url = reverse('enseignant:detail_classe', args=[classe.id])
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    nb_eleves = eleves_qs_for_prof(ctx, classe).count()
    return {
        'statut': 'ok',
        'nom': classe.nom,
        'id': classe.id,
        'classe_id': classe.id,
        'classe': classe.nom,
        'url': url,
        'ouvrir': bool(ouvrir),
        'titre': classe.nom,
        'nb_eleves': nb_eleves,
    }


def tool_lister_pages(_ctx, _args):
    from school_admin.services.assistant_pages_enseignant import list_pages

    return {
        'pages': [
            {'key': p['key'], 'titre': p['titre']}
            for p in list_pages()
        ],
    }


def tool_ouvrir_page(ctx, args):
    from school_admin.services.assistant_pages_enseignant import (
        find_page,
        page_url,
        related_pages,
    )

    page = find_page(args.get('page_key') or args.get('query'))
    if not page:
        return {'erreur': 'Page inconnue. Utilise lister_pages pour les clés valides.'}
    extra = {}
    if args.get('classe_id'):
        extra['classe_id'] = args['classe_id']
    elif args.get('classe'):
        classe = find_classe_prof(ctx, args.get('classe'))
        if classe:
            extra['classe_id'] = classe.id
    url = page_url(page, extra) or page.get('url')
    if not url:
        return {
            'erreur': 'Cette page nécessite une classe. Indiquez classe ou classe_id.',
            'key': page['key'],
        }
    ouvrir = args.get('ouvrir')
    if ouvrir is None:
        ouvrir = True
    return {
        'statut': 'ok',
        'key': page['key'],
        'titre': page['titre'],
        'url': url,
        'ouvrir': bool(ouvrir),
        'suggestions': related_pages(page['key']),
    }


def tool_chercher_en_base(ctx, args):
    question = (args.get('question') or args.get('query') or '').strip().lower()
    payload = {'classe': args.get('classe'), 'query': args.get('query') or question}

    if any(t in question for t in ('classe', 'affect', 'enseigne')):
        found = tool_get_mes_classes(ctx, args)
        return {'trouve': True, 'source': 'mes_classes', **found}
    if any(t in question for t in ('effectif', 'inscrit', 'fille', 'garçon', 'garcon', 'élève', 'eleve')):
        found = tool_get_effectifs(ctx, payload)
        return {'trouve': 'erreur' not in found, 'source': 'effectifs', **found}
    if any(t in question for t in ('note', 'moyenne', 'évaluation', 'evaluation')):
        if payload.get('query') and len(question.split()) <= 4:
            found = tool_get_notes_eleve(ctx, payload)
        else:
            found = tool_get_notes_classe(ctx, payload)
        return {'trouve': 'erreur' not in found, 'source': 'notes', **found}
    if any(t in question for t in ('difficult', 'faible')):
        found = tool_get_eleves_difficulte(ctx, payload)
        return {'trouve': True, 'source': 'difficulte', **found}
    if 'exercice' in question:
        found = tool_get_exercices_maison(ctx, payload)
        return {'trouve': True, 'source': 'exercices', **found}
    if any(t in question for t in ('absence', 'présence', 'presence', 'present')):
        found = tool_get_presences(ctx, payload)
        return {'trouve': True, 'source': 'presences', **found}
    if 'sanction' in question:
        found = tool_get_sanctions(ctx, payload)
        return {'trouve': 'erreur' not in found, 'source': 'sanctions', **found}
    if 'annonce' in question:
        found = tool_get_annonces(ctx, args)
        return {'trouve': True, 'source': 'annonces', **found}
    if 'période' in question or 'periode' in question or 'trimestre' in question:
        found = tool_periodes(ctx, args)
        return {'trouve': True, 'source': 'periodes', **found}
    if 'emploi' in question or 'edt' in question:
        found = tool_emploi_du_temps(ctx, payload)
        return {'trouve': 'erreur' not in found, 'source': 'emploi', **found}
    if 'notification' in question:
        found = tool_get_notifications(ctx, args)
        return {'trouve': True, 'source': 'notifications', **found}
    if not getattr(ctx, 'est_superieur', False) and not getattr(ctx, 'est_primaire', False):
        if 'examen' in question or 'composition' in question:
            from school_admin.services.assistant_enseignant_examens_tools import (
                tool_get_examens_prof,
                tool_get_notes_examen,
                tool_ouvrir_noter_examen,
            )

            if any(t in question for t in ('note', 'notes')):
                found = tool_get_notes_examen(ctx, payload)
                return {'trouve': 'erreur' not in found, 'source': 'notes_examen', **found}
            if any(t in question for t in ('noter', 'saisir', 'ouvrir')):
                found = tool_ouvrir_noter_examen(ctx, payload)
                return {'trouve': 'erreur' not in found, 'source': 'noter_examen', **found}
            found = tool_get_examens_prof(ctx, payload)
            return {'trouve': True, 'source': 'examens_prof', **found}
    if getattr(ctx, 'est_superieur', False):
        if any(t in question for t in ('module', 'maquette', 'ue ', ' ue', 'ects', 'credit')):
            if any(t in question for t in ('etudiant', 'eleve', 'etudiante')):
                found = tool_get_credits_etudiant(ctx, payload)
            else:
                found = tool_get_modules_classe(ctx, payload)
            return {'trouve': 'erreur' not in found, 'source': 'lmd', **found}
        if 'semestre' in question and 'note' not in question:
            found = tool_periodes(ctx, args)
            return {'trouve': True, 'source': 'periodes', **found}
    return {'trouve': False, 'message': 'Je n’ai pas reconnu le type de donnée. Précisez notes, présences, classes, etc.'}


def tool_get_modules_classe(ctx, args):
    from school_admin.services.assistant_enseignant_superieur_tools import (
        tool_get_modules_classe as _impl,
    )

    return _impl(ctx, args)


def tool_get_credits_etudiant(ctx, args):
    from school_admin.services.assistant_enseignant_superieur_tools import (
        tool_get_credits_etudiant as _impl,
    )

    return _impl(ctx, args)


def _merge_examens_handlers():
    from school_admin.services.assistant_enseignant_examens_tools import (
        ENSEIGNANT_EXAMENS_TOOL_HANDLERS,
    )

    return ENSEIGNANT_EXAMENS_TOOL_HANDLERS


ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS = {
    'chercher_en_base': tool_chercher_en_base,
    'get_modules_classe': tool_get_modules_classe,
    'get_credits_etudiant': tool_get_credits_etudiant,
    'proposer_actions': tool_proposer_actions,
    'get_mes_classes': tool_get_mes_classes,
    'get_effectifs': tool_get_effectifs,
    'rechercher_eleves': tool_rechercher_eleves,
    'get_evaluations_classe': tool_get_evaluations_classe,
    'get_notes_eleve': tool_get_notes_eleve,
    'get_notes_classe': tool_get_notes_classe,
    'get_eleves_difficulte': tool_get_eleves_difficulte,
    'get_exercices_maison': tool_get_exercices_maison,
    'get_presences': tool_get_presences,
    'get_sanctions': tool_get_sanctions,
    'get_periodes': tool_periodes,
    'get_emploi_du_temps': tool_get_emploi_du_temps_prof,
    'get_annonces': tool_get_annonces,
    'get_notifications': tool_get_notifications,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
    'ouvrir_classe': tool_ouvrir_classe,
}
ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS.update(_merge_examens_handlers())

ENSEIGNANT_SECONDAIRE_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'function': {
            'name': 'proposer_actions',
            'description': (
                'Propose 2 à 3 actions ou questions de suite (chips cliquables). '
                'Lecture seule.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'suggestions': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'label': {'type': 'string'},
                                'value': {'type': 'string'},
                            },
                        },
                    },
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'chercher_en_base',
            'description': (
                'Cherche une donnée scolaire dans vos classes (effectifs, notes, '
                'présences, exercices, élèves en difficulté).'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string'},
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
                'required': ['question'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_mes_classes',
            'description': 'Liste vos classes affectées et les matières enseignées.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_effectifs',
            'description': 'Effectifs dans vos classes (total, filles, garçons).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string', 'description': CLASSE_PARAM_DESCRIPTION},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rechercher_eleves',
            'description': 'Recherche un élève parmi vos classes.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'classe': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_evaluations_classe',
            'description': 'Liste vos évaluations pour une classe.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string'},
                    'periode': {'type': 'string'},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_eleve',
            'description': 'Notes d’un élève (vos évaluations).',
            'parameters': {
                'type': 'object',
                'properties': {'eleve': {'type': 'string'}, 'query': {'type': 'string'}},
                'required': ['eleve'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notes_classe',
            'description': 'Notes saisies pour une classe et optionnellement une évaluation.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'classe': {'type': 'string'},
                    'evaluation': {'type': 'string'},
                },
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_eleves_difficulte',
            'description': 'Élèves avec moyenne inférieure au seuil (défaut 9).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'periode': {'type': 'string'},
                    'seuil': {'type': 'number'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_exercices_maison',
            'description': 'Exercices à la maison programmés.',
            'parameters': {
                'type': 'object',
                'properties': {'classe': {'type': 'string'}},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_presences',
            'description': 'Présences et absences sur vos classes.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'eleve': {'type': 'string'},
                    'jours': {'type': 'integer'},
                    'classe': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_sanctions',
            'description': 'Sanctions que vous avez soumises.',
            'parameters': {
                'type': 'object',
                'properties': {'eleve': {'type': 'string'}},
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_periodes',
            'description': 'Périodes scolaires de l’établissement.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_emploi_du_temps',
            'description': 'Emploi du temps d’une de vos classes.',
            'parameters': {
                'type': 'object',
                'properties': {'classe': {'type': 'string'}},
                'required': ['classe'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_annonces',
            'description': 'Annonces publiées pour les enseignants.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_notifications',
            'description': 'Vos notifications enseignant.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lister_pages',
            'description': 'Pages de votre espace enseignant.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_page',
            'description': 'Ouvre une page (dashboard, notes, présence, etc.).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'page_key': {'type': 'string'},
                    'query': {'type': 'string'},
                    'classe': {'type': 'string'},
                    'classe_id': {'type': 'integer'},
                    'ouvrir': {'type': 'boolean'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ouvrir_classe',
            'description': 'Ouvre la fiche d’une de vos classes.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'classe': {'type': 'string'},
                    'ouvrir': {'type': 'boolean'},
                },
            },
        },
    },
]

ENSEIGNANT_SECONDAIRE_TOOLS_SCHEMA.extend(build_enseignant_secondaire_action_tool_schemas())


def get_enseignant_secondaire_tools_schema(ctx=None):
    from school_admin.services.assistant_enseignant_examens_tools import (
        extend_enseignant_schema_for_examens,
    )
    from school_admin.services.assistant_enseignant_superieur_tools import (
        extend_enseignant_schema_for_superieur,
    )

    schema = list(ENSEIGNANT_SECONDAIRE_TOOLS_SCHEMA)
    schema = extend_enseignant_schema_for_superieur(schema, ctx)
    return extend_enseignant_schema_for_examens(schema, ctx)


def execute_enseignant_secondaire_tool(ctx, name, arguments):
    handler = ENSEIGNANT_SECONDAIRE_TOOL_HANDLERS.get(name)
    if handler:
        try:
            args = arguments if isinstance(arguments, dict) else {}
            return handler(ctx, args)
        except Exception:
            logger.exception("Erreur outil enseignant %s", name)
            return {'erreur': f'Impossible d’exécuter {name} pour le moment.'}
    spec = ENSEIGNANT_SECONDAIRE_ACTION_SPECS.get(name)
    if spec and spec.prepare:
        try:
            args = arguments if isinstance(arguments, dict) else {}
            return spec.prepare(ctx, args)
        except Exception:
            logger.exception("Erreur action enseignant %s", name)
            return {'erreur': f'Impossible de préparer {name}.'}
    return {'erreur': f'Outil inconnu : {name}'}


def spoken_from_enseignant_tool(name, result):
    from school_admin.services.assistant_tools import _spoken_name_list

    if not isinstance(result, dict):
        return ''
    if name == 'get_mes_classes' and result.get('classes'):
        listed = _spoken_name_list({
            'classes': [
                {'nom': c.get('classe') or c.get('nom')}
                for c in result['classes']
            ],
        })
        if listed:
            return listed
    if result.get('message'):
        msg = result['message'].strip()
        if (
            name == 'get_eleves_difficulte' or result.get('source') == 'difficulte'
        ) and result.get('nb_eleves', result.get('nb', 1)) == 0:
            if 'Je peux' not in msg:
                msg += ' Je peux lister la classe ou ouvrir les notes.'
        return msg
    if result.get('erreur'):
        return result['erreur'].strip()
    if name == 'get_effectifs':
        classe = result.get('classe')
        total = result.get('total') or result.get('total_eleves')
        if total is not None and classe:
            filles = result.get('filles')
            garcons = result.get('garcons')
            extra = ''
            if filles is not None and garcons is not None:
                extra = f', {filles} filles et {garcons} garçons'
            return f"{classe} : {total} élèves{extra}."
        if total is not None:
            nb_classes = result.get('nb_classes')
            if nb_classes:
                return f"{total} élèves dans {nb_classes} classes."
            return f"{total} élèves au total."
    if name == 'ouvrir_classe' and result.get('nom'):
        effectifs_hint = result.get('effectifs') or result.get('nb_eleves')
        if effectifs_hint:
            return f"J’ouvre {result['nom']}, {effectifs_hint} élèves."
        return f"J’ouvre {result['nom']}."
    listed = _spoken_name_list(result)
    if listed:
        return listed
    if name == 'lister_pages' and result.get('pages'):
        return f"{len(result['pages'])} pages disponibles dans votre espace."
    if name == 'get_evaluations_classe' and result.get('evaluations'):
        nb = len(result['evaluations'])
        classe = result.get('classe') or 'cette classe'
        return f"{nb} évaluation{'s' if nb > 1 else ''} pour {classe}."
    if name == 'get_modules_classe' and result.get('modules') is not None:
        nb = result.get('nb', len(result.get('modules') or []))
        classe = result.get('classe') or 'cette promotion'
        credits = result.get('credits_total')
        if credits is not None:
            return f"{nb} module(s) pour {classe}, {credits} credits ECTS au total."
        return f"{nb} module(s) pour {classe}."
    if name == 'get_credits_etudiant' and result.get('message'):
        return result['message'].strip()
    if name == 'get_examens_prof' and result.get('sessions'):
        nb = result.get('nb', len(result['sessions']))
        return result.get('message') or f"{nb} session(s) d'examen dans votre perimetre."
    if name == 'get_notes_examen' and result.get('message'):
        return result['message'].strip()
    if name == 'ouvrir_noter_examen' and result.get('titre'):
        return f"J'ouvre {result['titre']}."
    return ''
