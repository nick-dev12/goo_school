"""
Registre des métriques dashboard (Metrics Engine — D0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from school_admin.services.dashboard.context import DashboardContext

MetricComputeFn = Callable[[DashboardContext], dict]


@dataclass(frozen=True)
class MetricSpec:
    id: str
    label: str
    unit: str
    source: str
    period_kind: str
    comparison_kind: str
    permission: Optional[str]
    definition: str
    compute: MetricComputeFn


METRIC_REGISTRY: dict[str, MetricSpec] = {}


def register_metric(spec: MetricSpec) -> MetricSpec:
    if spec.id in METRIC_REGISTRY:
        raise ValueError(f'Metric already registered: {spec.id}')
    METRIC_REGISTRY[spec.id] = spec
    return spec


def get_metric_spec(metric_id: str) -> Optional[MetricSpec]:
    return METRIC_REGISTRY.get(metric_id)


def list_metric_ids() -> list[str]:
    return sorted(METRIC_REGISTRY.keys())
