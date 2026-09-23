"""
Persona assistant pour les comptes Professeur (WebSocket + contexte).
"""


def resolve_professeur_assistant_persona(prof):
    """
    Retourne le persona WS ou None si le prof n'a pas encore accès vocal.

    P0 : seul l'établissement primaire (`type_etablissement == 'primary'`).
    P2+ : persona `enseignant` pour collège / lycée / supérieur.
    """
    if not prof or not getattr(prof, 'actif', False):
        return None
    if not getattr(prof, 'etablissement_id', None):
        return None
    etab = getattr(prof, 'etablissement', None)
    if not etab:
        return None
    if getattr(etab, 'type_etablissement', None) == 'primary':
        return 'enseignant_primaire'
    return None
