"""Compléments du tableau de bord (V3) : droits d'affichage, occupation des classes,
absentéisme par jour de semaine, équipe et données de graphiques prêtes à tracer.

Toutes les séries respectent les autorisations du personnel connecté (user_may) :
un bloc non autorisé n'est ni calculé ni affiché.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import ExtractIsoWeekDay

from school_admin.services.dashboard.context import DashboardContext
from school_admin.services.dashboard.permissions import user_may
from school_admin.services.dashboard.querysets import classes_qs

WEEKDAYS = ('Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi')
WEEKDAY_WINDOW_DAYS = 56
PRESENCE_THRESHOLD = 85.0


def dashboard_permissions(ctx: DashboardContext) -> dict:
    return {
        'eleves': user_may(ctx, 'eleves_liste'),
        'presences': user_may(ctx, 'presences_liste'),
        'notes': user_may(ctx, 'notes_liste'),
        'finance': user_may(ctx, 'comptabilite_voir'),
        'equipe': user_may(ctx, 'professeurs_liste') or user_may(ctx, 'personnel_liste'),
        'classes': user_may(ctx, 'classes_liste') or user_may(ctx, 'eleves_liste'),
    }


_CYCLE_ORDER = {'maternelle': 0, 'primaire': 1, 'college': 2, 'lycee': 3, 'superieur': 4}
# Ordre scolaire des niveaux (début du nom de classe), du plus petit au plus grand.
_LEVEL_ORDER = (
    'ps', 'ms', 'gs', 'ci', 'cp', 'ce1', 'ce2', 'cm1', 'cm2',
    '6', '5', '4', '3', '2', '1', 't', 'l1', 'l2', 'l3', 'm1', 'm2',
)


def _classe_sort_key(row):
    """Trie « CI A, CP A, CE1 A… » ou « 6e A, 5e A… Tle S1 » plutôt qu'alphabétiquement."""
    nom = (row.get('nom') or '').strip().lower()
    filiere, niveau_txt = '', nom
    for token in (nom.split() if row.get('niveau') == 'superieur' else ()):
        if token[:2] in ('l1', 'l2', 'l3', 'm1', 'm2'):
            niveau_txt = token
            filiere = nom.split()[0] if nom.split()[0] != token else ''
            break
    rank = len(_LEVEL_ORDER)
    for i, prefix in sorted(enumerate(_LEVEL_ORDER), key=lambda p: -len(p[1])):
        if niveau_txt.startswith(prefix):
            rank = i
            break
    return (_CYCLE_ORDER.get(row.get('niveau'), 9), rank, filiere, nom)


def class_occupation(ctx: DashboardContext) -> dict:
    """Effectif inscrit et capacité de chaque classe du périmètre."""
    qs = classes_qs(ctx)
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
    rows = []
    values = qs.values('id', 'nom', 'niveau', 'capacite_max', 'effectif')
    for row in sorted(values, key=_classe_sort_key):
        capacite = row['capacite_max'] or 0
        effectif = row['effectif'] or 0
        rows.append({
            'id': row['id'],
            'classe': row['nom'],
            'effectif': effectif,
            'capacite': capacite,
            'taux': round(effectif / capacite * 100, 1) if capacite else None,
            'depassement': bool(capacite) and effectif > capacite,
        })
    total_eff = sum(r['effectif'] for r in rows)
    total_cap = sum(r['capacite'] for r in rows)
    return {
        'empty': not rows or not total_eff,
        'empty_reason': 'Aucune classe ou aucun inscrit sur l’année consultée.',
        'rows': rows,
        'total_effectif': total_eff,
        'total_capacite': total_cap,
        'taux': round(total_eff / total_cap * 100, 1) if total_cap else None,
        'places_libres': max(total_cap - total_eff, 0),
        'pleines': sum(1 for r in rows if r['capacite'] and r['effectif'] >= r['capacite']),
        'charts': {
            'labels': [r['classe'] for r in rows],
            'effectif': [r['effectif'] for r in rows],
            'libres': [max(r['capacite'] - r['effectif'], 0) for r in rows],
            'depassement': [max(r['effectif'] - r['capacite'], 0) if r['capacite'] else 0 for r in rows],
        },
    }


def weekday_absences(ctx: DashboardContext) -> dict:
    """Taux d'absence (absences non justifiées + justifiées) par jour de semaine, 8 dernières semaines."""
    from school_admin.services.dashboard.metrics.presence import _presence_base_qs

    start = ctx.today - timedelta(days=WEEKDAY_WINDOW_DAYS - 1)
    rows = (
        _presence_base_qs(ctx)
        .filter(date__gte=start, date__lte=ctx.today)
        .annotate(jour=ExtractIsoWeekDay('date'))
        .values('jour')
        .annotate(
            total=Count('id'),
            absents=Count('id', filter=Q(statut__in=('absent', 'absent_justifie'))),
            retards=Count('id', filter=Q(statut='retard')),
        )
        .order_by('jour')
    )
    by_day = {r['jour']: r for r in rows if r['total']}
    labels, absences, retards = [], [], []
    for iso in range(1, 7):
        row = by_day.get(iso)
        if not row:
            continue
        labels.append(WEEKDAYS[iso - 1])
        absences.append(round(row['absents'] / row['total'] * 100, 1))
        retards.append(round(row['retards'] / row['total'] * 100, 1))
    empty = not labels
    pic = None
    if not empty:
        idx = max(range(len(absences)), key=lambda i: absences[i])
        pic = {'jour': labels[idx], 'taux': absences[idx]}
    return {
        'empty': empty,
        'empty_reason': 'Pas encore d’appels sur les 8 dernières semaines.',
        'pic': pic,
        'charts': {'labels': labels, 'absences': absences, 'retards': retards},
    }


def team_counts(ctx: DashboardContext) -> dict:
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur

    return {
        'enseignants': Professeur.objects.filter(etablissement=ctx.etablissement, actif=True).count(),
        'personnel': PersonnelAdministratif.objects.filter(etablissement=ctx.etablissement, actif=True).count(),
        'classes': classes_qs(ctx).count(),
    }


DISTINCTION_SEUIL = 16


def mini_indicators(ctx: DashboardContext, executive: dict, can: dict, gender: dict) -> list[dict]:
    """
    Cartes indicatives « vue d'ensemble » (élèves, équipe, classes, évaluations,
    bulletins, réussite, distinctions). Chaque carte n'apparaît que si l'utilisateur
    a le droit de voir la donnée ; les légendes reposent sur des chiffres réels.
    """
    from django.db.models import Q as _Q

    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    from school_admin.services.dashboard.metrics.pedagogie import _moyennes_qs

    kpis = {k['id']: k for k in executive.get('kpis') or [] if k.get('id')}
    libelle = 'Étudiants' if getattr(ctx.etablissement, 'type_etablissement', '') == 'superieur' else 'Élèves'
    cards = []
    nb_eleves = None

    if can['eleves']:
        m = kpis.get('student_count') or {}
        nb_eleves = None if m.get('empty') else m.get('value')
        comp = m.get('comparison') or {}
        caption = (
            f"{comp.get('delta_label')} {comp.get('period_label', '')}".strip()
            if comp else 'Inscrits sur l’année consultée'
        )
        cards.append({
            'id': 'eleves', 'label': f'{libelle} inscrits', 'icon': 'fa-user-graduate', 'tone': 'blue',
            'value': nb_eleves if nb_eleves is not None else 0,
            'caption': caption if nb_eleves is not None else (m.get('empty_reason') or ''),
            'trend': ('up' if comp.get('delta', 0) > 0 else 'down' if comp.get('delta', 0) < 0 else '') if comp else '',
            'gender': gender if gender.get('female_pct') is not None else None,
        })

    if user_may(ctx, 'professeurs_liste'):
        nb_profs = Professeur.objects.filter(etablissement=ctx.etablissement, actif=True).count()
        ratio = round(nb_eleves / nb_profs) if nb_profs and nb_eleves else None
        cards.append({
            'id': 'enseignants', 'label': 'Enseignants', 'icon': 'fa-chalkboard-user', 'tone': 'violet',
            'value': nb_profs,
            'caption': f'1 enseignant pour {ratio} {libelle.lower()}' if ratio else 'Enseignants actifs',
        })

    if user_may(ctx, 'personnel_liste'):
        personnel = PersonnelAdministratif.objects.filter(etablissement=ctx.etablissement, actif=True)
        nouveaux = (
            personnel.filter(date_creation__date__gte=ctx.annee_scolaire.date_debut).count()
            if ctx.annee_scolaire else 0
        )
        cards.append({
            'id': 'personnel', 'label': 'Personnel administratif', 'icon': 'fa-user-tie', 'tone': 'green',
            'value': personnel.count(),
            'caption': f'+{nouveaux} cette année' if nouveaux else 'Aucune arrivée cette année',
            'trend': 'up' if nouveaux else '',
        })

    if can['classes']:
        classes = classes_qs(ctx)
        nb_classes = classes.count()
        moyenne = round(nb_eleves / nb_classes) if nb_classes and nb_eleves else None
        cards.append({
            'id': 'classes', 'label': 'Classes actives', 'icon': 'fa-school', 'tone': 'indigo',
            'value': nb_classes,
            'caption': f'{moyenne} {libelle.lower()} en moyenne par classe' if moyenne else 'Classes ouvertes',
        })

    if can['notes']:
        classe_ids = list(classes_qs(ctx).values_list('id', flat=True))
        debut = ctx.today - timedelta(days=ctx.today.weekday())
        fin = debut + timedelta(days=6)
        semaine = _Q(date_evaluation__gte=debut, date_evaluation__lte=fin, classe_id__in=classe_ids)
        evals = Evaluation.objects.filter(semaine, actif=True)
        evals_prim = EvaluationPrimaire.objects.filter(semaine, actif=True)
        if ctx.annee_scolaire:
            evals = evals.filter(annee_scolaire=ctx.annee_scolaire)
            evals_prim = evals_prim.filter(annee_scolaire=ctx.annee_scolaire)
        nb_evals = evals.count() + evals_prim.count()
        a_venir = (
            evals.filter(date_evaluation__gt=ctx.today).count()
            + evals_prim.filter(date_evaluation__gt=ctx.today).count()
        )
        cards.append({
            'id': 'evaluations', 'label': 'Évaluations en cours', 'icon': 'fa-list-check', 'tone': 'blue',
            'value': nb_evals,
            'caption': f'Cette semaine · {a_venir} à venir' if a_venir else 'Prévues cette semaine',
        })

        moyennes = _moyennes_qs(ctx)
        periode_nom = ctx.periode_scolaire.nom_periode if ctx.periode_scolaire else ''
        nb_moyennes = moyennes.count() if moyennes is not None else 0
        publies = moyennes.filter(est_publie=True).count() if moyennes is not None else 0
        cards.append({
            'id': 'bulletins', 'label': 'Bulletins publiés', 'icon': 'fa-file-lines', 'tone': 'sky',
            'value': publies,
            'caption': (
                f'sur {nb_moyennes} · {periode_nom}' if nb_moyennes
                else (f'{periode_nom} · aucune moyenne calculée' if periode_nom else 'Aucune période active')
            ),
        })

        reussite = kpis.get('success_rate') or {}
        moyenne_g = kpis.get('average_grade') or {}
        cards.append({
            'id': 'reussite', 'label': 'Taux de réussite', 'icon': 'fa-chart-line', 'tone': 'green',
            'value': reussite.get('value') if not reussite.get('empty') else None,
            'unit': '%',
            'caption': (
                f"Moyenne générale {moyenne_g.get('value'):.2f}/20".replace('.', ',')
                if not moyenne_g.get('empty') and moyenne_g.get('value') is not None
                else (reussite.get('empty_reason') or 'Basé sur les moyennes générales')
            ),
        })

        distinctions = (
            moyennes.filter(moyenne_generale__gte=DISTINCTION_SEUIL).count() if moyennes is not None else 0
        )
        cards.append({
            'id': 'distinctions', 'label': 'Distinctions', 'icon': 'fa-medal', 'tone': 'amber',
            'value': distinctions,
            'caption': f'Moyenne ≥ {DISTINCTION_SEUIL}/20 · tableau d’honneur',
        })
    return cards


def build_overview(ctx: DashboardContext, executive: dict) -> dict:
    can = dashboard_permissions(ctx)
    trend = executive.get('attendance_trend') or {}
    cycles = (executive.get('cycle_distribution') or {}).get('charts') or {}
    gender = cycles.get('gender') or {}
    known = (gender.get('female') or 0) + (gender.get('male') or 0)
    overview = {
        'can': can,
        'presence_threshold': PRESENCE_THRESHOLD,
        'multi_cycle': len(cycles.get('labels') or []) > 1,
        'gender': {
            'female': gender.get('female') or 0,
            'male': gender.get('male') or 0,
            'female_pct': round((gender.get('female') or 0) / known * 100) if known else None,
            'male_pct': round((gender.get('male') or 0) / known * 100) if known else None,
        },
        'sparkline': (trend.get('charts') or {}).get('values') or [],
        # Accès direct aux indicateurs depuis le gabarit : overview.kpi.student_count…
        'kpi': {k['id']: k for k in executive.get('kpis') or [] if k.get('id')},
        'today': [
            item for item in (executive.get('today') or {}).get('items') or []
            if item.get('id') not in ('date', 'alerts_today')
            and not item.get('empty')
            and item.get('value') not in (None, '', 0)
        ],
    }
    overview['mini'] = mini_indicators(ctx, executive, can, overview['gender'])
    # Profil « finances » (caissier, comptable…) : indicateurs financiers détaillés.
    overview['finance_focus'] = can['finance'] and not (can['eleves'] or can['notes'] or can['presences'])
    payments = ((executive.get('finance') or {}).get('charts') or {}).get('payments') or {}
    overview['encaisse_30j'] = sum(payments.get('values') or [])
    presence_rows = ((executive.get('presence_by_class') or {}).get('extra') or {}).get('rows') or []
    overview['classes_sous_seuil'] = [r for r in presence_rows if r.get('watch')][:6]
    if can['classes']:
        overview['occupation'] = class_occupation(ctx)
    if can['presences']:
        overview['weekdays'] = weekday_absences(ctx)
    if can['equipe']:
        overview['team'] = team_counts(ctx)
    return overview
