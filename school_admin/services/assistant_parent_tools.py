"""
Outils assistant parent — Par2 : lecture socle + navigation.
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

PARENT_TOOL_NAMES = frozenset({
    'get_mes_enfants',
    'select_enfant',
    'get_resume_enfant',
    'lister_pages',
    'ouvrir_page',
    'get_notifications',
    'get_annonces',
})

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


TOOL_HANDLERS = {
    'get_mes_enfants': tool_get_mes_enfants,
    'select_enfant': tool_select_enfant,
    'get_resume_enfant': tool_get_resume_enfant,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
    'get_notifications': tool_get_notifications,
    'get_annonces': tool_get_annonces,
}


def build_parent_tool_schemas():
    return [
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


def get_parent_tools_schema():
    return build_parent_tool_schemas()


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
