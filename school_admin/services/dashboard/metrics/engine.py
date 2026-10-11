"""
Exécution des métriques enregistrées (Metrics Engine).
"""
from __future__ import annotations

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY, get_metric_spec


def _metrics_bootstrapped() -> bool:
    return bool(METRIC_REGISTRY)


def ensure_metrics_registered() -> None:
    if _metrics_bootstrapped():
        return
    from school_admin.services.dashboard.metrics.effectifs import register_effectifs_metrics
    from school_admin.services.dashboard.metrics.finance import register_finance_metrics
    from school_admin.services.dashboard.metrics.pedagogie import register_pedagogie_metrics
    from school_admin.services.dashboard.metrics.presence import register_presence_metrics

    register_effectifs_metrics()
    register_presence_metrics()
    register_pedagogie_metrics()
    register_finance_metrics()


def _user_may_compute(ctx: DashboardContext, permission: str | None) -> bool:
    if ctx.is_directeur:
        return True
    if permission is None:
        return False
    if ctx.permissions is None:
        return False
    return permission in ctx.permissions


def compute_metric(metric_id: str, ctx: DashboardContext) -> dict:
    ensure_metrics_registered()
    spec = get_metric_spec(metric_id)
    if spec is None:
        return {
            'id': metric_id,
            'empty': True,
            'empty_reason': 'Métrique inconnue.',
        }
    if not _user_may_compute(ctx, spec.permission):
        return {
            'id': metric_id,
            'empty': True,
            'empty_reason': 'Accès non autorisé.',
        }
    return spec.compute(ctx)
