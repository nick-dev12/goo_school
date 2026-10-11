"""
Contrats JSON stables pour blocs dashboard (D0).

Utilisés par templates (json_script), tests et futur endpoint partial.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class MetricComparison(TypedDict, total=False):
    reference_value: float
    delta: float
    delta_label: str
    period_label: str
    compatible: bool


class MetricValue(TypedDict, total=False):
    id: str
    label: str
    value: float | int | None
    unit: str
    empty: bool
    empty_reason: str
    comparison: MetricComparison
    definition: str


class BlockMeta(TypedDict, total=False):
    computed_at: str
    freshness_label: str
    is_live: bool
    completeness: Literal['complete', 'partial', 'unknown']
    completeness_detail: str


class BlockPayload(TypedDict, total=False):
    block_id: str
    title: str
    metrics: list[MetricValue]
    charts: dict[str, Any]
    tables: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    insights: list[dict[str, Any]]
    meta: BlockMeta
    empty: bool
    empty_reason: str


AlertCategory = Literal['URGENT', 'IMPORTANT', 'SURVEILLER', 'INFO']
