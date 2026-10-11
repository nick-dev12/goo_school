"""
Métriques pédagogie (D3).

Règle canonique : un élève réussit si sa moyenne générale de période
est ≥ seuil de passage (StandardsReussite.moyenne_passage, sinon 10/20).
Aucune moyenne → empty, jamais un 0 % inventé.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q
from django.urls import NoReverseMatch, reverse

from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.registry import MetricSpec, register_metric
from school_admin.services.dashboard.querysets import apply_classe_filters, eleves_qs

SUCCESS_DEFINITION = (
    'Part des moyennes générales de période ≥ seuil de passage. '
    'Le seuil vient des standards de réussite de l’établissement, sinon 10/20.'
)
AVERAGE_DEFINITION = (
    'Moyenne arithmétique des moyennes générales de période calculées. '
    'Les élèves sans moyenne ne sont pas comptés.'
)
DISTRIBUTION_DEFINITION = (
    'Répartition des moyennes générales par tranches. '
    'Uniquement les bulletins déjà calculés pour la période consultée.'
)

GRADE_BUCKETS = (
    ('< 8', Decimal('0'), Decimal('8')),
    ('8 – 10', Decimal('8'), Decimal('10')),
    ('10 – 12', Decimal('10'), Decimal('12')),
    ('12 – 14', Decimal('12'), Decimal('14')),
    ('14 – 16', Decimal('14'), Decimal('16')),
    ('≥ 16', Decimal('16'), Decimal('20.01')),
)

AT_RISK_LIMIT = 8
CLASSES_LIMIT = 12


def _seuil_passage(ctx: DashboardContext) -> Decimal:
    from school_admin.model.standards_reussite_model import StandardsReussite

    standards = StandardsReussite.objects.filter(
        etablissement=ctx.etablissement
    ).first()
    if standards and standards.moyenne_passage is not None:
        return Decimal(str(standards.moyenne_passage))
    return Decimal('10.00')


def _safe_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct(part: int, total: int) -> float | None:
    if not total:
        return None
    return round(part / total * 100, 1)


def _notes_url() -> str:
    try:
        return reverse('directeur:notes_et_resultats')
    except NoReverseMatch:
        return ''


def _eleve_url(eleve_id: int) -> str:
    try:
        return reverse('secretaire:detail_eleve', args=[eleve_id])
    except NoReverseMatch:
        return ''


def _empty(metric_id: str, label: str, unit: str, reason: str, definition: str) -> dict:
    return {
        'id': metric_id,
        'label': label,
        'value': None,
        'unit': unit,
        'empty': True,
        'empty_reason': reason,
        'definition': definition,
        'url': _notes_url(),
    }


def _moyennes_qs(ctx: DashboardContext, periode=None):
    periode = periode or ctx.periode_scolaire
    if not periode:
        return None
    eleve_ids = list(eleves_qs(ctx).values_list('id', flat=True))
    if not eleve_ids:
        return MoyennePeriode.objects.none()
    qs = MoyennePeriode.objects.filter(
        etablissement=ctx.etablissement,
        periode=periode,
        est_moyenne_generale=True,
        moyenne_generale__isnull=False,
        eleve_id__in=eleve_ids,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire=ctx.annee_scolaire)
    return apply_classe_filters(qs, ctx, classe_field='eleve__classe')


def _previous_periode(ctx: DashboardContext):
    if not ctx.periode_scolaire:
        return None
    qs = PeriodeScolaire.objects.filter(
        etablissement=ctx.etablissement,
        date_fin__lt=ctx.periode_scolaire.date_debut,
    )
    if ctx.annee_scolaire:
        qs = qs.filter(annee_scolaire_fk=ctx.annee_scolaire)
    return qs.order_by('-date_fin').first()


def _summarize(qs, seuil: Decimal) -> dict | None:
    if qs is None:
        return None
    agg = qs.aggregate(
        n=Count('id'),
        moyenne=Avg('moyenne_generale'),
        reussis=Count('id', filter=Q(moyenne_generale__gte=seuil)),
    )
    total = agg['n'] or 0
    if not total:
        return None
    reussis = agg['reussis'] or 0
    return {
        'nb': total,
        'reussis': reussis,
        'sous_seuil': total - reussis,
        'taux': _pct(reussis, total),
        'moyenne': round(float(agg['moyenne']), 2) if agg['moyenne'] is not None else None,
        'seuil': float(seuil),
    }


def _comparison(current: dict, previous: dict | None, periode) -> dict | None:
    if not previous or previous.get('taux') is None or current.get('taux') is None:
        return None
    delta = round(current['taux'] - previous['taux'], 1)
    return {
        'reference_value': previous['taux'],
        'delta': delta,
        'delta_label': f'{delta:+g} points',
        'period_label': f'versus {periode.nom_periode}',
        'compatible': True,
    }


def _success_rate(ctx: DashboardContext) -> dict:
    if not ctx.periode_scolaire:
        return _empty(
            'success_rate',
            'Taux de réussite',
            '%',
            'Aucune période scolaire sélectionnée.',
            SUCCESS_DEFINITION,
        )
    seuil = _seuil_passage(ctx)
    current = _summarize(_moyennes_qs(ctx), seuil)
    if current is None:
        return _empty(
            'success_rate',
            'Taux de réussite',
            '%',
            'Aucune moyenne générale calculée pour cette période.',
            SUCCESS_DEFINITION,
        )
    payload = {
        'id': 'success_rate',
        'label': 'Taux de réussite',
        'value': current['taux'],
        'unit': '%',
        'empty': False,
        'definition': SUCCESS_DEFINITION,
        'url': _notes_url(),
        'extra': {
            'seuil': current['seuil'],
            'nb': current['nb'],
            'reussis': current['reussis'],
            'sous_seuil': current['sous_seuil'],
            'periode': ctx.periode_scolaire.nom_periode,
        },
    }
    prev_periode = _previous_periode(ctx)
    if prev_periode:
        previous = _summarize(_moyennes_qs(ctx, prev_periode), seuil)
        comparison = _comparison(current, previous, prev_periode)
        if comparison:
            payload['comparison'] = comparison
    return payload


def _average_grade(ctx: DashboardContext) -> dict:
    if not ctx.periode_scolaire:
        return _empty(
            'average_grade',
            'Moyenne générale',
            '/20',
            'Aucune période scolaire sélectionnée.',
            AVERAGE_DEFINITION,
        )
    seuil = _seuil_passage(ctx)
    current = _summarize(_moyennes_qs(ctx), seuil)
    if current is None or current['moyenne'] is None:
        return _empty(
            'average_grade',
            'Moyenne générale',
            '/20',
            'Aucune moyenne générale calculée pour cette période.',
            AVERAGE_DEFINITION,
        )
    payload = {
        'id': 'average_grade',
        'label': 'Moyenne générale',
        'value': current['moyenne'],
        'unit': '/20',
        'empty': False,
        'definition': AVERAGE_DEFINITION,
        'url': _notes_url(),
        'extra': {
            'seuil': current['seuil'],
            'nb': current['nb'],
            'periode': ctx.periode_scolaire.nom_periode,
        },
    }
    prev_periode = _previous_periode(ctx)
    if prev_periode:
        previous = _summarize(_moyennes_qs(ctx, prev_periode), seuil)
        if previous and previous.get('moyenne') is not None:
            delta = round(current['moyenne'] - previous['moyenne'], 2)
            payload['comparison'] = {
                'reference_value': previous['moyenne'],
                'delta': delta,
                'delta_label': f'{delta:+g} /20',
                'period_label': f'versus {prev_periode.nom_periode}',
                'compatible': True,
            }
    return payload


def _grade_distribution(ctx: DashboardContext) -> dict:
    if not ctx.periode_scolaire:
        return _empty(
            'grade_distribution',
            'Répartition des moyennes',
            'count',
            'Aucune période scolaire sélectionnée.',
            DISTRIBUTION_DEFINITION,
        )
    qs = _moyennes_qs(ctx)
    seuil = _seuil_passage(ctx)
    current = _summarize(qs, seuil)
    if current is None:
        return _empty(
            'grade_distribution',
            'Répartition des moyennes',
            'count',
            'Aucune moyenne générale calculée pour cette période.',
            DISTRIBUTION_DEFINITION,
        )

    filters = {}
    for key, (_label, low, high) in enumerate(GRADE_BUCKETS):
        filters[f'b{key}'] = Count(
            'id',
            filter=Q(moyenne_generale__gte=low, moyenne_generale__lt=high),
        )
    buckets = qs.aggregate(**filters)
    labels = [row[0] for row in GRADE_BUCKETS]
    values = [buckets.get(f'b{i}') or 0 for i in range(len(GRADE_BUCKETS))]

    at_risk_qs = (
        qs.filter(moyenne_generale__lt=seuil)
        .select_related('eleve', 'eleve__classe')
        .order_by('moyenne_generale', 'eleve__nom')
    )
    at_risk = []
    for row in at_risk_qs[:AT_RISK_LIMIT]:
        at_risk.append({
            'eleve_id': row.eleve_id,
            'nom': row.eleve.nom_complet,
            'classe': row.eleve.classe.nom if row.eleve.classe_id else '—',
            'moyenne': _safe_float(row.moyenne_generale),
            'url': _eleve_url(row.eleve_id),
        })

    class_rows = []
    class_qs = (
        qs.values('eleve__classe_id', 'eleve__classe__nom')
        .annotate(
            n=Count('id'),
            moyenne=Avg('moyenne_generale'),
            reussis=Count('id', filter=Q(moyenne_generale__gte=seuil)),
        )
        .order_by('moyenne')
    )
    for row in class_qs[:CLASSES_LIMIT]:
        n = row['n'] or 0
        class_rows.append({
            'classe_id': row['eleve__classe_id'],
            'classe': row['eleve__classe__nom'] or '—',
            'n': n,
            'moyenne': round(float(row['moyenne']), 2) if row['moyenne'] is not None else None,
            'taux': _pct(row['reussis'] or 0, n),
        })

    cycle_labels = {
        'maternelle': 'Maternelle',
        'primaire': 'Primaire',
        'college': 'Collège',
        'lycee': 'Lycée',
        'superieur': 'Supérieur',
    }
    by_cycle = []
    cycle_qs = (
        qs.values('eleve__classe__niveau')
        .annotate(
            n=Count('id'),
            reussis=Count('id', filter=Q(moyenne_generale__gte=seuil)),
        )
        .order_by('eleve__classe__niveau')
    )
    for row in cycle_qs:
        niveau = row['eleve__classe__niveau']
        n = row['n'] or 0
        by_cycle.append({
            'cycle': cycle_labels.get(niveau, niveau or '—'),
            'n': n,
            'taux': _pct(row['reussis'] or 0, n),
        })

    return {
        'id': 'grade_distribution',
        'label': 'Répartition des moyennes',
        'value': current['nb'],
        'unit': 'count',
        'empty': False,
        'definition': DISTRIBUTION_DEFINITION,
        'url': _notes_url(),
        'extra': {
            'seuil': current['seuil'],
            'nb': current['nb'],
            'sous_seuil': current['sous_seuil'],
            'periode': ctx.periode_scolaire.nom_periode,
            'at_risk': at_risk,
            'classes': class_rows,
            'by_cycle': by_cycle,
        },
        'charts': {
            'labels': labels,
            'values': values,
            'by_cycle': {
                'labels': [r['cycle'] for r in by_cycle if r['taux'] is not None],
                'values': [r['taux'] for r in by_cycle if r['taux'] is not None],
            },
            'question': 'Comment se répartissent les moyennes générales ?',
        },
    }


def register_pedagogie_metrics() -> None:
    register_metric(
        MetricSpec(
            id='success_rate',
            label='Taux de réussite',
            unit='%',
            source='MoyennePeriode + StandardsReussite.moyenne_passage',
            period_kind='period_scolaire',
            comparison_kind='previous_period',
            permission='notes_liste',
            definition=SUCCESS_DEFINITION,
            compute=_success_rate,
        )
    )
    register_metric(
        MetricSpec(
            id='average_grade',
            label='Moyenne générale',
            unit='/20',
            source='MoyennePeriode.moyenne_generale',
            period_kind='period_scolaire',
            comparison_kind='previous_period',
            permission='notes_liste',
            definition=AVERAGE_DEFINITION,
            compute=_average_grade,
        )
    )
    register_metric(
        MetricSpec(
            id='grade_distribution',
            label='Répartition des moyennes',
            unit='count',
            source='MoyennePeriode (tranches + classes + élèves sous seuil)',
            period_kind='period_scolaire',
            comparison_kind='none',
            permission='notes_liste',
            definition=DISTRIBUTION_DEFINITION,
            compute=_grade_distribution,
        )
    )
