"""Querysets filtrés du dashboard (établissement + année + filtres GET)."""
from __future__ import annotations

from django.db.models import QuerySet

from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.services.dashboard.context import CYCLE_VALUES, DashboardContext


def apply_classe_filters(qs: QuerySet, ctx: DashboardContext, *, classe_field: str = '') -> QuerySet:
    cycle = ctx.filters.cycle
    if cycle in CYCLE_VALUES:
        prefix = f'{classe_field}__' if classe_field else ''
        qs = qs.filter(**{f'{prefix}niveau': cycle})
    if ctx.filters.classe_id:
        owns_classe = Classe.objects.filter(
            id=ctx.filters.classe_id,
            etablissement=ctx.etablissement,
        ).exists()
        if owns_classe:
            if classe_field:
                qs = qs.filter(**{f'{classe_field}_id': ctx.filters.classe_id})
            else:
                qs = qs.filter(id=ctx.filters.classe_id)
    if ctx.filters.filiere:
        try:
            filiere_id = int(ctx.filters.filiere)
        except (TypeError, ValueError):
            return qs
        prefix = f'{classe_field}__' if classe_field else ''
        qs = qs.filter(**{f'{prefix}department_id': filiere_id})
    return qs


def inscription_qs(ctx: DashboardContext) -> QuerySet:
    qs = InscriptionEleve.objects.filter(etablissement=ctx.etablissement)
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    else:
        return qs.none()
    return apply_classe_filters(qs, ctx, classe_field='classe')


def eleves_qs(ctx: DashboardContext) -> QuerySet:
    eleve_ids = inscription_qs(ctx).exclude(eleve_id__isnull=True).values_list('eleve_id', flat=True)
    return Eleve.objects.filter(
        id__in=eleve_ids,
        etablissement=ctx.etablissement,
        actif=True,
    )


def classes_qs(ctx: DashboardContext) -> QuerySet:
    qs = Classe.objects.filter(etablissement=ctx.etablissement, actif=True)
    return apply_classe_filters(qs, ctx)


def comptabilite_qs(ctx: DashboardContext) -> QuerySet:
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve

    if not ctx.annee_scolaire:
        return ComptabiliteEleve.objects.none()
    eleve_ids = list(eleves_qs(ctx).values_list('id', flat=True))
    if not eleve_ids:
        return ComptabiliteEleve.objects.none()
    return (
        ComptabiliteEleve.objects.filter(
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            eleve_id__in=eleve_ids,
        )
        .select_related('eleve', 'eleve__classe')
        .prefetch_related('frais_inscriptions', 'mensualites', 'frais_annexes')
    )
