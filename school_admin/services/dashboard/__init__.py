"""
Tableau de bord directeur — socle (contexte, métriques, blocs).

Voir .cursor/context/feuille_route_dashboard_admin_premium_aria.md
"""

from .context import DashboardContext, DashboardFilters, build_dashboard_context

__all__ = [
    'DashboardContext',
    'DashboardFilters',
    'build_dashboard_context',
]
