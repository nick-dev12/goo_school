"""
Tableau de bord enseignant (V3) — primaire, secondaire et supérieur.

Toutes les données sont limitées au périmètre de l'enseignant connecté : ses classes
(affectations de l'année consultée), ses évaluations, ses notes et ses appels.
Les notes sont ramenées sur 20 (note / barème × 20) pour être comparables.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.urls import NoReverseMatch, reverse

SEUIL = 10.0
PRESENCE_SEUIL = 85.0
GRADE_BUCKETS = (('< 8', 0, 8), ('8 – 10', 8, 10), ('10 – 12', 10, 12), ('12 – 14', 12, 14),
                 ('14 – 16', 14, 16), ('≥ 16', 16, 20.01))


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ''


def _fr(value):
    """69.1 → « 69,1 » (virgule décimale française)."""
    return f'{value:g}'.replace('.', ',') if isinstance(value, (int, float)) else str(value)


def _pct(part, total):
    return round(part / total * 100, 1) if total else None


def _sur20(note, bareme):
    try:
        note = float(note)
        bareme = float(bareme or 20) or 20.0
    except (TypeError, ValueError):
        return None
    return round(note / bareme * 20, 2)


def _affectations(professeur, annee, is_primaire):
    if is_primaire:
        from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire

        qs = AffectationProfesseurPrimaire.objects.filter(professeur=professeur, actif=True)
        if annee:
            qs = qs.filter(annee_scolaire=annee)
        return qs.select_related('classe').prefetch_related('matieres')
    from school_admin.model.affectation_model import AffectationProfesseur

    qs = AffectationProfesseur.objects.filter(professeur=professeur, actif=True)
    if annee:
        qs = qs.filter(annee_scolaire=annee)
    return qs.select_related('classe', 'matiere')


def _effectifs(classes, etablissement, annee):
    """{classe_id: [eleve_id…]} pour l'année consultée."""
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    out = defaultdict(list)
    ids = [c.id for c in classes]
    if annee:
        rows = InscriptionEleve.objects.filter(
            annee_scolaire=annee, etablissement=etablissement, classe_id__in=ids, eleve__actif=True,
        ).exclude(eleve_id__isnull=True).values_list('classe_id', 'eleve_id')
    else:
        rows = Eleve.objects.filter(classe_id__in=ids, actif=True).values_list('classe_id', 'id')
    for classe_id, eleve_id in rows:
        out[classe_id].append(eleve_id)
    return out


def build_teacher_dashboard(professeur, annee, today, is_primaire, periode=None):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
    from school_admin.model.presence_model import Presence

    ns = 'enseignant_primaire' if is_primaire else 'enseignant'
    etablissement = getattr(professeur, 'etablissement', None)
    est_superieur = getattr(etablissement, 'type_etablissement', '') == 'superieur'
    libelle = 'étudiants' if est_superieur else 'élèves'

    # ---------- Classes et matières ----------
    affectations = list(_affectations(professeur, annee, is_primaire))
    classes_by_id = {}
    matieres_by_classe = defaultdict(set)
    principal_ids = set()
    for aff in affectations:
        classes_by_id[aff.classe_id] = aff.classe
        if is_primaire:
            for m in aff.matieres.all():
                matieres_by_classe[aff.classe_id].add(m.nom)
        elif aff.matiere_id:
            matieres_by_classe[aff.classe_id].add(aff.matiere.nom)
        if aff.is_principal:
            principal_ids.add(aff.classe_id)
    classes = sorted(classes_by_id.values(), key=lambda c: c.nom)
    classe_ids = [c.id for c in classes]
    effectifs = _effectifs(classes, etablissement, annee)
    eleve_ids = {e for ids in effectifs.values() for e in ids}

    gender = {'F': 0, 'M': 0}
    for sexe, n in Eleve.objects.filter(id__in=eleve_ids).values_list('sexe').annotate(n=Count('id')):
        if sexe in gender:
            gender[sexe] = n
    known = gender['F'] + gender['M']

    # ---------- Emploi du temps ----------
    creneaux = CreneauEmploiDuTemps.objects.filter(
        professeur=professeur,
        emploi_du_temps__est_actif=True,
        emploi_du_temps__statut_publication='publie',
    ).select_related('periode_etablissement', 'emploi_du_temps')
    if annee:
        creneaux = creneaux.filter(emploi_du_temps__annee_scolaire_fk=annee)
    minutes_semaine = 0
    minutes_par_classe = defaultdict(int)
    for c in creneaux:
        try:
            duree = c.duree_minutes
        except Exception:
            duree = 0
        minutes_semaine += duree
        minutes_par_classe[c.emploi_du_temps.classe_id] += duree

    # ---------- Évaluations et notes ----------
    if is_primaire:
        from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
        from school_admin.model.note_primaire_model import NotePrimaire

        evals = EvaluationPrimaire.objects.filter(professeur=professeur, actif=True)
        note_fk = 'evaluation_primaire'
        NoteModel = NotePrimaire
    else:
        from school_admin.model.evaluation_model import Evaluation, Note

        evals = Evaluation.objects.filter(professeur=professeur, actif=True)
        note_fk = 'evaluation'
        NoteModel = Note
    if annee:
        evals = evals.filter(annee_scolaire=annee)
    evals = evals.filter(classe_id__in=classe_ids).select_related('classe', 'matiere')

    evals_list = list(evals.order_by('date_evaluation'))
    bareme = {e.id: e.bareme for e in evals_list}
    notes = list(
        NoteModel.objects.filter(**{f'{note_fk}_id__in': list(bareme)}, absent=False, note__isnull=False)
        .values_list(f'{note_fk}_id', 'eleve_id', 'note')
    )
    matiere_of_eval = {e.id: getattr(e.matiere, 'nom', '') or 'Autre' for e in evals_list}
    notes_par_matiere = defaultdict(list)
    notes_par_eval = defaultdict(list)
    notes_par_eleve = defaultdict(list)
    notes_par_classe = defaultdict(list)
    classe_of_eval = {e.id: e.classe_id for e in evals_list}
    toutes = []
    for eval_id, eleve_id, valeur in notes:
        v = _sur20(valeur, bareme.get(eval_id))
        if v is None:
            continue
        notes_par_eval[eval_id].append(v)
        notes_par_eleve[eleve_id].append(v)
        notes_par_classe[classe_of_eval[eval_id]].append(v)
        notes_par_matiere[matiere_of_eval[eval_id]].append(v)
        toutes.append(v)

    saisies = dict(
        NoteModel.objects.filter(**{f'{note_fk}_id__in': list(bareme)})
        .values(f'{note_fk}_id').annotate(n=Count('id')).values_list(f'{note_fk}_id', 'n')
    )

    moyenne_globale = round(sum(toutes) / len(toutes), 2) if toutes else None
    reussite = _pct(sum(1 for v in toutes if v >= SEUIL), len(toutes))

    # Évaluations passées dont la saisie n'est pas complète (« à corriger »).
    a_corriger = []
    for e in evals_list:
        if e.date_evaluation > today:
            continue
        attendus = len(effectifs.get(e.classe_id, []))
        faits = saisies.get(e.id, 0)
        if attendus and faits < attendus:
            a_corriger.append({
                'titre': e.titre, 'classe': e.classe.nom, 'date': e.date_evaluation,
                'faits': faits, 'attendus': attendus, 'pct': int(faits / attendus * 100),
                'url': _url(f'{ns}:noter_eleves', e.classe_id),
            })
    a_corriger.sort(key=lambda r: r['date'], reverse=True)
    notes_manquantes = sum(r['attendus'] - r['faits'] for r in a_corriger)

    a_venir = [e for e in evals_list if today <= e.date_evaluation <= today + timedelta(days=13)]
    prochaines = [{
        'titre': e.titre, 'classe': e.classe.nom, 'matiere': getattr(e.matiere, 'nom', ''),
        'date': e.date_evaluation, 'jours': (e.date_evaluation - today).days,
    } for e in a_venir[:5]]

    # Résultats au fil des évaluations (10 dernières notées).
    notees = [e for e in evals_list if notes_par_eval.get(e.id)][-10:]
    evolution = {
        'labels': [f"{e.date_evaluation:%d/%m} · {e.classe.nom}" for e in notees],
        'values': [round(sum(notes_par_eval[e.id]) / len(notes_par_eval[e.id]), 2) for e in notees],
        'titles': [e.titre for e in notees],
    }

    histogram = {
        'labels': [b[0] for b in GRADE_BUCKETS],
        'values': [sum(1 for v in toutes if lo <= v < hi) for _l, lo, hi in GRADE_BUCKETS],
    }

    # ---------- Présence (appels de l'enseignant) ----------
    presence = Presence.objects.filter(professeur=professeur, classe_id__in=classe_ids)
    if annee:
        presence = presence.filter(annee_scolaire=annee)
    start = today - timedelta(days=29)
    daily = (
        presence.filter(date__gte=start, date__lte=today).values('date')
        .annotate(total=Count('id'), presents=Count('id', filter=Q(statut='present'))).order_by('date')
    )
    trend = {'labels': [], 'values': []}
    tot30 = pres30 = 0
    for row in daily:
        if row['total']:
            trend['labels'].append(row['date'].strftime('%d/%m'))
            trend['values'].append(round(row['presents'] / row['total'] * 100, 1))
            tot30 += row['total']
            pres30 += row['presents']
    taux_presence = _pct(pres30, tot30)
    appels = presence.filter(date__gte=start).values('date', 'classe_id').distinct().count()
    par_classe_presence = {
        r['classe_id']: _pct(r['presents'], r['total'])
        for r in presence.values('classe_id').annotate(
            total=Count('id'), presents=Count('id', filter=Q(statut='present'))
        )
    }

    from django.db.models.functions import ExtractIsoWeekDay

    jours = ('Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi')
    weekdays = {'labels': [], 'values': []}
    for row in (
        presence.filter(date__gte=today - timedelta(days=55), date__lte=today)
        .annotate(jour=ExtractIsoWeekDay('date')).values('jour')
        .annotate(total=Count('id'), absents=Count('id', filter=Q(statut__in=('absent', 'absent_justifie'))))
        .order_by('jour')
    ):
        if row['total'] and 1 <= row['jour'] <= 6:
            weekdays['labels'].append(jours[row['jour'] - 1])
            weekdays['values'].append(round(row['absents'] / row['total'] * 100, 1))

    # ---------- Élèves à suivre ----------
    noms = {e.id: e for e in Eleve.objects.filter(id__in=list(notes_par_eleve)).select_related('classe')}
    a_suivre = []
    for eleve_id, valeurs in notes_par_eleve.items():
        moy = sum(valeurs) / len(valeurs)
        if moy < SEUIL and eleve_id in noms:
            e = noms[eleve_id]
            a_suivre.append({
                'nom': e.nom_complet, 'classe': e.classe.nom if e.classe_id else '—',
                'moyenne': round(moy, 2), 'nb': len(valeurs),
            })
    a_suivre.sort(key=lambda r: r['moyenne'])

    # ---------- Mes classes ----------
    classes_rows = []
    for c in classes:
        vals = notes_par_classe.get(c.id, [])
        classes_rows.append({
            'id': c.id,
            'nom': c.nom,
            'effectif': len(effectifs.get(c.id, [])),
            'matieres': sorted(matieres_by_classe.get(c.id, [])),
            'heures': round(minutes_par_classe.get(c.id, 0) / 60, 1),
            'principal': c.id in principal_ids,
            'moyenne': round(sum(vals) / len(vals), 2) if vals else None,
            'reussite': _pct(sum(1 for v in vals if v >= SEUIL), len(vals)),
            'presence': par_classe_presence.get(c.id),
            'urls': {
                'detail': _url(f'{ns}:detail_classe', c.id),
                'noter': _url(f'{ns}:noter_eleves', c.id),
                'appel': _url(f'{ns}:liste_presence', c.id),
            },
        })

    classes_notees = [r for r in classes_rows if r['moyenne'] is not None]
    classes_presence = sorted(
        [r for r in classes_rows if r['presence'] is not None], key=lambda r: r['presence']
    )

    nb_eleves = len(eleve_ids)
    mini = [
        {'id': 'classes', 'label': 'Mes classes', 'icon': 'fa-chalkboard', 'tone': 'sky',
         'value': len(classes),
         'caption': (f'dont {len(principal_ids)} comme professeur principal' if principal_ids
                     else 'Classes affectées cette année'),
         'url': _url(f'{ns}:gestion_classes')},
        {'id': 'eleves', 'label': f'{libelle.capitalize()} encadrés', 'icon': 'fa-user-graduate', 'tone': 'violet',
         'value': nb_eleves, 'caption': 'Dans toutes mes classes',
         'gender': ({'female_pct': round(gender['F'] / known * 100), 'male_pct': round(gender['M'] / known * 100)}
                    if known else None),
         'url': _url(f'{ns}:gestion_eleves')},
        {'id': 'heures', 'label': 'Heures par semaine', 'icon': 'fa-clock', 'tone': 'indigo',
         'value': round(minutes_semaine / 60, 1) if minutes_semaine else 0, 'unit': 'h',
         'caption': 'Selon l’emploi du temps publié' if minutes_semaine else 'Emploi du temps non publié',
         'url': _url(f'{ns}:emploi_du_temps')},
        {'id': 'evaluations', 'label': 'Évaluations à venir', 'icon': 'fa-calendar-check', 'tone': 'blue',
         'value': len(a_venir),
         'caption': (f"Prochaine : {a_venir[0].date_evaluation:%d/%m} · {a_venir[0].classe.nom}" if a_venir
                     else 'Rien de prévu sur 2 semaines'),
         'url': _url(f'{ns}:liste_evaluations')},
        {'id': 'saisie', 'label': 'Notes à saisir', 'icon': 'fa-pen-to-square', 'tone': 'orange',
         'value': notes_manquantes,
         'caption': (f'{len(a_corriger)} évaluation(s) incomplète(s)' if a_corriger else 'Toutes les notes sont saisies'),
         'trend': 'down' if notes_manquantes else 'up'},
        {'id': 'moyenne', 'label': 'Moyenne de mes classes', 'icon': 'fa-chart-line', 'tone': 'green',
         'value': moyenne_globale, 'unit': '/20',
         'caption': (f'{_fr(reussite)} % des notes ≥ 10/20' if reussite is not None else 'Aucune note saisie')},
        {'id': 'presence', 'label': 'Présence · 30 jours', 'icon': 'fa-user-check', 'tone': 'teal',
         'value': taux_presence, 'unit': '%',
         'caption': f'{appels} appel(s) effectué(s)' if appels else 'Aucun appel sur 30 jours',
         'trend': ('down' if taux_presence is not None and taux_presence < PRESENCE_SEUIL else '')},
        {'id': 'difficulte', 'label': f'{libelle.capitalize()} en difficulté', 'icon': 'fa-life-ring', 'tone': 'red',
         'value': len(a_suivre), 'caption': 'Moyenne sous 10/20 dans mes notes'},
    ]

    return {
        'ns': ns,
        'is_primaire': is_primaire,
        'est_superieur': est_superieur,
        'libelle': libelle,
        'periode': periode,
        'mini': mini,
        'classes': classes_rows,
        'a_corriger': a_corriger[:5],
        'prochaines': prochaines,
        'a_suivre': a_suivre[:6],
        'seuil': SEUIL,
        'presence_seuil': PRESENCE_SEUIL,
        'moyenne_globale': moyenne_globale,
        'nb_notes': len(toutes),
        'une_classe': len(classes) == 1,
        'charts': {
            'matieres_moyenne': {
                'labels': sorted(notes_par_matiere),
                'values': [round(sum(notes_par_matiere[m]) / len(notes_par_matiere[m]), 2) for m in sorted(notes_par_matiere)],
            },
            'weekdays': weekdays,
            'trend': trend,
            'histogram': histogram,
            'evolution': evolution,
            'classes_moyenne': {
                'labels': [r['nom'] for r in classes_notees],
                'values': [r['moyenne'] for r in classes_notees],
            },
            'classes_presence': [
                {'classe': r['nom'], 'taux': r['presence'], 'watch': r['presence'] < PRESENCE_SEUIL}
                for r in classes_presence
            ],
        },
    }
