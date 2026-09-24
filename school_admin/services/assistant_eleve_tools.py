"""
Outils assistant élève — navigation, lecture scolaire (self-only).
"""
from __future__ import annotations

from django.db.models import Q

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


TOOL_HANDLERS = {
    'get_mon_resume': tool_get_mon_resume,
    'lister_pages': tool_lister_pages,
    'ouvrir_page': tool_ouvrir_page,
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
