"""Contexte hub « Présence » — une classe active via ?classe=."""
from __future__ import annotations


def find_presence_classe_entry(classes_grouped, classe_id):
    """Retourne (categorie, classe_data) pour la classe demandée."""
    if not classe_id or not classes_grouped:
        return None, None
    cid = str(classe_id)
    for categorie, data in classes_grouped.items():
        for classe_data in data.get('classes') or []:
            if str(classe_data['classe'].id) == cid:
                return categorie, classe_data
    return None, None
