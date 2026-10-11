"""Alertes structurées du dashboard (D2)."""
from __future__ import annotations

from django.db.models import Count
from django.urls import NoReverseMatch, reverse

from school_admin.services.dashboard.completeness import build_completeness_block
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.permissions import user_may
from school_admin.services.dashboard.querysets import apply_classe_filters, eleves_qs

CATEGORY_URGENT = 'URGENT'
CATEGORY_IMPORTANT = 'IMPORTANT'
CATEGORY_WATCH = 'SURVEILLER'
CATEGORY_INFO = 'INFO'


def _apprenant(ctx: DashboardContext) -> str:
    """« étudiant » dans le supérieur, « élève » ailleurs."""
    return 'étudiant' if getattr(ctx.etablissement, 'type_etablissement', '') == 'superieur' else 'élève'


def _apprenants(ctx: DashboardContext) -> str:
    return _apprenant(ctx) + 's'


def _url(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return ''


def build_dashboard_alerts(ctx: DashboardContext) -> list[dict]:
    alerts = []
    period_label = ctx.annee_scolaire.libelle if ctx.annee_scolaire else 'session courante'

    if user_may(ctx, 'comptabilite_voir') and ctx.annee_scolaire:
        from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

        n_impayes = ComptabiliteEleve.objects.filter(
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            statut_paiement__in=('en_retard', 'impaye'),
        ).count()
        if n_impayes:
            alerts.append({
                'id': 'payments_overdue',
                'category': CATEGORY_URGENT,
                'priority': 1,
                'message': f'{n_impayes} dossier(s) de paiement en retard ou impayé(s)',
                'detail': f'Dossiers {_apprenants(ctx)} dont le statut de paiement est en retard ou impayé.',
                'value': n_impayes,
                'period': period_label,
                'source': 'ComptabiliteEleve.statut_paiement',
                'url': _url('directeur:liste_impayes_directeur'),
                'permission': 'comptabilite_voir',
            })

    if user_may(ctx, 'presences_liste'):
        completeness = build_completeness_block(ctx)
        appel_gap = next((g for g in completeness['gaps'] if g['id'] == 'appels_manquants'), None)
        if appel_gap:
            alerts.append({
                'id': 'missing_rollcalls',
                'category': CATEGORY_IMPORTANT,
                'priority': 2,
                'message': appel_gap['label'],
                'detail': 'Des classes n’ont pas de soumission d’appel sur les 5 derniers jours ouvrés.',
                'value': None,
                'period': '5 jours ouvrés',
                'source': 'SoumissionListePresence',
                'url': _url('directeur:suivi_presence'),
                'permission': 'presences_liste',
            })

        from school_admin.model.presence_model import Presence

        eleve_ids = list(eleves_qs(ctx).values_list('id', flat=True))
        if eleve_ids:
            qs = Presence.objects.filter(
                etablissement=ctx.etablissement,
                eleve_id__in=eleve_ids,
                statut='absent',
            )
            if ctx.annee_scolaire:
                qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
            n_gt12 = sum(
                1
                for row in qs.values('eleve_id').annotate(n=Count('id'))
                if row['n'] > 12
            )
            if n_gt12:
                alerts.append({
                    'id': 'students_gt_12_absences',
                    'category': CATEGORY_WATCH,
                    'priority': 3,
                    'message': f'{n_gt12} {_apprenant(ctx)}(s) avec plus de 12 absences non justifiées',
                    'detail': 'Comptage d’appels absents (NJ) sur l’année consultée. Les retards ne sont pas des absences.',
                    'value': n_gt12,
                    'period': period_label,
                    'source': 'Presence.statut=absent',
                    'url': _url('directeur:suivi_presence'),
                    'permission': 'presences_liste',
                })

    if user_may(ctx, 'notes_justifications_voir'):
        from school_admin.model.justification_note_model import JustificationNote

        just_qs = JustificationNote.objects.filter(
            etablissement=ctx.etablissement,
            statut=JustificationNote.STATUT_EN_ATTENTE,
        )
        if ctx.annee_scolaire:
            just_qs = just_qs.filter(annee_scolaire=ctx.annee_scolaire)
        n_just = just_qs.count()
        if n_just:
            alerts.append({
                'id': 'pending_note_justifications',
                'category': CATEGORY_IMPORTANT,
                'priority': 2,
                'message': f'{n_just} justification(s) de note en attente',
                'detail': 'Demandes de modification de note non encore traitées.',
                'value': n_just,
                'period': period_label,
                'source': 'JustificationNote.statut=en_attente',
                'url': _url('directeur:justifications_notes'),
                'permission': 'notes_justifications_voir',
            })

    if user_may(ctx, 'notes_liste') and ctx.periode_scolaire:
        from school_admin.services.dashboard.metrics.engine import compute_metric

        success = compute_metric('success_rate', ctx)
        extra = success.get('extra') or {}
        n_sous = extra.get('sous_seuil') or 0
        if not success.get('empty') and n_sous:
            alerts.append({
                'id': 'students_below_threshold',
                'category': CATEGORY_WATCH,
                'priority': 3,
                'message': (
                    f"{n_sous} {_apprenant(ctx)}(s) sous le seuil de passage "
                    f"({extra.get('seuil')} /20)"
                ),
                'detail': (
                    'Moyennes générales de la période consultée inférieures '
                    'au seuil de réussite configuré.'
                ),
                'value': n_sous,
                'period': extra.get('periode') or period_label,
                'source': 'MoyennePeriode.moyenne_generale',
                'url': _url('directeur:notes_et_resultats'),
                'permission': 'notes_liste',
            })

        completeness = build_completeness_block(ctx)
        bulletin_gap = next(
            (g for g in completeness['gaps'] if g['id'] in ('bulletins_non_publies', 'bulletins_absents')),
            None,
        )
        if bulletin_gap and bulletin_gap['id'] == 'bulletins_non_publies':
            alerts.append({
                'id': 'unpublished_bulletins',
                'category': CATEGORY_IMPORTANT,
                'priority': 2,
                'message': bulletin_gap['label'],
                'detail': 'Des moyennes générales existent mais le bulletin n’est pas encore publié.',
                'value': None,
                'period': ctx.periode_scolaire.nom_periode,
                'source': 'MoyennePeriode.est_publie',
                'url': _url('directeur:notes_et_resultats'),
                'permission': 'notes_liste',
            })

    if user_may(ctx, 'notes_liste') and ctx.annee_scolaire:
        from school_admin.model.releve_notes_model import ReleveNotes

        releves = apply_classe_filters(
            ReleveNotes.objects.filter(
                etablissement=ctx.etablissement,
                annee_scolaire=ctx.annee_scolaire,
                soumis=False,
            ),
            ctx,
            classe_field='classe',
        )
        n_releves = releves.count()
        if n_releves:
            alerts.append({
                'id': 'unsubmitted_gradebooks',
                'category': CATEGORY_WATCH,
                'priority': 3,
                'message': f'{n_releves} relevé(s) de notes non soumis',
                'detail': 'Relevés encore en cours de saisie.',
                'value': n_releves,
                'period': period_label,
                'source': 'ReleveNotes.soumis=False',
                'url': _url('directeur:notes_et_resultats'),
                'permission': 'notes_liste',
            })

    alerts.sort(key=lambda a: a['priority'])
    return alerts
