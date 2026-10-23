"""
Contrôle continu du supérieur, pondéré par type d'évaluation.

Toutes les évaluations de l'EC dans la classe et le semestre comptent, quel que soit l'enseignant
(CM, TD G1, TD G2…). Chaque type (TD, TP, devoir, partiel…) donne une moyenne ; la moyenne de
contrôle continu est la moyenne pondérée de ces types selon les règles de l'établissement
(ReglesExamen.poids_cc). Sans pondération définie, les types présents comptent à égalité.
Une évaluation sans type est classée « autre ».
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

D0 = Decimal('0')
LIBELLES = {'interrogation': 'Interrogations', 'devoir': 'Devoirs', 'td': 'TD', 'tp': 'TP', 'expose': 'Exposés',
            'projet': 'Projets', 'partiel': 'Partiels', 'autre': 'Autres'}


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def poids_par_type(regle):
    poids = {}
    for k, v in (getattr(regle, 'poids_cc', None) or {}).items():
        try:
            poids[k] = Decimal(str(v))
        except Exception:
            continue
    return poids


def calculer(notes_par_type, regle):
    """notes_par_type : {type: [note_sur_20, ...]} → {'moyenne', 'detail': [{type, libelle, moyenne, poids, nb}]}"""
    poids = poids_par_type(regle)
    moyennes = OrderedDict()
    for t, valeurs in notes_par_type.items():
        if valeurs:
            moyennes[t] = _q(sum(valeurs, D0) / len(valeurs))
    if not moyennes:
        return {'moyenne': None, 'detail': []}
    pondere = {t: poids.get(t, D0) for t in moyennes}
    if not any(p > 0 for p in pondere.values()):
        pondere = {t: Decimal('1') for t in moyennes}  # aucune pondération utile : types à égalité
    total = sum(pondere.values(), D0)
    moyenne = _q(sum((moyennes[t] * pondere[t] for t in moyennes), D0) / total) if total else None
    detail = [{'type': t, 'libelle': LIBELLES.get(t, t), 'moyenne': m, 'nb': len(notes_par_type[t]),
               'poids': _q(pondere[t] / total * 100) if total else D0} for t, m in moyennes.items()]
    return {'moyenne': moyenne, 'detail': detail}


def moyenne_cc(eleve, classe, matiere, periode, annee=None, regle=None):
    """Moyenne de contrôle continu pondérée d'un étudiant pour un EC (toutes évaluations de l'EC)."""
    from school_admin.model.evaluation_model import Evaluation, Note
    from school_admin.services.examens import regles

    regle = regle or regles(classe.etablissement)
    evaluations = Evaluation.objects.filter(classe=classe, matiere=matiere, actif=True)
    if periode is not None:
        evaluations = evaluations.filter(periode_scolaire=periode)
    if annee is not None:
        evaluations = evaluations.filter(annee_scolaire=annee)
    evaluations = list(evaluations)
    notes = (Note.objects.filter(eleve=eleve, evaluation__in=evaluations, absent=False, note__isnull=False)
             .select_related('evaluation'))
    par_type, ids = OrderedDict(), []
    for n in notes:
        e = n.evaluation
        bareme = Decimal(str(e.bareme or 20)) or Decimal('20')
        par_type.setdefault(e.type_evaluation or 'autre', []).append(Decimal(str(n.note)) / bareme * 20)
        ids.append(e.id)
    resultat = calculer(par_type, regle)
    resultat['evaluations'] = ids
    resultat['nb_evaluations'] = len(evaluations)
    return resultat
