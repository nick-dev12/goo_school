"""
Contexte unifié du dashboard directeur (D0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, FrozenSet, Optional, Set

from django.utils import timezone

VUE_EXECUTIVE = 'executive'
VUE_ANALYTIQUE = 'analytique'
VUE_CHOICES = frozenset({VUE_EXECUTIVE, VUE_ANALYTIQUE})
CYCLE_VALUES = frozenset({'maternelle', 'primaire', 'college', 'lycee', 'superieur'})


@dataclass(frozen=True)
class DashboardFilters:
    cycle: str = ''
    niveau: str = ''
    filiere: str = ''
    classe_id: Optional[int] = None
    periode_id: Optional[int] = None


@dataclass
class DashboardContext:
    etablissement: Any
    annee_scolaire: Any
    annee_scolaire_reellement_active: Any
    periode_scolaire: Any
    filters: DashboardFilters
    vue: str
    is_directeur: bool
    permissions: Optional[FrozenSet[str]]
    today: date
    computed_at: datetime = field(default_factory=lambda: timezone.now())

    @property
    def is_executive(self) -> bool:
        return self.vue == VUE_EXECUTIVE

    def freshness_meta(self) -> dict:
        local = timezone.localtime(self.computed_at)
        return {
            'computed_at': self.computed_at.isoformat(),
            'freshness_label': f"Mis à jour à {local.strftime('%H:%M')}",
            'is_live': False,
        }


def _parse_int_param(raw) -> Optional[int]:
    if raw in (None, ''):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_filters(request) -> DashboardFilters:
    cycle = (request.GET.get('cycle') or '').strip().lower()
    if cycle not in CYCLE_VALUES:
        cycle = ''
    return DashboardFilters(
        cycle=cycle,
        niveau=(request.GET.get('niveau') or '').strip(),
        filiere=(request.GET.get('filiere') or '').strip(),
        classe_id=_parse_int_param(request.GET.get('classe')),
        periode_id=_parse_int_param(request.GET.get('periode')),
    )


def resolve_periode_scolaire(etablissement, annee_scolaire, periode_id, fallback):
    if not periode_id:
        return fallback
    from school_admin.model.periode_model import PeriodeScolaire

    qs = PeriodeScolaire.objects.filter(
        id=periode_id,
        etablissement=etablissement,
    )
    if annee_scolaire:
        qs = qs.filter(annee_scolaire_fk=annee_scolaire)
    return qs.first() or fallback


def _parse_vue(request) -> str:
    vue = (request.GET.get('vue') or VUE_EXECUTIVE).strip().lower()
    if vue not in VUE_CHOICES:
        return VUE_EXECUTIVE
    return vue


def build_dashboard_context(
    request,
    *,
    etablissement,
    annee_scolaire,
    annee_scolaire_reellement_active,
    periode_scolaire,
    is_directeur: bool,
    permissions: Optional[Set[str]] = None,
) -> DashboardContext:
    perm_frozen = frozenset(permissions) if permissions is not None else None
    filters = _parse_filters(request)
    periode = resolve_periode_scolaire(
        etablissement,
        annee_scolaire,
        filters.periode_id,
        periode_scolaire,
    )
    return DashboardContext(
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        annee_scolaire_reellement_active=annee_scolaire_reellement_active,
        periode_scolaire=periode,
        filters=filters,
        vue=_parse_vue(request),
        is_directeur=is_directeur,
        permissions=perm_frozen,
        today=timezone.localdate(),
    )
