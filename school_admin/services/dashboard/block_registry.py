"""
Registre des blocs UI dashboard (D0 — structure, compute en D1+).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.contracts import BlockPayload

BlockComputeFn = Callable[[DashboardContext], BlockPayload]


@dataclass(frozen=True)
class DashboardBlockSpec:
    block_id: str
    title: str
    permission: Optional[str]
    executive_visible: bool
    compute: BlockComputeFn


BLOCK_REGISTRY: list[DashboardBlockSpec] = []


def register_block(spec: DashboardBlockSpec) -> DashboardBlockSpec:
    BLOCK_REGISTRY.append(spec)
    return spec
