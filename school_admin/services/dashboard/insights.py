"""Insights déterministes v1 — aucune causalité, aucune prédiction."""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.engine import compute_metric
from school_admin.services.dashboard.permissions import user_may

SEVERITY_LABELS = {
    'warning': 'À surveiller',
    'info': 'Information',
}

ALERT_INSIGHT_IDS = (
    'missing_rollcalls',
    'unsubmitted_gradebooks',
    'payments_overdue',
    'students_below_threshold',
    'unpublished_bulletins',
)


def _url(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return ''


def _with_display(item: dict) -> dict:
    payload = dict(item)
    payload['label'] = SEVERITY_LABELS.get(payload.get('severity'), 'Information')
    why = payload.get('why') or {}
    payload['why_label'] = why.get('note') or why.get('period') or ''
    return payload


def build_insight_bar(insights: list[dict], completeness: dict) -> dict:
    """Bandeau « À retenir » : insights + filet de fiabilité, jamais inventé."""
    items = [_with_display(item) for item in insights[:4]]
    gaps = completeness.get('gaps') or []
    status = completeness.get('status') or 'complete'
    if not items and gaps:
        for gap in gaps[:3]:
            items.append({
                'id': f"gap_{gap['id']}",
                'severity': 'info',
                'label': 'Fiabilité',
                'message': gap['label'],
                'why_label': completeness.get('detail') or '',
                'url': _url(gap.get('url_name') or ''),
            })
    empty = not items
    return {
        'items': items,
        'empty': empty,
        'empty_reason': 'Aucun écart sur les règles de pilotage actives.' if empty else '',
        'partial': status != 'complete',
        'partial_detail': completeness.get('detail') or '',
        'gaps': gaps,
    }


def build_dashboard_insights(ctx: DashboardContext, alerts: list[dict] | None = None) -> list[dict]:
    insights = []
    if user_may(ctx, 'presences_liste'):
        trend = compute_metric('attendance_trend', ctx)
        if not trend.get('empty'):
            current = trend.get('rate_7')
            baseline = trend.get('rate_30')
            if current is not None and baseline is not None and current < baseline:
                delta = round(current - baseline, 1)
                insights.append({
                    'id': 'presence_below_30d_avg',
                    'severity': 'warning',
                    'message': (
                        f'Le taux de présence des 7 derniers jours ({current} %) '
                        f'est inférieur à celui des 30 derniers jours ({baseline} %).'
                    ),
                    'why': {
                        'metric': 'attendance_rate',
                        'value': current,
                        'threshold': baseline,
                        'period': 'rolling_7',
                        'baseline': 'rolling_30',
                        'note': 'Les retards ne sont pas comptés comme présents.',
                    },
                    'url': _url('directeur:suivi_presence'),
                })

    if user_may(ctx, 'comptabilite_voir'):
        collection = compute_metric('collection_rate', ctx)
        if (
            not collection.get('empty')
            and collection.get('value') is not None
            and collection['value'] < 70
        ):
            insights.append({
                'id': 'collection_below_70',
                'severity': 'warning',
                'message': (
                    f"Le taux de recouvrement ({collection['value']} %) "
                    f"est inférieur à 70 % sur la session consultée."
                ),
                'why': {
                    'metric': 'collection_rate',
                    'value': collection['value'],
                    'threshold': 70,
                    'period': ctx.annee_scolaire.libelle if ctx.annee_scolaire else '',
                    'baseline': 'fixed_threshold',
                    'note': collection.get('definition'),
                },
                'url': _url('directeur:liste_impayes_directeur'),
            })

    if user_may(ctx, 'notes_liste'):
        success = compute_metric('success_rate', ctx)
        comparison = success.get('comparison') or {}
        if (
            not success.get('empty')
            and comparison.get('compatible')
            and comparison.get('delta') is not None
            and comparison['delta'] < 0
        ):
            insights.append({
                'id': 'success_below_previous_period',
                'severity': 'warning',
                'message': (
                    f"Le taux de réussite ({success['value']} %) est inférieur "
                    f"à la période précédente ({comparison['reference_value']} %)."
                ),
                'why': {
                    'metric': 'success_rate',
                    'value': success['value'],
                    'threshold': comparison['reference_value'],
                    'period': comparison.get('period_label'),
                    'baseline': 'previous_period',
                    'note': success.get('definition'),
                },
                'url': _url('directeur:notes_et_resultats'),
            })

    for alert in (alerts or []):
        if alert['id'] in ALERT_INSIGHT_IDS:
            insights.append({
                'id': f"insight_{alert['id']}",
                'severity': 'info' if alert['category'] == 'INFO' else 'warning',
                'message': alert['message'],
                'why': {
                    'metric': alert['id'],
                    'value': alert.get('value'),
                    'threshold': None,
                    'period': alert.get('period'),
                    'source': alert.get('source'),
                },
                'url': alert.get('url') or '',
            })

    # Dédupliquer par id, max 5
    seen = set()
    unique = []
    for item in insights:
        if item['id'] in seen:
            continue
        seen.add(item['id'])
        unique.append(item)
    return unique[:5]
