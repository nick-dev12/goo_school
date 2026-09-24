"""
Outils assistant élève — navigation, lecture scolaire (self-only).
"""
from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from school_admin.services.assistant_eleve_scope import assert_self_only, get_self_eleve
from school_admin.services.assistant_eleve_schema import (
    ELEVE_NAV_TOOLS,
    ELEVE_TOOL_NAMES_ALL,
    allowed_tool_names,
    build_eleve_tool_schemas,
)
from school_admin.services.assistant_parent_schema import PARENT_TOOL_NAMES_ALL

ELEVE_TOOL_NAMES = ELEVE_TOOL_NAMES_ALL

# Outils homonymes parent / élève (implémentation élève distincte).
_SHARED_WITH_PARENT = frozenset({
    'lister_pages',
    'ouvrir_page',
    'get_annonces',
    'get_notifications',
})

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
    'get_scolarite',
    'marquer_notification',
)


def get_eleve_tools_schema(ctx=None):
    return build_eleve_tool_schemas(ctx)


def _require_self(ctx, args):
    denied = assert_self_only(ctx, args.get('eleve_id') or args.get('id'))
    if denied:
        return None, denied
    eleve = get_self_eleve(ctx)
    if not eleve:
        return None, {'erreur': 'Compte élève requis.', 'statut': 'erreur'}
    return eleve, None


def tool_get_mon_resume(ctx, args):
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    from school_admin.model.notification_eleve_model import NotificationEleve
    from school_admin.model.presence_model import Presence
    from school_admin.personal_views.eleve_view import get_classe_eleve_active

    eleve, err = _require_self(ctx, args)
    if err:
        return err
    etab = eleve.etablissement
    annee = ctx.annee_scolaire or (
        AnneeScolaire.get_session_active(etab) if etab else None
    )
    classe = get_classe_eleve_active(eleve, annee, etab) if annee else eleve.classe
    presences = Presence.objects.filter(eleve=eleve)
    if annee:
        presences = presences.filter(annee_scolaire=annee)
    total_absences = presences.filter(
        Q(statut='absent') | Q(statut='absent_justifie')
    ).count()
    notif_qs = NotificationEleve.objects.filter(eleve=eleve, lu=False)
    if annee:
        notif_qs = notif_qs.filter(annee_scolaire=annee)
    notif_non_lues = notif_qs.count()
    prenom = eleve.prenom or 'toi'
    classe_label = classe.nom if classe else 'non assignée'
    return {
        'eleve_id': eleve.id,
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'classe': classe_label,
        'etablissement': etab.nom if etab else None,
        'total_absences': total_absences,
        'notifications_non_lues': notif_non_lues,
        'message': (
            f"{prenom}, tu es en {classe_label} — "
            f"{total_absences} absence(s) enregistrée(s), "
            f"{notif_non_lues} notification(s) non lue(s)."
        ),
    }


def tool_lister_pages(_ctx, _args):
    from school_admin.services.assistant_pages_eleve import list_pages

    return {
        'pages': [
            {'key': p['key'], 'titre': p['titre'], 'espace': p.get('espace')}
            for p in list_pages()
        ],
    }


def tool_ouvrir_page(ctx, args):
    from school_admin.services.assistant_pages_eleve import (
        find_page,
        page_url,
        related_pages,
    )

    _, err = _require_self(ctx, args)
    if err:
        return err
    page = find_page(args.get('page_key') or args.get('query') or args.get('page'))
    if not page:
        return {'erreur': 'Page inconnue. Utilise lister_pages pour les clés valides.'}
    url = page_url(page) or page.get('url')
    if not url:
        return {'erreur': 'Impossible de construire l’URL.', 'key': page['key']}
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


def tool_get_annonces(ctx, args):
    from datetime import timedelta

    from django.utils import timezone

    from school_admin.model.annonce_model import Annonce

    eleve, err = _require_self(ctx, args)
    if err:
        return err
    etab = eleve.etablissement
    if not etab:
        return {'annonces': [], 'nb': 0, 'message': 'Établissement introuvable.'}
    periode = (args.get('periode') or '').strip().lower()
    today = timezone.now().date()
    qs = Annonce.objects.filter(
        etablissement=etab,
        statut='publiee',
        actif=True,
    ).filter(
        Q(destinataires__contains=['tous']) | Q(destinataires__contains=['eleves'])
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
            'date': a.date_publication.isoformat() if a.date_publication else None,
            'extrait': (a.contenu or '')[:160],
        }
        for a in qs.order_by('-date_publication', '-date_creation')[:10]
    ]
    return {
        'nb': len(items),
        'annonces': items,
        'url_annonces': reverse('eleve:annonces_eleve'),
        'message': f"{len(items)} annonce(s) pour toi." if items else 'Aucune annonce récente.',
    }


def _wrap_scolaire(eleve, ctx, reader, **kwargs):
    from django.urls import reverse

    out = reader(eleve, ctx, **kwargs) if kwargs else reader(eleve, ctx)
    if isinstance(out, dict) and out.get('message') and eleve:
        prenom = eleve.prenom or 'toi'
        out['message'] = out['message'].replace(f"de {prenom}", 'pour toi').replace(
            f"pour {prenom}", 'pour toi'
        )
    return out


def tool_get_mes_notes(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_notes_enfant

    return _wrap_scolaire(eleve, ctx, read_notes_enfant)


def tool_get_mon_bulletin(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_bulletin_enfant

    return _wrap_scolaire(eleve, ctx, read_bulletin_enfant)


def tool_get_mes_devoirs(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_devoirs_enfant

    periode = args.get('periode') or 'semaine'
    return _wrap_scolaire(eleve, ctx, read_devoirs_enfant, periode=periode)


def tool_get_mes_absences(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_absences_enfant

    return _wrap_scolaire(eleve, ctx, read_absences_enfant)


def tool_get_mes_sanctions(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_sanctions_enfant

    return _wrap_scolaire(eleve, ctx, read_sanctions_enfant)


def tool_get_mes_convocations(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_convocations_enfant

    a_venir = args.get('a_venir')
    if a_venir is None:
        a_venir = True
    return _wrap_scolaire(eleve, ctx, read_convocations_enfant, a_venir=bool(a_venir))


def tool_get_mon_emploi(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from school_admin.services.assistant_parent_scolaire import read_emploi_enfant

    return _wrap_scolaire(eleve, ctx, read_emploi_enfant)


def tool_get_notifications(ctx, args):
    from school_admin.model.notification_eleve_model import NotificationEleve

    eleve, err = _require_self(ctx, args)
    if err:
        return err
    notif_id = args.get('notification_id')
    if notif_id:
        notif = NotificationEleve.objects.filter(pk=notif_id, eleve=eleve).first()
        if not notif:
            return {'erreur': 'Notification introuvable.', 'statut': 'introuvable'}
        return {
            'notification_id': notif.id,
            'titre': notif.titre,
            'message': (notif.message or '')[:500],
            'lu': bool(getattr(notif, 'lu', False)),
            'date': notif.date_creation.isoformat() if notif.date_creation else None,
            'message_resume': f"Notification : {notif.titre}.",
        }

    qs = NotificationEleve.objects.filter(eleve=eleve)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    if args.get('non_lues_seulement'):
        qs = qs.filter(lu=False)
    items = []
    for n in qs.order_by('-date_creation')[:15]:
        items.append({
            'notification_id': n.id,
            'titre': n.titre,
            'message': (n.message or '')[:200],
            'lu': bool(getattr(n, 'lu', False)),
            'date': n.date_creation.isoformat() if n.date_creation else None,
        })
    nb_non_lues = qs.filter(lu=False).count()
    return {
        'nb_non_lues': nb_non_lues,
        'notifications': items,
        'url_notifications': reverse('eleve:notifications_eleve'),
        'message': (
            f"Tu as {nb_non_lues} notification(s) non lue(s)."
            if nb_non_lues
            else 'Aucune notification non lue.'
        ),
    }


def tool_get_mon_historique(ctx, args):
    from django.db.models import Q

    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.presence_model import Presence
    from school_admin.model.sanction_model import Sanction

    eleve, err = _require_self(ctx, args)
    if err:
        return err
    etab = eleve.etablissement
    if not etab:
        return {'annees': [], 'message': 'Établissement introuvable.'}
    inscriptions = InscriptionEleve.objects.filter(
        eleve=eleve,
        etablissement=etab,
        annee_scolaire__est_active=False,
    ).select_related('annee_scolaire', 'classe').order_by('-annee_scolaire__date_debut')[:8]
    rows = []
    for ins in inscriptions:
        annee = ins.annee_scolaire
        pres = Presence.objects.filter(eleve=eleve, annee_scolaire=annee)
        absences = pres.filter(Q(statut='absent') | Q(statut='absent_justifie')).count()
        sanctions = Sanction.objects.filter(eleve=eleve, annee_scolaire=annee).count()
        rows.append({
            'annee_id': annee.id if annee else None,
            'libelle': getattr(annee, 'nom_annee', None) or str(annee),
            'classe': ins.classe.nom if ins.classe_id else None,
            'absences': absences,
            'sanctions': sanctions,
        })
    return {
        'nb': len(rows),
        'annees': rows,
        'url_historique': reverse('eleve:historique_annees'),
        'message': (
            f"{len(rows)} année(s) passée(s) dans ton historique."
            if rows
            else 'Aucune année archivée pour le moment.'
        ),
    }


def tool_get_mon_profil(ctx, args):
    eleve, err = _require_self(ctx, args)
    if err:
        return err
    from django.urls import reverse

    return {
        'nom': getattr(eleve, 'nom_complet', None) or f'{eleve.prenom} {eleve.nom}',
        'prenom': eleve.prenom,
        'matricule': getattr(eleve, 'matricule_eleve', None),
        'email': getattr(eleve, 'email', None),
        'classe': eleve.classe.nom if eleve.classe_id else None,
        'url_profil': reverse('eleve:profil_eleve'),
        'message': (
            f"Ton compte : {eleve.prenom} {eleve.nom}. "
            'Pour la photo ou le mot de passe, utilise la page profil.'
        ),
    }


TOOL_HANDLERS = {
    'get_mon_resume': tool_get_mon_resume,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
    'get_annonces': tool_get_annonces,
    'get_mes_notes': tool_get_mes_notes,
    'get_mon_bulletin': tool_get_mon_bulletin,
    'get_mes_devoirs': tool_get_mes_devoirs,
    'get_mes_absences': tool_get_mes_absences,
    'get_mes_sanctions': tool_get_mes_sanctions,
    'get_mes_convocations': tool_get_mes_convocations,
    'get_mon_emploi': tool_get_mon_emploi,
    'get_mon_profil': tool_get_mon_profil,
    'get_notifications': tool_get_notifications,
    'get_mon_historique': tool_get_mon_historique,
}


def execute_eleve_tool(ctx, name, arguments):
    args = arguments if isinstance(arguments, dict) else {}
    lowered = (name or '').strip().lower()

    if lowered in PARENT_TOOL_NAMES_ALL and lowered not in _SHARED_WITH_PARENT:
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

    if lowered not in allowed_tool_names(ctx):
        if lowered in ELEVE_TOOL_NAMES_ALL:
            return {
                'erreur': f'Outil « {name} » pas encore activé pour ton assistant.',
                'statut': 'outil_inconnu',
            }
        return {
            'erreur': f'Outil « {name} » non disponible pour les élèves.',
            'statut': 'outil_inconnu',
        }

    handler = TOOL_HANDLERS.get(lowered)
    if not handler:
        return {'erreur': f'Outil « {name} » indisponible pour le moment.'}

    return handler(ctx, args)


def spoken_from_eleve_tool(name, result):
    if not isinstance(result, dict):
        return ''
    if result.get('message'):
        return str(result['message']).strip()
    if result.get('erreur'):
        return str(result['erreur']).strip()
    if name == 'ouvrir_page' and result.get('titre'):
        return f"J’ouvre {result['titre']}."
    if name == 'get_mes_notes' and result.get('moyenne_generale') is not None:
        return f"Ta moyenne générale est {result['moyenne_generale']}."
    if name == 'get_mon_bulletin':
        return result.get('message') or 'Bulletin récupéré.'
    return ''


def suggestions_after_eleve_read(tool_results):
    names = {
        item[0]
        for item in (tool_results or [])
        if isinstance(item, (tuple, list)) and item
    }
    from school_admin.services.assistant_tools import normalize_suggestions

    items = []
    if names & {'get_mes_notes', 'get_mon_bulletin'}:
        items = [
            {'label': 'Devoirs', 'value': 'Quels sont mes devoirs cette semaine ?'},
            {'label': 'Absences', 'value': 'Mes absences ?'},
            {'label': 'Emploi du temps', 'value': 'Mon emploi du temps demain.'},
        ]
    elif names & {'get_mes_devoirs'}:
        items = [
            {'label': 'Notes', 'value': 'Mes notes ?'},
            {'label': 'Bulletin', 'value': 'Mon bulletin est publié ?'},
            {'label': 'Ouvrir devoirs', 'value': 'Ouvre mes devoirs.'},
        ]
    elif names & {'get_mon_resume', 'ouvrir_page', 'lister_pages'}:
        items = [
            {'label': 'Devoirs', 'value': 'Ouvre mes devoirs.'},
            {'label': 'Notes', 'value': 'Montre mes notes.'},
            {'label': 'Notifications', 'value': 'Mes notifications ?'},
        ]
    return normalize_suggestions(items, limit=3)
