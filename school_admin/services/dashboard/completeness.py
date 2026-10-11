"""Complétude des données (D1 — minimum viable)."""
from __future__ import annotations

from datetime import timedelta

from school_admin.model.classe_model import Classe
from school_admin.model.presence_model import SoumissionListePresence
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.querysets import apply_classe_filters


def _may(ctx: DashboardContext, permission: str) -> bool:
    if ctx.is_directeur:
        return True
    if ctx.permissions is None:
        return False
    return permission in ctx.permissions


def build_completeness_block(ctx: DashboardContext) -> dict:
    gaps = []

    if _may(ctx, 'presences_liste'):
        classes = apply_classe_filters(
            Classe.objects.filter(etablissement=ctx.etablissement, actif=True),
            ctx,
        )
        total_classes = classes.count()
        if total_classes:
            dates = []
            cursor = ctx.today
            while len(dates) < 5:
                if cursor.weekday() < 5:
                    dates.append(cursor)
                cursor -= timedelta(days=1)
            soum = SoumissionListePresence.objects.filter(
                etablissement=ctx.etablissement,
                date__gte=min(dates),
                date__lte=ctx.today,
            )
            if ctx.annee_scolaire:
                soum = soum.filter(annee_scolaire=ctx.annee_scolaire)
            covered = set(soum.values_list('classe_id', flat=True))
            missing = total_classes - len(covered & set(classes.values_list('id', flat=True)))
            if missing:
                gaps.append({
                    'id': 'appels_manquants',
                    'label': f'{missing} classe(s) sans appel sur les 5 derniers jours ouvrés',
                    'url_name': 'directeur:suivi_presence',
                })

    if _may(ctx, 'bulletins_voir') and ctx.periode_scolaire:
        from school_admin.model.moyenne_periode_model import MoyennePeriode

        qs = MoyennePeriode.objects.filter(
            etablissement=ctx.etablissement,
            periode=ctx.periode_scolaire,
            est_moyenne_generale=True,
        )
        if ctx.annee_scolaire:
            qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
        total = qs.count()
        publies = qs.filter(est_publie=True).count()
        if total and publies < total:
            gaps.append({
                'id': 'bulletins_non_publies',
                'label': f'{total - publies} bulletin(s) non publié(s) sur {total} pour la période',
                'url_name': 'directeur:notes_et_resultats',
            })
        elif not total:
            gaps.append({
                'id': 'bulletins_absents',
                'label': 'Aucun bulletin de moyenne générale pour la période consultée',
                'url_name': 'directeur:notes_et_resultats',
            })

    if gaps:
        status = 'partial'
        detail = 'Certaines données ne sont pas encore disponibles.'
    else:
        status = 'complete'
        detail = 'Aucun écart détecté sur les contrôles D1 (appels récents, bulletins).'

    return {
        'block_id': 'completeness',
        'title': 'Fiabilité des données',
        'status': status,
        'detail': detail,
        'gaps': gaps,
        'meta': ctx.freshness_meta(),
        'empty': False,
    }
