"""Ancienne page « Service des enseignants » (supprimée).

Ce module ne reste que pour l'historique des migrations : 0239 référence `_service_defaut` comme valeur par
défaut d'un champ de la table « règles de service », supprimée depuis. Aucun modèle n'est défini ici.
"""

SERVICE_PAR_GRADE_DEFAUT = {
    'professeur_titulaire': 192, 'maitre_conferences': 192, 'maitre_assistant': 192,
    'assistant': 192, 'charge_cours': 192, 'vacataire': 0,
}


def _service_defaut():
    return dict(SERVICE_PAR_GRADE_DEFAUT)
