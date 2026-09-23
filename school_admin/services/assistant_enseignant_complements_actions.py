"""
Actions confirmées P7 — justifier absence, évaluations, notifications lues.
Partagées primaire + secondaire / supérieur (périmètre affectations).
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from school_admin.services.assistant_actions import CONFIRM_CHOICES, _incomplete, _ok, _pending
from school_admin.services.assistant_enseignant_actions import register_enseignant_action
from school_admin.services.assistant_enseignant_scope import (
    classe_ids_for_prof,
    ensure_classe_access,
    ensure_eleve_access,
    find_classe_prof,
    find_eleve_prof,
)
from school_admin.services.assistant_enseignant_secondaire_actions import (
    ActionSpec,
    _parse_note,
    register_enseignant_secondaire_action,
)

logger = logging.getLogger(__name__)


def _reverse(route, args=None):
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse(route, args=args or [])
    except NoReverseMatch:
        return None


def _persona_primaire(ctx):
    return getattr(ctx, 'persona', '') == 'enseignant_primaire'


def _resolve_helpers(ctx):
    if _persona_primaire(ctx):
        from school_admin.services import assistant_enseignant_actions as mod

        return mod._resolve_matiere, mod._resolve_periode
    from school_admin.services import assistant_enseignant_secondaire_actions as mod

    return mod._resolve_matiere, mod._resolve_periode


def _evaluation_qs(ctx):
    if _persona_primaire(ctx):
        from school_admin.model.evaluation_primaire_model import EvaluationPrimaire

        qs = EvaluationPrimaire.objects.filter(
            professeur=ctx.professeur,
            actif=True,
        )
    else:
        from school_admin.model.evaluation_model import Evaluation

        qs = Evaluation.objects.filter(
            professeur=ctx.professeur,
            actif=True,
        )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return qs


def _find_evaluation_prof(ctx, args):
    classe = find_classe_prof(ctx, args.get('classe') or '')
    eval_id = args.get('evaluation_id')
    eval_q = (args.get('evaluation') or args.get('titre') or '').strip()
    qs = _evaluation_qs(ctx)
    evaluation = None
    if eval_id:
        evaluation = qs.filter(pk=eval_id).first()
    elif eval_q:
        scoped = qs.filter(titre__icontains=eval_q)
        if classe:
            scoped = scoped.filter(classe=classe)
        evaluation = scoped.order_by('-date_evaluation').first()
    if not evaluation:
        return None, None
    if err := ensure_classe_access(ctx, evaluation.classe):
        return None, err
    return evaluation, None


def _normalize_type_justificatif(raw):
    from school_admin.model.presence_model import Presence

    text = (raw or '').strip().lower()
    if not text:
        return None
    choices = dict(Presence.TYPE_JUSTIFICATIF_CHOICES)
    if text in choices:
        return text
    for key, label in Presence.TYPE_JUSTIFICATIF_CHOICES:
        low = label.lower()
        if text in low or low in text:
            return key
    aliases = {
        'medical': 'certificat_medical',
        'certificat': 'certificat_medical',
        'famille': 'raison_familiale',
        'familial': 'raison_familiale',
        'deces': 'deces_famille',
        'transport': 'probleme_transport',
    }
    for needle, key in aliases.items():
        if needle in text:
            return key
    return None


def _find_absence_to_justify(ctx, args):
    from school_admin.model.presence_model import Presence

    presence_id = args.get('presence_id')
    if presence_id:
        presence = (
            Presence.objects.filter(pk=presence_id)
            .select_related('eleve', 'classe')
            .first()
        )
        if not presence:
            return None, {'erreur': 'Présence introuvable.'}
        if err := ensure_classe_access(ctx, presence.classe):
            return None, err
        if err := ensure_eleve_access(ctx, presence.eleve):
            return None, err
        return presence, None

    classe = find_classe_prof(ctx, args.get('classe') or '')
    eleve = find_eleve_prof(
        ctx,
        args.get('eleve') or args.get('query') or '',
        classe,
    )
    if not eleve:
        return None, _incomplete(
            'justifier_absence',
            ['eleve'],
            'Quel élève et quelle date d’absence ?',
        )
    if err := ensure_eleve_access(ctx, eleve):
        return None, err
    if not classe:
        from school_admin.services.assistant_enseignant_scope import classe_eleve_active

        classe = classe_eleve_active(ctx, eleve)
    if err := ensure_classe_access(ctx, classe):
        return None, err

    date_raw = (args.get('date') or args.get('date_absence') or '').strip()[:10]
    date_val = parse_date(date_raw) if date_raw else None
    qs = Presence.objects.filter(
        eleve=eleve,
        classe=classe,
        statut='absent',
    ).filter(Q(type_justificatif__isnull=True) | Q(type_justificatif=''))
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    if date_val:
        qs = qs.filter(date=date_val)
    presence = qs.order_by('-date').first()
    if not presence:
        return None, {
            'erreur': 'Aucune absence non justifiée trouvée pour cet élève.',
        }
    return presence, None


def prepare_justifier_absence(ctx, args):
    type_j = _normalize_type_justificatif(
        args.get('type_justificatif') or args.get('motif') or args.get('type')
    )
    if not type_j:
        return _incomplete(
            'justifier_absence',
            ['type_justificatif'],
            'Quel type de justificatif (médical, familial, etc.) ?',
        )
    presence, err = _find_absence_to_justify(ctx, args)
    if err and not presence:
        return err
    if presence.statut != 'absent' or presence.type_justificatif:
        return {'erreur': 'Cette absence ne peut pas être justifiée.'}
    label = dict(presence.TYPE_JUSTIFICATIF_CHOICES).get(type_j, type_j)
    draft = {
        'presence_id': presence.id,
        'eleve_id': presence.eleve_id,
        'classe_id': presence.classe_id,
        'date_absence': presence.date.isoformat(),
        'type_justificatif': type_j,
        'manquants': [],
    }
    return _pending(
        'justifier_absence',
        (
            f"Justifier l’absence de {presence.eleve.nom_complet} "
            f"du {presence.date.strftime('%d/%m/%Y')} ({label})."
        ),
        **draft,
    )


def apply_justifier_absence(ctx, draft):
    from school_admin.model.presence_model import Presence

    presence = Presence.objects.filter(pk=draft.get('presence_id')).select_related(
        'eleve', 'classe'
    ).first()
    if not presence:
        return {'erreur': 'Présence introuvable.'}
    if err := ensure_classe_access(ctx, presence.classe):
        return err
    if presence.statut != 'absent' or presence.type_justificatif:
        return {'erreur': 'Cette absence a déjà été traitée.'}
    type_j = draft.get('type_justificatif')
    presence.type_justificatif = type_j
    presence.statut = 'absent_justifie'
    presence.justificatif_valide = True
    presence.date_justification = timezone.now()
    presence.save(
        update_fields=[
            'type_justificatif',
            'statut',
            'justificatif_valide',
            'date_justification',
            'date_modification',
        ]
    )
    route = (
        'enseignant_primaire:historique_presence'
        if _persona_primaire(ctx)
        else 'enseignant:historique_presence'
    )
    url = _reverse(route, [presence.eleve_id])
    return _ok(
        f"Absence du {presence.date.strftime('%d/%m/%Y')} justifiée.",
        url=url,
    )


def prepare_modifier_evaluation(ctx, args):
    evaluation, err = _find_evaluation_prof(ctx, args)
    if err:
        return err
    if not evaluation:
        return _incomplete(
            'modifier_evaluation',
            ['evaluation'],
            'Quelle évaluation modifier (titre ou identifiant) ?',
        )
    resolve_matiere, resolve_periode = _resolve_helpers(ctx)
    classe = evaluation.classe
    titre = (args.get('titre') or '').strip() or evaluation.titre
    description = args.get('description')
    if description is None:
        description = evaluation.description or ''
    else:
        description = str(description)[:2000]
    bareme_raw = args.get('bareme')
    bareme = str(bareme_raw) if bareme_raw is not None else str(evaluation.bareme)
    if _parse_note(bareme) is None:
        return {'erreur': 'Barème invalide.'}
    date_raw = (args.get('date_evaluation') or args.get('date') or '')[:10]
    date_eval = parse_date(date_raw) if date_raw else evaluation.date_evaluation
    if not date_eval:
        return _incomplete(
            'modifier_evaluation',
            ['date_evaluation'],
            'Quelle date pour l’évaluation ?',
            evaluation_id=evaluation.id,
        )
    matiere = evaluation.matiere
    if args.get('matiere') or args.get('matiere_id'):
        matiere, m_missing = resolve_matiere(ctx, classe, args)
        if m_missing:
            return _incomplete(
                'modifier_evaluation',
                m_missing,
                'Quelle matière ?',
                evaluation_id=evaluation.id,
            )
    periode = evaluation.periode_scolaire
    if args.get('periode') or args.get('periode_id') or args.get('semestre'):
        periode = resolve_periode(ctx, args, classe=classe)
    if not periode:
        return _incomplete(
            'modifier_evaluation',
            ['periode'],
            'Quelle période scolaire ?',
            evaluation_id=evaluation.id,
        )
    draft = {
        'evaluation_id': evaluation.id,
        'classe_id': classe.id,
        'titre': titre,
        'description': description,
        'matiere_id': matiere.id,
        'periode_id': periode.id,
        'date_evaluation': date_eval.isoformat(),
        'bareme': bareme,
        'manquants': [],
    }
    return _pending(
        'modifier_evaluation',
        f"Modifier l’évaluation « {evaluation.titre} » → « {titre} » ({classe.nom}).",
        **draft,
    )


def apply_modifier_evaluation(ctx, draft):
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.periode_model import PeriodeScolaire

    evaluation, err = _find_evaluation_prof(ctx, {'evaluation_id': draft.get('evaluation_id')})
    if err:
        return err
    if not evaluation:
        return {'erreur': 'Évaluation introuvable.'}
    matiere = Matiere.objects.filter(pk=draft.get('matiere_id')).first()
    if err := ensure_classe_access(ctx, evaluation.classe):
        return err
    from school_admin.services.assistant_enseignant_scope import ensure_matiere_in_classe

    if err := ensure_matiere_in_classe(ctx, evaluation.classe, matiere):
        return err
    periode = PeriodeScolaire.objects.filter(pk=draft.get('periode_id')).first()
    date_eval = parse_date(draft.get('date_evaluation') or '')
    evaluation.titre = draft.get('titre')
    evaluation.description = draft.get('description') or ''
    evaluation.matiere = matiere
    evaluation.date_evaluation = date_eval
    evaluation.bareme = _parse_note(draft.get('bareme')) or evaluation.bareme
    evaluation.periode_scolaire = periode
    if ctx.annee_scolaire and hasattr(evaluation, 'annee_scolaire_id'):
        evaluation.annee_scolaire = ctx.annee_scolaire
    evaluation.save()
    if not _persona_primaire(ctx):
        try:
            from school_admin.personal_views.enseignant_view import _emit_enseignant_live

            _emit_enseignant_live(
                ctx.professeur,
                'evaluation.modifiee',
                evaluation_id=evaluation.id,
                titre=evaluation.titre,
                classe_id=evaluation.classe_id,
                classe_nom=evaluation.classe.nom if evaluation.classe else '',
                matiere_id=matiere.id,
                matiere_nom=matiere.nom,
            )
        except Exception:
            logger.exception('Live evaluation.modifiee non émis')
    route = (
        'enseignant_primaire:evaluations_classe'
        if _persona_primaire(ctx)
        else 'enseignant:liste_evaluations'
    )
    url = _reverse(route, [evaluation.classe_id]) if _persona_primaire(ctx) else _reverse(route)
    return _ok(f"Évaluation « {evaluation.titre} » modifiée.", url=url)


def prepare_supprimer_evaluation(ctx, args):
    evaluation, err = _find_evaluation_prof(ctx, args)
    if err:
        return err
    if not evaluation:
        return _incomplete(
            'supprimer_evaluation',
            ['evaluation'],
            'Quelle évaluation supprimer ?',
        )
    draft = {
        'evaluation_id': evaluation.id,
        'titre': evaluation.titre,
        'classe_id': evaluation.classe_id,
        'destructive': True,
        'manquants': [],
    }
    return _pending(
        'supprimer_evaluation',
        f"Supprimer l’évaluation « {evaluation.titre} » ({evaluation.classe.nom}).",
        **draft,
    )


def apply_supprimer_evaluation(ctx, draft):
    evaluation, err = _find_evaluation_prof(ctx, {'evaluation_id': draft.get('evaluation_id')})
    if err:
        return err
    if not evaluation:
        return {'erreur': 'Évaluation introuvable.'}
    if err := ensure_classe_access(ctx, evaluation.classe):
        return err
    titre = evaluation.titre
    classe_id = evaluation.classe_id
    with transaction.atomic():
        evaluation.actif = False
        evaluation.save(update_fields=['actif'])
    if not _persona_primaire(ctx):
        try:
            from school_admin.personal_views.enseignant_view import _emit_enseignant_live

            _emit_enseignant_live(
                ctx.professeur,
                'evaluation.supprimee',
                evaluation_id=evaluation.id,
                titre=titre,
                classe_id=classe_id,
                classe_nom=evaluation.classe.nom if evaluation.classe else '',
            )
        except Exception:
            logger.exception('Live evaluation.supprimee non émis')
    route = (
        'enseignant_primaire:evaluations_classe'
        if _persona_primaire(ctx)
        else 'enseignant:liste_evaluations'
    )
    url = _reverse(route, [classe_id]) if _persona_primaire(ctx) else _reverse(route)
    return _ok(f"Évaluation « {titre} » supprimée.", url=url)


def _notifications_qs(ctx):
    from school_admin.model.notification_enseignant_model import NotificationEnseignant

    qs = NotificationEnseignant.objects.filter(enseignant=ctx.professeur)
    if ctx.annee_scolaire:
        qs = qs.filter(
            Q(annee_scolaire=ctx.annee_scolaire) | Q(annee_scolaire__isnull=True)
        )
    return qs


def prepare_marquer_notification_lue(ctx, args):
    qs = _notifications_qs(ctx).filter(lu=False)
    notif_id = args.get('notification_id') or args.get('id')
    if notif_id:
        qs = qs.filter(pk=notif_id)
        if not qs.exists():
            return {'erreur': 'Notification introuvable ou déjà lue.'}
        resume = 'Marquer cette notification comme lue.'
        draft_ids = list(qs.values_list('id', flat=True))
    else:
        count = qs.count()
        if count == 0:
            return {'erreur': 'Aucune notification non lue.'}
        resume = f'Marquer {count} notification(s) comme lues.'
        draft_ids = list(qs.values_list('id', flat=True)[:50])
    return _pending(
        'marquer_notification_lue',
        resume,
        notification_ids=draft_ids,
        manquants=[],
    )


def apply_marquer_notification_lue(ctx, draft):
    from school_admin.model.notification_enseignant_model import NotificationEnseignant

    ids = draft.get('notification_ids') or []
    if not ids:
        return {'erreur': 'Aucune notification à marquer.'}
    qs = NotificationEnseignant.objects.filter(
        pk__in=ids,
        enseignant=ctx.professeur,
        lu=False,
    )
    updated = 0
    now = timezone.now()
    for notif in qs:
        notif.lu = True
        notif.statut = 'lu'
        notif.date_lecture = now
        notif.save(update_fields=['lu', 'statut', 'date_lecture', 'date_modification'])
        updated += 1
    route = 'enseignant:notifications_enseignant'
    url = _reverse(route)
    return _ok(f'{updated} notification(s) marquée(s) comme lues.', url=url)


def _register_complement(spec: ActionSpec):
    register_enseignant_action(spec)
    register_enseignant_secondaire_action(spec)


_register_complement(
    ActionSpec(
        name='justifier_absence',
        description='Justifie une absence non justifiée d’un élève de vos classes.',
        properties={
            'eleve': {'type': 'string'},
            'classe': {'type': 'string'},
            'date': {'type': 'string'},
            'date_absence': {'type': 'string'},
            'presence_id': {'type': 'integer'},
            'type_justificatif': {'type': 'string'},
            'motif': {'type': 'string'},
        },
        required=('type_justificatif',),
        prepare=prepare_justifier_absence,
        apply=apply_justifier_absence,
    )
)

_register_complement(
    ActionSpec(
        name='modifier_evaluation',
        description='Modifie une évaluation que vous avez créée (titre, date, barème, matière).',
        properties={
            'evaluation_id': {'type': 'integer'},
            'evaluation': {'type': 'string'},
            'titre': {'type': 'string'},
            'classe': {'type': 'string'},
            'matiere': {'type': 'string'},
            'date_evaluation': {'type': 'string'},
            'bareme': {'type': 'number'},
            'periode': {'type': 'string'},
            'description': {'type': 'string'},
        },
        required=(),
        prepare=prepare_modifier_evaluation,
        apply=apply_modifier_evaluation,
    )
)

_register_complement(
    ActionSpec(
        name='supprimer_evaluation',
        description='Supprime (désactive) une de vos évaluations.',
        properties={
            'evaluation_id': {'type': 'integer'},
            'evaluation': {'type': 'string'},
            'titre': {'type': 'string'},
            'classe': {'type': 'string'},
        },
        required=(),
        destructive=True,
        prepare=prepare_supprimer_evaluation,
        apply=apply_supprimer_evaluation,
    )
)

_register_complement(
    ActionSpec(
        name='marquer_notification_lue',
        description='Marque une ou toutes vos notifications comme lues.',
        properties={
            'notification_id': {'type': 'integer'},
            'id': {'type': 'integer'},
        },
        required=(),
        prepare=prepare_marquer_notification_lue,
        apply=apply_marquer_notification_lue,
    )
)
