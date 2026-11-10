"""Définitions partagées des compteurs des tableaux de bord historiques."""
from datetime import timedelta

from django.utils import timezone


def evaluations_semaine(etablissement, annee_scolaire):
    from school_admin.model.evaluation_model import Evaluation
    from school_admin.model.evaluation_primaire_model import EvaluationPrimaire
    if annee_scolaire is None:
        return 0
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday())
    filters = {
        'classe__etablissement': etablissement, 'annee_scolaire': annee_scolaire,
        'actif': True, 'date_evaluation__range': (start, start + timedelta(days=6)),
    }
    return Evaluation.objects.filter(**filters).count() + EvaluationPrimaire.objects.filter(**filters).count()
