"""Permissions dashboard (directeur = tout)."""
from __future__ import annotations

from school_admin.services.dashboard.context import DashboardContext


def user_may(ctx: DashboardContext, permission: str) -> bool:
    if ctx.is_directeur:
        return True
    if ctx.permissions is None:
        return False
    return permission in ctx.permissions
