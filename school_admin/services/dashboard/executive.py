"""Assemblage du tableau de bord executive (D1)."""
from __future__ import annotations

from school_admin.services.dashboard.alerts import build_dashboard_alerts
from school_admin.services.dashboard.completeness import build_completeness_block
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.filter_options import build_filter_options
from school_admin.services.dashboard.insights import build_dashboard_insights, build_insight_bar
from school_admin.services.dashboard.activity import build_activity_feed
from school_admin.services.dashboard.metrics.engine import compute_metric
from school_admin.services.dashboard.today import build_today_block

KPI_IDS = (
    'student_count',
    'class_capacity',
    'attendance_rate',
    'success_rate',
    'average_grade',
    'collection_rate',
    'outstanding_amount',
)


def _metric_by_id(kpis: list[dict], metric_id: str) -> dict:
    return next((item for item in kpis if item.get('id') == metric_id), {})


def _premium_hero_kpis(kpis: list[dict], completeness: dict) -> list[dict]:
    """Cinq cartes de la maquette — vraies métriques, jamais de chiffres de démo."""
    collection = _metric_by_id(kpis, 'collection_rate')
    extra = collection.get('extra') or {}
    recette = {
        'id': 'school_revenue',
        'label': 'Recettes scolaires',
        'value': extra.get('total_paye') if not collection.get('empty') else None,
        'unit': extra.get('devise') or 'FCFA',
        'empty': bool(collection.get('empty', True)),
        'empty_reason': collection.get('empty_reason') or 'Aucune recette enregistrée.',
        'comparison': collection.get('comparison'),
        'extra': extra,
    }
    gaps = completeness.get('gaps') or []
    dossiers = {
        'id': 'incomplete_files',
        'label': 'Dossiers incomplets',
        'value': len(gaps),
        'unit': 'count',
        'empty': False,
        'empty_reason': '',
        'extra': {
            'detail': completeness.get('detail') or '',
            'partial': completeness.get('status') != 'complete',
        },
    }
    return [
        _metric_by_id(kpis, 'student_count'),
        _metric_by_id(kpis, 'attendance_rate'),
        _metric_by_id(kpis, 'success_rate'),
        recette,
        dossiers,
    ]


def build_executive_dashboard(ctx: DashboardContext) -> dict:
    kpis = [compute_metric(metric_id, ctx) for metric_id in KPI_IDS]
    cycle = compute_metric('cycle_distribution', ctx)
    trend = compute_metric('attendance_trend', ctx)
    presence_classes = compute_metric('presence_by_class', ctx)
    results = compute_metric('grade_distribution', ctx)
    finance = compute_metric('finance_status', ctx)
    alerts = build_dashboard_alerts(ctx)
    insights = build_dashboard_insights(ctx, alerts)
    completeness = build_completeness_block(ctx)
    today = build_today_block(ctx)
    if alerts:
        today['items'].append({
            'id': 'alerts_today',
            'label': 'Alertes à traiter',
            'value': len(alerts),
            'detail': 'règles déterministes',
            'icon': 'fa-bell',
            'empty': False,
        })
    return {
        'kpis': kpis,
        'premium_kpis': _premium_hero_kpis(kpis, completeness),
        'cycle_distribution': cycle,
        'attendance_trend': trend,
        'presence_by_class': presence_classes,
        'results': results,
        'finance': finance,
        'alerts': alerts,
        'insights': insights,
        'insight_bar': build_insight_bar(insights, completeness),
        'today': today,
        'activity': build_activity_feed(ctx),
        'completeness': completeness,
        'filters': build_filter_options(ctx),
        'meta': ctx.freshness_meta(),
    }
