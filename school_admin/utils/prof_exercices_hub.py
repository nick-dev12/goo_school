"""Contexte hub « Exercices de maison »."""
from __future__ import annotations


def build_matieres_data_exercices(
    professeur,
    classe,
    matieres,
    periode_scolaire,
    annee_scolaire,
):
    """Liste matières + nombre d'exercices actifs pour la classe/période."""
    if not classe or not matieres:
        return []

    from ..model.exercice_maison_model import ExerciceMaison

    result = []
    for matiere in matieres:
        qs = ExerciceMaison.objects.filter(
            professeur=professeur,
            classe=classe,
            matiere=matiere,
            actif=True,
        )
        if annee_scolaire:
            qs = qs.filter(annee_scolaire=annee_scolaire)
        if periode_scolaire:
            qs = qs.filter(periode_scolaire=periode_scolaire)
        result.append({
            'matiere': matiere,
            'nombre_exercices': qs.count(),
        })
    return result


def exercices_categorie_for_classe(classes_options, classe_id):
    if not classe_id or not classes_options:
        return None
    cid = str(classe_id)
    for item in classes_options:
        if str(item['classe'].id) == cid:
            return item.get('categorie')
    return None
