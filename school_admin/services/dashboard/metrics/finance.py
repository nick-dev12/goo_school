"""
Métriques finances (D4).

Règle canonique : taux de recouvrement = total payé / total dû (session consultée).
Aucune charge → empty, jamais un 0 % inventé. Aligné assistant `tool_statistiques_pilotage`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import NoReverseMatch, reverse

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.registry import MetricSpec, register_metric
from school_admin.services.dashboard.querysets import comptabilite_qs

ZERO = Decimal('0.00')

COLLECTION_DEFINITION = (
    'Total payé / total dû sur l’année scolaire consultée, après filtres. '
    'Calcul identique au pilotage assistant vocal.'
)
OUTSTANDING_DEFINITION = (
    'Somme des restes à payer (total dû − total payé, minimum 0) '
    'pour les dossiers comptables du périmètre filtré.'
)
FINANCE_STATUS_DEFINITION = (
    'Répartition des statuts de paiement et encaissements quotidiens sur 30 jours.'
)

STATUT_LABELS = {
    'a_jour': 'À jour',
    'en_retard': 'En retard',
    'impaye': 'Impayé',
}

CLASSES_LIMIT = 12


def _url(name: str) -> str:
    try:
        return reverse(name)
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
        'url': _url('directeur:liste_comptabilite_eleves_directeur'),
    }


def _pct(part: Decimal, total: Decimal) -> float | None:
    if total <= ZERO:
        return None
    return round(float(part / total * 100), 1)


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal('0.01')))


def _aggregate_fiches(qs) -> dict:
    total_du = ZERO
    total_paye = ZERO
    by_class: dict[int, dict] = defaultdict(
        lambda: {'reste': ZERO, 'du': ZERO, 'paye': ZERO, 'n': 0, 'classe': '—'}
    )
    for fiche in qs:
        du = fiche.calculer_total_du()
        paye = fiche.calculer_total_paye()
        total_du += du
        total_paye += paye
        reste = du - paye
        if reste < ZERO:
            reste = ZERO
        classe = fiche.eleve.classe if fiche.eleve_id else None
        if classe:
            row = by_class[classe.id]
            row['classe'] = classe.nom
            row['classe_id'] = classe.id
            row['du'] += du
            row['paye'] += paye
            row['reste'] += reste
            row['n'] += 1

    reste_total = total_du - total_paye
    if reste_total < ZERO:
        reste_total = ZERO

    statuts = {
        row['statut_paiement']: row['n']
        for row in qs.values('statut_paiement').annotate(n=Count('id'))
    }
    classes = sorted(
        by_class.values(),
        key=lambda r: r['reste'],
        reverse=True,
    )[:CLASSES_LIMIT]
    for row in classes:
        row['taux'] = _pct(row['paye'], row['du']) if row['du'] > ZERO else None
        row['reste'] = _money(row['reste'])
        row['du'] = _money(row['du'])

    return {
        'total_du': total_du,
        'total_paye': total_paye,
        'reste': reste_total,
        'nb_fiches': qs.count(),
        'statuts': statuts,
        'classes': classes,
        'nb_impayes': statuts.get('en_retard', 0) + statuts.get('impaye', 0),
        'nb_a_jour': statuts.get('a_jour', 0),
    }


def _previous_annee(ctx: DashboardContext):
    if not ctx.annee_scolaire:
        return None
    from school_admin.model.annee_scolaire_model import AnneeScolaire

    return (
        AnneeScolaire.objects.filter(
            etablissement=ctx.etablissement,
            date_fin__lt=ctx.annee_scolaire.date_debut,
        )
        .order_by('-date_fin')
        .first()
    )


def _collection_for_annee(ctx: DashboardContext, annee) -> tuple[Decimal, Decimal] | None:
    if not annee:
        return None
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve
    from school_admin.services.dashboard.querysets import eleves_qs

    eleve_ids = list(eleves_qs(ctx).values_list('id', flat=True))
    if not eleve_ids:
        return None
    qs = (
        ComptabiliteEleve.objects.filter(
            etablissement=ctx.etablissement,
            annee_scolaire=annee,
            eleve_id__in=eleve_ids,
        )
        .prefetch_related('frais_inscriptions', 'mensualites', 'frais_annexes')
    )
    total_du = ZERO
    total_paye = ZERO
    for fiche in qs:
        total_du += fiche.calculer_total_du()
        total_paye += fiche.calculer_total_paye()
    if total_du <= ZERO:
        return None
    return total_du, total_paye


def _collection_rate(ctx: DashboardContext) -> dict:
    from school_admin.services.recouvrement import devise_etablissement

    if not ctx.annee_scolaire:
        return _empty(
            'collection_rate',
            'Taux de recouvrement',
            '%',
            'Aucune année scolaire sélectionnée.',
            COLLECTION_DEFINITION,
        )
    qs = comptabilite_qs(ctx)
    if not qs.exists():
        return _empty(
            'collection_rate',
            'Taux de recouvrement',
            '%',
            'Aucun dossier comptable sur le périmètre filtré.',
            COLLECTION_DEFINITION,
        )
    agg = _aggregate_fiches(qs)
    if agg['total_du'] <= ZERO:
        return _empty(
            'collection_rate',
            'Taux de recouvrement',
            '%',
            'Aucune charge scolarité enregistrée pour cette session.',
            COLLECTION_DEFINITION,
        )
    devise = devise_etablissement(ctx.etablissement)
    rate = _pct(agg['total_paye'], agg['total_du'])
    payload = {
        'id': 'collection_rate',
        'label': 'Taux de recouvrement',
        'value': rate,
        'unit': '%',
        'empty': False,
        'definition': COLLECTION_DEFINITION,
        'url': _url('directeur:liste_comptabilite_eleves_directeur'),
        'extra': {
            'devise': devise,
            'total_du': _money(agg['total_du']),
            'total_paye': _money(agg['total_paye']),
            'reste': _money(agg['reste']),
            'nb_fiches': agg['nb_fiches'],
            'nb_impayes': agg['nb_impayes'],
        },
    }
    prev = _previous_annee(ctx)
    if prev:
        prev_totals = _collection_for_annee(ctx, prev)
        if prev_totals:
            prev_rate = _pct(prev_totals[1], prev_totals[0])
            if prev_rate is not None and rate is not None:
                delta = round(rate - prev_rate, 1)
                payload['comparison'] = {
                    'reference_value': prev_rate,
                    'delta': delta,
                    'delta_label': f'{delta:+g} points',
                    'period_label': f'versus {prev.libelle}',
                    'compatible': True,
                }
    return payload


def _outstanding_amount(ctx: DashboardContext) -> dict:
    from school_admin.services.recouvrement import devise_etablissement

    if not ctx.annee_scolaire:
        return _empty(
            'outstanding_amount',
            'Reste à recouvrer',
            'FCFA',
            'Aucune année scolaire sélectionnée.',
            OUTSTANDING_DEFINITION,
        )
    qs = comptabilite_qs(ctx)
    if not qs.exists():
        return _empty(
            'outstanding_amount',
            'Reste à recouvrer',
            'FCFA',
            'Aucun dossier comptable sur le périmètre filtré.',
            OUTSTANDING_DEFINITION,
        )
    agg = _aggregate_fiches(qs)
    if agg['total_du'] <= ZERO:
        return _empty(
            'outstanding_amount',
            'Reste à recouvrer',
            'FCFA',
            'Aucune charge scolarité enregistrée pour cette session.',
            OUTSTANDING_DEFINITION,
        )
    devise = devise_etablissement(ctx.etablissement)
    reste = agg['reste']
    return {
        'id': 'outstanding_amount',
        'label': 'Reste à recouvrer',
        'value': _money(reste),
        'unit': devise,
        'empty': False,
        'definition': OUTSTANDING_DEFINITION,
        'url': _url('directeur:liste_impayes_directeur'),
        'extra': {
            'devise': devise,
            'nb_impayes': agg['nb_impayes'],
            'total_du': _money(agg['total_du']),
            'total_paye': _money(agg['total_paye']),
        },
    }


def _finance_status(ctx: DashboardContext) -> dict:
    from school_admin.model.comptabilite_eleve_model import PaiementEleve
    from school_admin.services.recouvrement import devise_etablissement

    if not ctx.annee_scolaire:
        return _empty(
            'finance_status',
            'Situation financière',
            'count',
            'Aucune année scolaire sélectionnée.',
            FINANCE_STATUS_DEFINITION,
        )
    qs = comptabilite_qs(ctx)
    if not qs.exists():
        return _empty(
            'finance_status',
            'Situation financière',
            'count',
            'Aucun dossier comptable sur le périmètre filtré.',
            FINANCE_STATUS_DEFINITION,
        )
    agg = _aggregate_fiches(qs)
    if agg['total_du'] <= ZERO:
        return _empty(
            'finance_status',
            'Situation financière',
            'count',
            'Aucune charge scolarité enregistrée pour cette session.',
            FINANCE_STATUS_DEFINITION,
        )

    labels = []
    values = []
    for key in ('a_jour', 'en_retard', 'impaye'):
        n = agg['statuts'].get(key, 0)
        if n:
            labels.append(STATUT_LABELS[key])
            values.append(n)

    eleve_ids = list(qs.values_list('eleve_id', flat=True))
    start = ctx.today - timedelta(days=29)
    daily = (
        PaiementEleve.objects.filter(
            etablissement=ctx.etablissement,
            annee_scolaire=ctx.annee_scolaire,
            eleve_id__in=eleve_ids,
            date_paiement__date__gte=start,
            date_paiement__date__lte=ctx.today,
        )
        .annotate(day=TruncDate('date_paiement'))
        .values('day')
        .annotate(total=Sum('montant'))
        .order_by('day')
    )
    pay_labels = []
    pay_values = []
    for row in daily:
        if not row['day']:
            continue
        pay_labels.append(row['day'].strftime('%d/%m'))
        pay_values.append(_money(row['total'] or ZERO))

    devise = devise_etablissement(ctx.etablissement)
    return {
        'id': 'finance_status',
        'label': 'Situation financière',
        'value': _money(agg['reste']),
        'unit': devise,
        'empty': False,
        'definition': FINANCE_STATUS_DEFINITION,
        'url': _url('directeur:liste_impayes_directeur'),
        'extra': {
            'devise': devise,
            'nb_fiches': agg['nb_fiches'],
            'nb_impayes': agg['nb_impayes'],
            'classes': agg['classes'],
            'reste': _money(agg['reste']),
            'total_paye': _money(agg['total_paye']),
            'total_du': _money(agg['total_du']),
            'recouvrement': _pct(agg['total_paye'], agg['total_du']),
        },
        'charts': {
            'statuts': {'labels': labels, 'values': values},
            'payments': {'labels': pay_labels, 'values': pay_values},
            'mode': 'payments' if pay_labels else ('statuts' if labels else None),
            'question': 'Comment évoluent les encaissements ?',
        },
    }


def register_finance_metrics() -> None:
    register_metric(
        MetricSpec(
            id='collection_rate',
            label='Taux de recouvrement',
            unit='%',
            source='ComptabiliteEleve + charges',
            period_kind='annee',
            comparison_kind='previous_year',
            permission='comptabilite_voir',
            definition=COLLECTION_DEFINITION,
            compute=_collection_rate,
        )
    )
    register_metric(
        MetricSpec(
            id='outstanding_amount',
            label='Reste à recouvrer',
            unit='money',
            source='ComptabiliteEleve agrégats',
            period_kind='annee',
            comparison_kind='none',
            permission='comptabilite_voir',
            definition=OUTSTANDING_DEFINITION,
            compute=_outstanding_amount,
        )
    )
    register_metric(
        MetricSpec(
            id='finance_status',
            label='Situation financière',
            unit='count',
            source='ComptabiliteEleve + PaiementEleve',
            period_kind='annee',
            comparison_kind='none',
            permission='comptabilite_voir',
            definition=FINANCE_STATUS_DEFINITION,
            compute=_finance_status,
        )
    )
