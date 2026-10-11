"""Métriques effectifs et capacité (D0/D1)."""
from __future__ import annotations

from django.db.models import Count, Q

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.metrics.registry import MetricSpec, register_metric
from school_admin.services.dashboard.querysets import classes_qs, eleves_qs, inscription_qs


def _student_count(ctx: DashboardContext) -> dict:
    if not ctx.annee_scolaire:
        return {
            'id': 'student_count',
            'label': 'Élèves inscrits',
            'value': None,
            'unit': 'count',
            'empty': True,
            'empty_reason': 'Aucune année scolaire sélectionnée.',
            'definition': 'Élèves actifs inscrits sur l’année consultée.',
        }
    count = eleves_qs(ctx).count()
    payload = {
        'id': 'student_count',
        'label': 'Élèves inscrits',
        'value': count,
        'unit': 'count',
        'empty': False,
        'definition': 'Élèves actifs inscrits sur l’année scolaire consultée, après filtres.',
    }
    prev_annee = (
        AnneeScolaire.objects.filter(
            etablissement=ctx.etablissement,
            date_fin__lt=ctx.annee_scolaire.date_debut,
        )
        .order_by('-date_fin')
        .first()
    )
    if prev_annee:
        prev_count = InscriptionEleve.objects.filter(
            etablissement=ctx.etablissement,
            annee_scolaire=prev_annee,
            eleve__actif=True,
        ).exclude(eleve_id__isnull=True).count()
        if prev_count:
            delta = count - prev_count
            payload['comparison'] = {
                'reference_value': prev_count,
                'delta': delta,
                'delta_label': f'{delta:+d} élèves',
                'period_label': f'versus {prev_annee.libelle}',
                'compatible': True,
            }
    return payload


def _class_capacity(ctx: DashboardContext) -> dict:
    qs = classes_qs(ctx)
    if not qs.exists():
        return {
            'id': 'class_capacity',
            'label': 'Occupation des classes',
            'value': None,
            'unit': '%',
            'empty': True,
            'empty_reason': 'Aucune classe active dans le périmètre filtré.',
            'definition': 'Effectif inscrit / capacité configurée (capacite_max).',
        }
    if ctx.annee_scolaire:
        qs = qs.annotate(
            effectif=Count(
                'inscriptions_eleves',
                filter=Q(
                    inscriptions_eleves__annee_scolaire=ctx.annee_scolaire,
                    inscriptions_eleves__eleve__actif=True,
                ),
            )
        )
    else:
        qs = qs.annotate(effectif=Count('eleves', filter=Q(eleves__actif=True)))

    rows = list(qs.values('id', 'nom', 'capacite_max', 'effectif'))
    total_cap = sum(r['capacite_max'] or 0 for r in rows)
    total_eff = sum(r['effectif'] or 0 for r in rows)
    if not total_cap:
        return {
            'id': 'class_capacity',
            'label': 'Occupation des classes',
            'value': None,
            'unit': '%',
            'empty': True,
            'empty_reason': 'Capacité maximale non configurée.',
            'definition': 'Effectif inscrit / capacité configurée (capacite_max).',
        }
    taux = round((total_eff / total_cap) * 100, 1)
    over = [r for r in rows if r['effectif'] > r['capacite_max']]
    full = [r for r in rows if r['effectif'] == r['capacite_max'] and r['capacite_max'] > 0]
    return {
        'id': 'class_capacity',
        'label': 'Occupation des classes',
        'value': taux,
        'unit': '%',
        'empty': False,
        'definition': 'Somme des inscrits / somme des capacités configurées.',
        'extra': {
            'effectif': total_eff,
            'capacite': total_cap,
            'classes_pleines': len(full),
            'classes_depassement': len(over),
        },
    }


def _cycle_distribution(ctx: DashboardContext) -> dict:
    if not ctx.annee_scolaire:
        return {
            'id': 'cycle_distribution',
            'label': 'Répartition par cycle',
            'value': None,
            'unit': 'count',
            'empty': True,
            'empty_reason': 'Aucune année scolaire sélectionnée.',
            'charts': {
                'labels': [],
                'values': [],
                'gender': {'female': 0, 'male': 0, 'unknown': 0},
            },
        }
    rows = (
        inscription_qs(ctx)
        .exclude(eleve_id__isnull=True)
        .filter(eleve__actif=True)
        .values('classe__niveau')
        .annotate(n=Count('id'))
        .order_by('classe__niveau')
    )
    labels = {
        'maternelle': 'Maternelle',
        'primaire': 'Primaire',
        'college': 'Collège',
        'lycee': 'Lycée',
        'superieur': 'Supérieur',
    }
    chart_labels = []
    chart_values = []
    for row in rows:
        key = row['classe__niveau']
        if not key:
            continue
        chart_labels.append(labels.get(key, key))
        chart_values.append(row['n'])
    empty = not chart_values
    total = sum(chart_values) if chart_values else 0
    cycle_colors = {
        'Maternelle': '#8b5cf6',
        'Primaire': '#3b82f6',
        'Collège': '#10b981',
        'Lycée': '#f59e0b',
        'Supérieur': '#ef4444',
    }
    rows_ui = []
    chart_colors = []
    for label, value in zip(chart_labels, chart_values):
        pct = round(value / total * 100, 1) if total else None
        rows_ui.append({'label': label, 'value': value, 'pct': pct})
        chart_colors.append(cycle_colors.get(label, '#3b82f6'))
    gender = {'female': 0, 'male': 0, 'unknown': 0}
    for row in eleves_qs(ctx).values('sexe').annotate(n=Count('id')):
        sexe = row['sexe']
        n = row['n']
        if sexe == 'F':
            gender['female'] = n
        elif sexe == 'M':
            gender['male'] = n
        else:
            gender['unknown'] += n
    return {
        'id': 'cycle_distribution',
        'label': 'Répartition par cycle',
        'value': total if total else None,
        'unit': 'count',
        'empty': empty,
        'empty_reason': 'Aucune inscription dans le périmètre.' if empty else '',
        'charts': {
            'labels': chart_labels,
            'values': chart_values,
            'colors': chart_colors,
            'rows': rows_ui,
            'total': total,
            'gender': gender,
        },
        'definition': 'Inscriptions actives groupées par cycle (niveau de classe).',
    }


def register_effectifs_metrics() -> None:
    register_metric(
        MetricSpec(
            id='student_count',
            label='Élèves inscrits',
            unit='count',
            source='InscriptionEleve + Eleve.actif',
            period_kind='annee',
            comparison_kind='previous_year',
            permission='eleves_liste',
            definition='Nombre d’élèves actifs inscrits pour l’année scolaire consultée.',
            compute=_student_count,
        )
    )
    register_metric(
        MetricSpec(
            id='class_capacity',
            label='Occupation des classes',
            unit='%',
            source='Classe.capacite_max + InscriptionEleve',
            period_kind='annee',
            comparison_kind='none',
            permission='eleves_liste',
            definition='Effectif inscrit / capacité configurée.',
            compute=_class_capacity,
        )
    )
    register_metric(
        MetricSpec(
            id='cycle_distribution',
            label='Répartition par cycle',
            unit='count',
            source='InscriptionEleve.classe.niveau',
            period_kind='annee',
            comparison_kind='none',
            permission='eleves_liste',
            definition='Répartition des inscrits par cycle.',
            compute=_cycle_distribution,
        )
    )
