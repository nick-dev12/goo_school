"""
Outils assistant parent — Par2 navigation + Par4 suivi scolaire.
"""
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from school_admin.services.assistant_parent_scope import (
    apply_consultation_session,
    assert_eleve_autorise,
    eleve_depuis_session,
    find_enfant_par_nom,
    get_eleve_lie,
    liens_valides_qs,
    resume_enfants,
)

from school_admin.services.assistant_parent_schema import PARENT_TOOL_NAMES_ALL

PARENT_TOOL_NAMES = PARENT_TOOL_NAMES_ALL

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
    'get_notes',
    'get_devoirs',
    'get_absences',
    'get_scolarite',
)


def _resolve_eleve_cible(ctx, args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return None, {'erreur': 'Compte parent requis.', 'statut': 'erreur'}
    eleve_id = args.get('eleve_id') or args.get('id')
    if eleve_id:
        denied = assert_eleve_autorise(parent, eleve_id)
        if denied:
            return None, denied
        return get_eleve_lie(parent, eleve_id), None
    eleve = getattr(ctx, 'eleve_consulte', None) or eleve_depuis_session(
        parent, getattr(ctx, 'session_store', None) or {}
    )
    if eleve:
        return eleve, None
    query = (args.get('nom') or args.get('query') or '').strip()
    if query:
        found = find_enfant_par_nom(parent, query)
        if found:
            return found, None
    return None, {
        'erreur': 'Précisez quel enfant (select_enfant ou nom) ou ouvrez d’abord son espace.',
        'statut': 'enfant_requis',
    }


def tool_get_mes_enfants(ctx, _args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    session = getattr(ctx, 'session_store', None) or {}
    consulte_id = session.get('eleve_consulte_id')
    items = []
    for row in resume_enfants(parent, limit=20):
        row = dict(row)
        row['en_consultation'] = consulte_id == row.get('id')
        items.append(row)
    return {
        'nb': len(items),
        'enfants': items,
        'message': (
            f"Vous avez {len(items)} enfant(s) lié(s)."
            if items
            else "Aucun enfant lié. Utilisez la liaison depuis l’accueil parent."
        ),
    }


def tool_select_enfant(ctx, args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    eleve_id = args.get('eleve_id') or args.get('id')
    eleve = None
    if eleve_id:
        eleve = get_eleve_lie(parent, eleve_id)
    else:
        query = (args.get('nom') or args.get('query') or '').strip()
        if query:
            eleve = find_enfant_par_nom(parent, query)
    if not eleve:
        return {
            'erreur': 'Enfant introuvable ou non lié à votre compte.',
            'statut': 'acces_refuse',
        }
    session = getattr(ctx, 'session_store', None)
    apply_consultation_session(session, parent, eleve)
    ctx.eleve_consulte = eleve
    url = reverse('eleve:dashboard_eleve')
    return {
        'statut': 'ok',
        'eleve_id': eleve.id,
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'message': f"J’ai sélectionné {eleve.prenom}. Vous pouvez consulter son espace.",
        'url': url,
        'ouvrir': True,
    }


def tool_get_resume_enfant(ctx, args):
    from school_admin.model.presence_model import Presence
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    from school_admin.personal_views.eleve_view import get_classe_eleve_active

    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    etab = eleve.etablissement
    annee = (
        AnneeScolaire.get_session_active(etab)
        if etab
        else ctx.annee_scolaire
    )
    classe = get_classe_eleve_active(eleve, annee, etab) if annee else eleve.classe
    presences = Presence.objects.filter(eleve=eleve)
    if annee:
        presences = presences.filter(annee_scolaire=annee)
    total_absences = presences.filter(
        Q(statut='absent') | Q(statut='absent_justifie')
    ).count()
    from school_admin.model.notification_parent_model import NotificationParent

    parent = ctx.parent
    notif_non_lues = NotificationParent.objects.filter(parent=parent, lu=False)
    if annee:
        notif_non_lues = notif_non_lues.filter(annee_scolaire=annee)
    notif_non_lues = notif_non_lues.filter(eleve=eleve).count()
    return {
        'eleve_id': eleve.id,
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'classe': classe.nom if classe else None,
        'etablissement': etab.nom if etab else None,
        'total_absences': total_absences,
        'notifications_non_lues': notif_non_lues,
        'message': (
            f"{eleve.prenom} — classe {classe.nom if classe else 'non assignée'}, "
            f"{total_absences} absence(s) enregistrée(s), "
            f"{notif_non_lues} notification(s) non lue(s) pour cet enfant."
        ),
    }


def tool_get_notifications(ctx, args):
    from school_admin.model.notification_eleve_model import NotificationEleve
    from school_admin.model.notification_parent_model import NotificationParent

    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    espace = (args.get('espace') or 'auto').strip().lower()
    eleve, err = _resolve_eleve_cible(ctx, args) if espace in ('enfant', 'auto') else (None, None)
    if err and espace == 'enfant':
        return err

    items = []
    nb_non_lues = 0
    if espace in ('parent', 'auto', 'hub'):
        qs = NotificationParent.objects.filter(parent=parent).select_related('eleve')
        if ctx.annee_scolaire:
            qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
        if eleve and espace != 'hub':
            qs = qs.filter(eleve=eleve)
        nb_non_lues = qs.filter(lu=False).count()
        for n in qs.order_by('-date_creation')[:12]:
            items.append({
                'source': 'parent',
                'titre': n.titre,
                'message': (n.message or '')[:200],
                'lu': bool(n.lu),
                'enfant': n.eleve.nom_complet if n.eleve_id else None,
                'date': n.date_creation.isoformat() if n.date_creation else None,
            })

    if eleve and espace in ('enfant', 'auto'):
        qs_el = NotificationEleve.objects.filter(eleve=eleve)
        if ctx.annee_scolaire:
            qs_el = qs_el.filter(annee_scolaire=ctx.annee_scolaire)
        nb_non_lues += qs_el.filter(lu=False).count()
        for n in qs_el.order_by('-date_creation')[:8]:
            items.append({
                'source': 'eleve',
                'titre': n.titre,
                'message': (n.message or '')[:200],
                'lu': bool(getattr(n, 'lu', False)),
                'date': n.date_creation.isoformat() if n.date_creation else None,
            })

    url_parent = reverse('school_admin:notifications_parent')
    url_enfant = reverse('eleve:notifications_eleve') if eleve else None
    return {
        'nb_non_lues': nb_non_lues,
        'notifications': items[:15],
        'url_notifications_parent': url_parent,
        'url_notifications_enfant': url_enfant,
    }


def tool_get_annonces(ctx, args):
    from datetime import timedelta

    from school_admin.model.annonce_model import Annonce

    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}

    etab_ids = set()
    for lien in liens_valides_qs(parent):
        if lien.eleve and lien.eleve.etablissement_id:
            etab_ids.add(lien.eleve.etablissement_id)
    if not etab_ids:
        return {'annonces': [], 'nb': 0, 'message': 'Aucun établissement associé à vos enfants.'}

    periode = (args.get('periode') or '').strip().lower()
    today = timezone.now().date()
    qs = Annonce.objects.filter(
        etablissement_id__in=etab_ids,
        statut='publiee',
        actif=True,
    ).filter(
        Q(destinataires__contains=['tous']) | Q(destinataires__contains=['parents'])
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    if periode == 'semaine':
        qs = qs.filter(date_publication__gte=today - timedelta(days=7))
    elif periode == 'mois':
        qs = qs.filter(date_publication__gte=today - timedelta(days=30))

    items = [
        {
            'titre': a.titre,
            'etablissement': a.etablissement.nom if a.etablissement_id else None,
            'date': a.date_publication.isoformat() if a.date_publication else None,
            'extrait': (a.contenu or '')[:160],
        }
        for a in qs.order_by('-date_publication', '-date_creation')[:10]
    ]
    return {
        'nb': len(items),
        'annonces': items,
        'url_annonces_parent': reverse('school_admin:annonces_parent'),
    }


def tool_lister_pages(_ctx, _args):
    from school_admin.services.assistant_pages_parent import list_pages

    return {
        'pages': [
            {
                'key': p['key'],
                'titre': p['titre'],
                'espace': p.get('espace'),
            }
            for p in list_pages()
        ],
    }


def tool_ouvrir_page(ctx, args):
    from school_admin.services.assistant_pages_parent import (
        find_page,
        page_url,
        related_pages,
    )

    page = find_page(args.get('page_key') or args.get('query') or args.get('page'))
    if not page:
        return {'erreur': 'Page inconnue. Utilise lister_pages pour les clés valides.'}

    extra = {}
    if page.get('key') == 'selection_enfant' or page.get('route_kwargs'):
        eleve_id = args.get('eleve_id')
        if not eleve_id:
            eleve, err = _resolve_eleve_cible(ctx, args)
            if err:
                return {
                    **err,
                    'hint': 'Appelez select_enfant ou indiquez eleve_id pour ouvrir l’espace enfant.',
                }
            eleve_id = eleve.id
        extra['eleve_id'] = eleve_id

    meta_requires = False
    for meta in __import__(
        'school_admin.services.assistant_pages_parent', fromlist=['PAGE_CATALOG']
    ).PAGE_CATALOG:
        if meta['key'] == page['key']:
            meta_requires = bool(meta.get('requires_enfant_session'))
            break

    if meta_requires:
        session = getattr(ctx, 'session_store', None) or {}
        if not session.get('eleve_consulte_id'):
            return {
                'erreur': 'Sélectionnez d’abord un enfant (select_enfant).',
                'statut': 'enfant_requis',
                'key': page['key'],
            }

    url = page_url(page, extra) or page.get('url')
    if not url:
        return {
            'erreur': 'Impossible de construire l’URL. Indiquez eleve_id ou select_enfant.',
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


def tool_get_notes_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_notes_enfant

    return read_notes_enfant(eleve, ctx)


def tool_get_bulletin_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_bulletin_enfant

    return read_bulletin_enfant(eleve, ctx)


def tool_get_devoirs_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_devoirs_enfant

    return read_devoirs_enfant(eleve, ctx, periode=args.get('periode'))


def tool_get_absences_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_absences_enfant

    return read_absences_enfant(eleve, ctx)


def tool_get_sanctions_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_sanctions_enfant

    return read_sanctions_enfant(eleve, ctx)


def tool_get_convocations_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_convocations_enfant

    a_venir = args.get('a_venir')
    if a_venir is None:
        a_venir = True
    return read_convocations_enfant(eleve, ctx, a_venir=bool(a_venir))


def tool_get_convocations_famille(ctx, _args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    from school_admin.services.assistant_parent_scolaire import read_convocations_famille

    return read_convocations_famille(parent, ctx)


def tool_get_emploi_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_emploi_enfant

    return read_emploi_enfant(eleve, ctx)


TOOL_HANDLERS = {
    'get_mes_enfants': tool_get_mes_enfants,
    'select_enfant': tool_select_enfant,
    'get_resume_enfant': tool_get_resume_enfant,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
    'get_notifications': tool_get_notifications,
    'get_annonces': tool_get_annonces,
    'get_notes_enfant': tool_get_notes_enfant,
    'get_bulletin_enfant': tool_get_bulletin_enfant,
    'get_devoirs_enfant': tool_get_devoirs_enfant,
    'get_absences_enfant': tool_get_absences_enfant,
    'get_sanctions_enfant': tool_get_sanctions_enfant,
    'get_convocations_enfant': tool_get_convocations_enfant,
    'get_convocations_famille': tool_get_convocations_famille,
    'get_emploi_enfant': tool_get_emploi_enfant,
}


def tool_get_scolarite_enfant(ctx, args):
    eleve, err = _resolve_eleve_cible(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolarite import read_scolarite_enfant

    return read_scolarite_enfant(eleve, ctx)


def tool_get_scolarite_famille(ctx, _args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    from school_admin.services.assistant_parent_scolarite import read_scolarite_famille

    return read_scolarite_famille(parent, ctx)


def tool_ouvrir_recu(ctx, args):
    parent = getattr(ctx, 'parent', None)
    if not parent:
        return {'erreur': 'Compte parent requis.'}
    from school_admin.services.assistant_parent_scolarite import ouvrir_recu_parent

    pid = args.get('paiement_id') or args.get('id')
    ouvrir = args.get('ouvrir', True)
    return ouvrir_recu_parent(parent, pid, ouvrir=ouvrir)


TOOL_HANDLERS.update({
    'get_scolarite_enfant': tool_get_scolarite_enfant,
    'get_scolarite_famille': tool_get_scolarite_famille,
    'ouvrir_recu': tool_ouvrir_recu,
})


PAR2_GEMINI_TOOLS = [
        {
            'type': 'function',
            'function': {
                'name': 'get_mes_enfants',
                'description': 'Liste les enfants liés au compte parent (nom, classe, enfant en consultation).',
                'parameters': {'type': 'object', 'properties': {}},
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'select_enfant',
                'description': 'Sélectionne un enfant pour consulter son espace (session).',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'eleve_id': {'type': 'integer'},
                        'nom': {'type': 'string', 'description': 'Nom ou prénom de l’enfant'},
                    },
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'get_resume_enfant',
                'description': 'Résumé léger : classe, absences, notifications non lues (pas le détail des notes).',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'eleve_id': {'type': 'integer'},
                        'nom': {'type': 'string'},
                    },
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'get_annonces',
                'description': 'Annonces publiées pour les parents (établissements de vos enfants).',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'periode': {
                            'type': 'string',
                            'description': 'semaine, mois ou vide pour toutes',
                        },
                    },
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'get_notifications',
                'description': 'Notifications parent et/ou espace enfant consulté.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'espace': {
                            'type': 'string',
                            'description': 'auto, parent, enfant ou hub',
                        },
                        'eleve_id': {'type': 'integer'},
                        'nom': {'type': 'string'},
                    },
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'lister_pages',
                'description': 'Pages disponibles dans l’espace parent et enfant.',
                'parameters': {'type': 'object', 'properties': {}},
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'ouvrir_page',
                'description': 'Ouvre une page (accueil, notes, annonces, etc.).',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'page_key': {'type': 'string'},
                        'query': {'type': 'string'},
                        'eleve_id': {'type': 'integer'},
                        'ouvrir': {'type': 'boolean'},
                    },
                },
            },
        },
    ]


def build_parent_tool_schemas():
    return list(PAR2_GEMINI_TOOLS)


def get_parent_tools_schema(ctx=None):
    from school_admin.services.assistant_parent_schema import build_parent_tool_schemas

    return build_parent_tool_schemas(ctx)


def spoken_from_parent_tool(name, result):
    if not isinstance(result, dict):
        return ''
    if result.get('message'):
        return str(result['message']).strip()
    if result.get('erreur'):
        return str(result['erreur']).strip()
    if name == 'get_notes_enfant' and result.get('moyenne_generale') is not None:
        return (
            f"Moyenne générale {result['moyenne_generale']} "
            f"pour {result.get('nom') or 'votre enfant'}."
        )
    if name == 'get_bulletin_enfant':
        if result.get('publie'):
            return result.get('message') or 'Bulletin publié.'
        return result.get('message') or 'Bulletin non publié.'
    if name == 'get_devoirs_enfant':
        return result.get('message') or 'Devoirs récupérés.'
    if name == 'get_absences_enfant':
        return result.get('message') or 'Absences récupérées.'
    if name == 'get_convocations_famille':
        return result.get('message') or 'Convocations familiale.'
    if name in ('get_scolarite_enfant', 'get_scolarite_famille'):
        return result.get('message') or 'Scolarité récupérée.'
    if name == 'ouvrir_recu' and result.get('url'):
        return result.get('message') or 'Reçu ouvert.'
    return ''


def suggestions_after_parent_read(tool_results):
    names = {
        item[0]
        for item in (tool_results or [])
        if isinstance(item, (tuple, list)) and item
    }
    from school_admin.services.assistant_tools import normalize_suggestions

    items = []
    if {'get_notes_enfant', 'get_absences_enfant'} <= names:
        items = [
            {'label': 'Devoirs', 'value': 'Quels devoirs cette semaine ?'},
            {'label': 'Scolarité', 'value': 'Quel est le reste à payer ?'},
            {'label': 'Conseil', 'value': 'Comment l’aider à progresser ?'},
        ]
    elif 'get_notes_enfant' in names:
        items = [
            {'label': 'Bulletin', 'value': 'Le bulletin est-il publié ?'},
            {'label': 'Devoirs', 'value': 'Quels devoirs cette semaine ?'},
            {'label': 'Ouvrir notes', 'value': 'Ouvre la page des notes.'},
        ]
    elif 'get_devoirs_enfant' in names:
        items = [
            {'label': 'Notes', 'value': 'Montre les notes récentes.'},
            {'label': 'Absences', 'value': 'Combien d’absences ?'},
            {'label': 'Emploi du temps', 'value': 'Emploi du temps demain ?'},
        ]
    elif 'get_absences_enfant' in names:
        items = [
            {'label': 'Sanctions', 'value': 'Y a-t-il des sanctions ?'},
            {'label': 'Convocations', 'value': 'Convocations à venir ?'},
            {'label': 'Conseil', 'value': 'Comment l’aider à mieux assister ?'},
        ]
    elif 'get_bulletin_enfant' in names:
        items = [
            {'label': 'Ouvrir bulletin', 'value': 'Ouvre le bulletin.'},
            {'label': 'Notes détail', 'value': 'Détail des notes par matière.'},
        ]
    elif 'get_convocations_enfant' in names or 'get_convocations_famille' in names:
        items = [
            {'label': 'Notifications', 'value': 'Notifications non lues ?'},
            {'label': 'Annonces', 'value': 'Annonces de l’école ?'},
        ]
    elif 'get_emploi_enfant' in names:
        items = [
            {'label': 'Devoirs', 'value': 'Devoirs pour cette semaine ?'},
            {'label': 'Notes', 'value': 'Notes récentes ?'},
        ]
    elif 'get_sanctions_enfant' in names:
        items = [
            {'label': 'Absences', 'value': 'Absences récentes ?'},
            {'label': 'Convocations', 'value': 'Convocations ?'},
        ]
    elif 'get_scolarite_enfant' in names:
        items = [
            {'label': 'Reçu', 'value': 'Ouvre le dernier reçu de paiement.'},
            {'label': 'Famille', 'value': 'Dette totale pour tous mes enfants ?'},
            {'label': 'Page scolarité', 'value': 'Ouvre la page scolarité parent.'},
        ]
    elif 'get_scolarite_famille' in names:
        items = [
            {'label': 'Détail enfant', 'value': 'Combien je dois pour mon enfant ?'},
            {'label': 'Ouvrir scolarité', 'value': 'Ouvre la page scolarité.'},
        ]
    elif 'ouvrir_recu' in names:
        items = [
            {'label': 'Scolarité', 'value': 'Quel est le reste à payer ?'},
        ]
    return normalize_suggestions(items, limit=3)


def execute_parent_tool(ctx, name, arguments):
    args = arguments if isinstance(arguments, dict) else {}
    lowered = (name or '').strip().lower()

    if lowered in PARENT_TOOL_NAMES:
        handler = TOOL_HANDLERS.get(lowered)
        if handler:
            try:
                return handler(ctx, args)
            except Exception:
                import logging

                logging.getLogger(__name__).exception('Erreur outil parent %s', name)
                return {'erreur': f'Impossible d’exécuter {name} pour le moment.'}

    for blocked in _FORBIDDEN_TOOL_PREFIXES:
        if lowered == blocked or lowered.startswith(blocked):
            return {
                'erreur': "Cette action est réservée à l'établissement, pas aux parents.",
                'statut': 'hors_perimetre',
            }

    eleve_id = args.get('eleve_id') or args.get('id')
    parent = getattr(ctx, 'parent', None)
    if eleve_id and parent:
        denied = assert_eleve_autorise(parent, eleve_id)
        if denied:
            return denied

    return {
        'erreur': f'Outil « {name} » non disponible pour les parents.',
        'statut': 'outil_inconnu',
    }
