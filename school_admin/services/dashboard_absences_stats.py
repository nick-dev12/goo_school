"""
Statistiques absences pour l'onglet Absences du tableau de bord directeur.
Contrat métier : voir .cursor/context/feuille_route_dashboard_absences_directeur.md §2
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Optional

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.presence_model import Presence, SoumissionListePresence

MIN_CLASS_RECORDS_FOR_RANKING = 10
COUVERTURE_JOURS_OUVRES = 5
ELEVES_RISQUE_LIMIT = 10
CLASSES_SOUS_SEUIL_TAUX = 85.0


def _month_bounds(reference: date) -> tuple[date, date]:
    start = reference.replace(day=1)
    last_day = monthrange(reference.year, reference.month)[1]
    end = reference.replace(day=last_day)
    return start, end


def _previous_month(reference: date) -> date:
    first = reference.replace(day=1)
    prev_last = first - timedelta(days=1)
    return prev_last.replace(day=1)


def _empty_payload(period_label: str) -> dict[str, Any]:
    return {
        'kpis': {
            'taux_presence': 0.0,
            'taux_presence_delta_mois': None,
            'absences_nj_total': 0,
            'absences_nj_delta_mois': None,
            'absences_justifiees': 0,
            'retards': 0,
            'retards_pct': 0.0,
            'filles_nj': 0,
            'garcons_nj': 0,
            'filles_nj_pct': 0.0,
            'garcons_nj_pct': 0.0,
            'eleves_10_12': 0,
            'eleves_gt_12': 0,
            'eleves_sans_nj': 0,
            'couverture_appels_pct': 0.0,
        },
        'charts': {
            'sexe_nj': {'labels': ['Filles', 'Garçons'], 'values': [0, 0]},
            'statuts': {
                'labels': ['Présents', 'Absences NJ', 'Justifiées', 'Retards'],
                'values': [0, 0, 0, 0],
            },
            'tranches_eleves': {
                'labels': ['0', '1–3', '4–9', '10–12', '13+'],
                'values': [0, 0, 0, 0, 0],
            },
            'top_classes': {'labels': [], 'values': []},
            'bottom_classes': {'labels': [], 'values': []},
            'evolution_mensuelle': {'labels': [], 'absences_nj': [], 'absences_justifiees': []},
            'sexe_tranche_13_plus': {'labels': ['Filles', 'Garçons'], 'values': [0, 0]},
        },
        'top_classes': [],
        'bottom_classes': [],
        'classes_sous_seuil': [],
        'eleves_risque': [],
        'meta': {
            'period_label': period_label,
            'last_submission_at': None,
            'classes_sans_appel': [],
            'has_data': False,
        },
    }


def build_dashboard_absences_stats(
    etablissement,
    annee_scolaire,
    eleves_qs,
    *,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """
    Agrège KPI, graphiques et listes pour le panneau absences du dashboard directeur.
    """
    if today is None:
        today = timezone.localdate()

    period_label = annee_scolaire.libelle if annee_scolaire else 'Toutes sessions'
    eleve_ids = list(eleves_qs.values_list('id', flat=True))
    if not eleve_ids:
        return _empty_payload(period_label)

    presence_qs = Presence.objects.filter(
        etablissement=etablissement,
        eleve_id__in=eleve_ids,
    )
    if annee_scolaire:
        presence_qs = presence_qs.filter(annee_scolaire=annee_scolaire)

    agg = presence_qs.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(statut='present')),
        absents_nj=Count('id', filter=Q(statut='absent')),
        absents_j=Count('id', filter=Q(statut='absent_justifie')),
        retards=Count('id', filter=Q(statut='retard')),
    )
    total = agg['total'] or 0
    presents = agg['presents'] or 0
    absents_nj = agg['absents_nj'] or 0
    absents_j = agg['absents_j'] or 0
    retards = agg['retards'] or 0

    taux_presence = round((presents / total) * 100, 1) if total else 0.0
    retards_pct = round((retards / total) * 100, 1) if total else 0.0

    filles_nj = presence_qs.filter(statut='absent', eleve__sexe='F').count()
    garcons_nj = presence_qs.filter(statut='absent', eleve__sexe='M').count()
    nj_sexe_total = filles_nj + garcons_nj
    filles_nj_pct = round((filles_nj / nj_sexe_total) * 100, 1) if nj_sexe_total else 0.0
    garcons_nj_pct = round((garcons_nj / nj_sexe_total) * 100, 1) if nj_sexe_total else 0.0

    mois_debut, mois_fin = _month_bounds(today)
    prev_ref = _previous_month(today)
    prev_debut, prev_fin = _month_bounds(prev_ref)

    nj_mois = presence_qs.filter(statut='absent', date__gte=mois_debut, date__lte=mois_fin).count()
    nj_mois_prec = presence_qs.filter(
        statut='absent', date__gte=prev_debut, date__lte=prev_fin
    ).count()
    absences_nj_delta_mois = nj_mois - nj_mois_prec

    pres_mois = presence_qs.filter(date__gte=mois_debut, date__lte=mois_fin)
    pres_mois_agg = pres_mois.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(statut='present')),
    )
    taux_mois = (
        round((pres_mois_agg['presents'] / pres_mois_agg['total']) * 100, 1)
        if pres_mois_agg['total']
        else 0.0
    )
    pres_mois_prec = presence_qs.filter(date__gte=prev_debut, date__lte=prev_fin)
    pres_mois_prec_agg = pres_mois_prec.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(statut='present')),
    )
    taux_mois_prec = (
        round((pres_mois_prec_agg['presents'] / pres_mois_prec_agg['total']) * 100, 1)
        if pres_mois_prec_agg['total']
        else 0.0
    )
    taux_presence_delta_mois = round(taux_mois - taux_mois_prec, 1) if pres_mois_agg['total'] else None

    per_eleve_nj = (
        presence_qs.filter(statut='absent')
        .values('eleve_id')
        .annotate(nj=Count('id'))
    )
    nj_by_eleve = {row['eleve_id']: row['nj'] for row in per_eleve_nj}
    eleves_10_12 = sum(1 for n in nj_by_eleve.values() if 10 <= n <= 12)
    eleves_gt_12 = sum(1 for n in nj_by_eleve.values() if n > 12)
    eleves_sans_nj = len(eleve_ids) - len(nj_by_eleve)

    tranche_counts = [0, 0, 0, 0, 0]
    for eid in eleve_ids:
        n = nj_by_eleve.get(eid, 0)
        if n == 0:
            tranche_counts[0] += 1
        elif n <= 3:
            tranche_counts[1] += 1
        elif n <= 9:
            tranche_counts[2] += 1
        elif n <= 12:
            tranche_counts[3] += 1
        else:
            tranche_counts[4] += 1

    sexe_13_f = 0
    sexe_13_m = 0
    if nj_by_eleve:
        eleve_sexe = dict(eleves_qs.values_list('id', 'sexe'))
        for eid, n in nj_by_eleve.items():
            if n <= 12:
                continue
            sexe = eleve_sexe.get(eid)
            if sexe == 'F':
                sexe_13_f += 1
            elif sexe == 'M':
                sexe_13_m += 1

    class_rows = (
        presence_qs.values('classe_id', 'classe__nom')
        .annotate(
            total=Count('id'),
            presents=Count('id', filter=Q(statut='present')),
        )
        .filter(total__gte=MIN_CLASS_RECORDS_FOR_RANKING)
    )
    ranked = []
    for row in class_rows:
        taux = round((row['presents'] / row['total']) * 100, 1) if row['total'] else 0.0
        ranked.append(
            {
                'classe_id': row['classe_id'],
                'nom': row['classe__nom'],
                'taux_presence': taux,
                'total_enregistrements': row['total'],
                'absences_nj': presence_qs.filter(
                    classe_id=row['classe_id'], statut='absent'
                ).count(),
            }
        )
    ranked.sort(key=lambda x: x['taux_presence'], reverse=True)
    top_classes = ranked[:5]
    bottom_classes = sorted(ranked, key=lambda x: x['taux_presence'])[:5]
    classes_sous_seuil = [c for c in ranked if c['taux_presence'] < CLASSES_SOUS_SEUIL_TAUX][:8]

    monthly_nj = (
        presence_qs.filter(statut='absent')
        .annotate(m=TruncMonth('date'))
        .values('m')
        .annotate(n=Count('id'))
        .order_by('m')
    )
    monthly_j = (
        presence_qs.filter(statut='absent_justifie')
        .annotate(m=TruncMonth('date'))
        .values('m')
        .annotate(n=Count('id'))
        .order_by('m')
    )
    j_by_month = {row['m']: row['n'] for row in monthly_j if row['m']}
    ev_labels = []
    ev_nj = []
    ev_j = []
    for row in monthly_nj:
        if not row['m']:
            continue
        m = row['m']
        if hasattr(m, 'date'):
            m = m.date()
        ev_labels.append(m.strftime('%b %Y'))
        ev_nj.append(row['n'])
        ev_j.append(j_by_month.get(row['m'], 0))

    eleve_map = {
        e['id']: e
        for e in eleves_qs.values('id', 'nom', 'prenom', 'sexe', 'classe_id', 'classe__nom')
    }
    risque = []
    for eid, nj in sorted(nj_by_eleve.items(), key=lambda x: x[1], reverse=True)[:ELEVES_RISQUE_LIMIT]:
        info = eleve_map.get(eid)
        if not info:
            continue
        nj_distinct = (
            presence_qs.filter(eleve_id=eid, statut='absent')
            .values('date')
            .distinct()
            .count()
        )
        justifiees = presence_qs.filter(eleve_id=eid, statut='absent_justifie').count()
        total_eleve = presence_qs.filter(eleve_id=eid).count()
        presents_eleve = presence_qs.filter(eleve_id=eid, statut='present').count()
        taux_eleve = round((presents_eleve / total_eleve) * 100, 1) if total_eleve else 0.0
        risque.append(
            {
                'eleve_id': eid,
                'nom_complet': f"{info['nom']} {info['prenom']}".strip(),
                'classe_id': info['classe_id'],
                'classe_nom': info['classe__nom'] or '',
                'absences_nj': nj,
                'absences_justifiees': justifiees,
                'jours_absents_nj': nj_distinct,
                'taux_presence': taux_eleve,
            }
        )

    soumission_qs = SoumissionListePresence.objects.filter(etablissement=etablissement)
    if annee_scolaire:
        soumission_qs = soumission_qs.filter(annee_scolaire=annee_scolaire)
    last_sub = soumission_qs.order_by('-date_soumission').values_list('date_soumission', flat=True).first()

    classes_actives = Classe.objects.filter(etablissement=etablissement, actif=True)
    total_classes = classes_actives.count()
    couverture_pct = 0.0
    classes_sans_appel = []
    if total_classes:
        seuil_date = today
        jours_comptes = 0
        dates_ouvres = []
        while jours_comptes < COUVERTURE_JOURS_OUVRES and seuil_date.year > today.year - 2:
            if seuil_date.weekday() < 5:
                dates_ouvres.append(seuil_date)
                jours_comptes += 1
            seuil_date -= timedelta(days=1)
        if dates_ouvres:
            min_d = min(dates_ouvres)
            classes_avec = set(
                soumission_qs.filter(date__gte=min_d, date__lte=today).values_list(
                    'classe_id', flat=True
                )
            )
            couverture_pct = round((len(classes_avec) / total_classes) * 100, 1)
            sans = classes_actives.exclude(id__in=classes_avec).values_list('nom', flat=True)[:5]
            classes_sans_appel = list(sans)

    return {
        'kpis': {
            'taux_presence': taux_presence,
            'taux_presence_delta_mois': taux_presence_delta_mois,
            'absences_nj_total': absents_nj,
            'absences_nj_delta_mois': absences_nj_delta_mois,
            'absences_justifiees': absents_j,
            'retards': retards,
            'retards_pct': retards_pct,
            'filles_nj': filles_nj,
            'garcons_nj': garcons_nj,
            'filles_nj_pct': filles_nj_pct,
            'garcons_nj_pct': garcons_nj_pct,
            'eleves_10_12': eleves_10_12,
            'eleves_gt_12': eleves_gt_12,
            'eleves_sans_nj': eleves_sans_nj,
            'couverture_appels_pct': couverture_pct,
        },
        'charts': {
            'sexe_nj': {'labels': ['Filles', 'Garçons'], 'values': [filles_nj, garcons_nj]},
            'statuts': {
                'labels': ['Présents', 'Absences NJ', 'Justifiées', 'Retards'],
                'values': [presents, absents_nj, absents_j, retards],
            },
            'tranches_eleves': {
                'labels': ['0', '1–3', '4–9', '10–12', '13+'],
                'values': tranche_counts,
            },
            'top_classes': {
                'labels': [c['nom'] for c in top_classes],
                'values': [c['taux_presence'] for c in top_classes],
            },
            'bottom_classes': {
                'labels': [c['nom'] for c in bottom_classes],
                'values': [c['taux_presence'] for c in bottom_classes],
            },
            'evolution_mensuelle': {
                'labels': ev_labels,
                'absences_nj': ev_nj,
                'absences_justifiees': ev_j,
            },
            'sexe_tranche_13_plus': {
                'labels': ['Filles', 'Garçons'],
                'values': [sexe_13_f, sexe_13_m],
            },
        },
        'top_classes': top_classes,
        'bottom_classes': bottom_classes,
        'classes_sous_seuil': classes_sous_seuil,
        'eleves_risque': risque,
        'meta': {
            'period_label': period_label,
            'last_submission_at': last_sub,
            'classes_sans_appel': classes_sans_appel,
            'has_data': total > 0,
        },
    }
