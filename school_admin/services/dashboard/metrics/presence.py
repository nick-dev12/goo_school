"""
Métriques présence.

Règle canonique : un retard n’est PAS une présence.
taux = présents / total des enregistrements (présent, absent, justifié, retard).
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q

from school_admin.model.presence_model import Presence
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.registry import MetricSpec, register_metric
from school_admin.services.dashboard.querysets import apply_classe_filters, eleves_qs as scoped_eleves_qs


ATTENDANCE_DEFINITION = (
    'Présents / total des enregistrements (présents, absents, justifiés, retards). '
    'Un retard n’est pas une présence.'
)


def _presence_base_qs(ctx: DashboardContext):
    eleve_ids = list(scoped_eleves_qs(ctx).values_list('id', flat=True))
    qs = Presence.objects.filter(etablissement=ctx.etablissement)
    if eleve_ids:
        qs = qs.filter(eleve_id__in=eleve_ids)
    else:
        qs = qs.none()
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return apply_classe_filters(qs, ctx, classe_field='classe')


def _rate_from_qs(qs) -> float | None:
    agg = qs.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(statut='present')),
    )
    total = agg['total'] or 0
    if not total:
        return None
    return round((agg['presents'] or 0) / total * 100, 1)


def _attendance_rate(ctx: DashboardContext) -> dict:
    from school_admin.services.dashboard_absences_stats import build_dashboard_absences_stats

    data = build_dashboard_absences_stats(
        ctx.etablissement,
        ctx.annee_scolaire,
        scoped_eleves_qs(ctx),
        today=ctx.today,
    )
    if not data['meta']['has_data']:
        return {
            'id': 'attendance_rate',
            'label': 'Taux de présence',
            'value': None,
            'unit': '%',
            'empty': True,
            'empty_reason': 'Aucune donnée de présence sur la période.',
            'definition': ATTENDANCE_DEFINITION,
        }
    kpis = data['kpis']
    payload = {
        'id': 'attendance_rate',
        'label': 'Taux de présence',
        'value': kpis['taux_presence'],
        'unit': '%',
        'empty': False,
        'definition': ATTENDANCE_DEFINITION,
    }
    delta = kpis.get('taux_presence_delta_mois')
    if delta is not None:
        payload['comparison'] = {
            'delta': delta,
            'delta_label': f'{delta:+g} points',
            'period_label': 'vs mois précédent (taux)',
            'compatible': True,
        }
    return payload


def _attendance_trend(ctx: DashboardContext) -> dict:
    qs = _presence_base_qs(ctx)
    start_30 = ctx.today - timedelta(days=29)
    start_7 = ctx.today - timedelta(days=6)
    qs_30 = qs.filter(date__gte=start_30, date__lte=ctx.today)
    qs_7 = qs.filter(date__gte=start_7, date__lte=ctx.today)
    rate_30 = _rate_from_qs(qs_30)
    rate_7 = _rate_from_qs(qs_7)

    daily = (
        qs_30.values('date')
        .annotate(
            total=Count('id'),
            presents=Count('id', filter=Q(statut='present')),
        )
        .order_by('date')
    )
    labels = []
    values = []
    for row in daily:
        if not row['total']:
            continue
        labels.append(row['date'].strftime('%d/%m'))
        values.append(round(row['presents'] / row['total'] * 100, 1))

    empty = rate_7 is None and rate_30 is None
    return {
        'id': 'attendance_trend',
        'label': 'Évolution de la présence',
        'value': rate_7,
        'unit': '%',
        'empty': empty,
        'empty_reason': 'Pas assez d’appels sur les 30 derniers jours.' if empty else '',
        'rate_7': rate_7,
        'rate_30': rate_30,
        'definition': ATTENDANCE_DEFINITION,
        'charts': {
            'labels': labels,
            'values': values,
            'question': 'Comment évolue la présence des élèves ?',
        },
    }


PRESENCE_CLASS_MIN = 3
PRESENCE_WATCH_THRESHOLD = 85.0


def _presence_by_class(ctx: DashboardContext) -> dict:
    qs = _presence_base_qs(ctx)
    rows = (
        qs.values('classe_id', 'classe__nom')
        .annotate(
            total=Count('id'),
            presents=Count('id', filter=Q(statut='present')),
        )
        .filter(total__gte=PRESENCE_CLASS_MIN)
        .order_by('classe__nom')
    )
    items = []
    for row in rows:
        taux = round((row['presents'] / row['total']) * 100, 1) if row['total'] else 0.0
        items.append({
            'classe_id': row['classe_id'],
            'classe': row['classe__nom'] or '—',
            'taux': taux,
            'n': row['total'],
            'watch': taux < PRESENCE_WATCH_THRESHOLD,
        })
    items.sort(key=lambda r: r['taux'])
    empty = not items
    return {
        'id': 'presence_by_class',
        'label': 'Présence par classe',
        'value': None if empty else items[0]['taux'],
        'unit': '%',
        'empty': empty,
        'empty_reason': 'Pas assez d’appels par classe (minimum 3).' if empty else '',
        'definition': ATTENDANCE_DEFINITION + f' Seuil de vigilance : {int(PRESENCE_WATCH_THRESHOLD)} %.',
        'extra': {'rows': items[:12], 'threshold': PRESENCE_WATCH_THRESHOLD},
        'charts': {
            'labels': [r['classe'] for r in items[:12]],
            'values': [r['taux'] for r in items[:12]],
            'colors': ['#ef4444' if r['watch'] else '#10b981' for r in items[:12]],
        },
    }


def register_presence_metrics() -> None:
    register_metric(
        MetricSpec(
            id='attendance_rate',
            label='Taux de présence',
            unit='%',
            source='Presence (présents uniquement, hors retards)',
            period_kind='annee',
            comparison_kind='previous_month',
            permission='presences_liste',
            definition=ATTENDANCE_DEFINITION,
            compute=_attendance_rate,
        )
    )
    register_metric(
        MetricSpec(
            id='attendance_trend',
            label='Évolution de la présence',
            unit='%',
            source='Presence par jour (7 / 30 jours)',
            period_kind='rolling_30',
            comparison_kind='rolling_7_vs_30',
            permission='presences_liste',
            definition=ATTENDANCE_DEFINITION,
            compute=_attendance_trend,
        )
    )
    register_metric(
        MetricSpec(
            id='presence_by_class',
            label='Présence par classe',
            unit='%',
            source='Presence agrégée par classe (min. 3 appels)',
            period_kind='annee',
            comparison_kind='none',
            permission='presences_liste',
            definition=ATTENDANCE_DEFINITION,
            compute=_presence_by_class,
        )
    )
