"""Contexte hub « Mes élèves » — une classe active via ?classe=."""
from __future__ import annotations


def find_eleves_classe_primaire(eleves_par_categorie, classe_id):
    """Retourne (categorie, classe_data) pour la classe demandée."""
    if not classe_id or not eleves_par_categorie:
        return None, None
    cid = str(classe_id)
    for categorie, data in eleves_par_categorie.items():
        for classe_data in data.get('classes') or []:
            if str(classe_data['classe'].id) == cid:
                return categorie, classe_data
    return None, None


def find_eleves_classe_secondaire(classes_grouped, classe_id):
    """Retourne (categorie, classe_data) pour la classe demandée."""
    if not classe_id or not classes_grouped:
        return None, None
    cid = str(classe_id)
    for categorie, data in classes_grouped.items():
        for classe_data in data.get('classes') or []:
            if str(classe_data['classe'].id) == cid:
                return categorie, classe_data
    return None, None
