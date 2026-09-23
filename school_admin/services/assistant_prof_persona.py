"""
Persona assistant pour les comptes Professeur (WebSocket + contexte).

Source de vérité assistant : **type_etablissement** de l'établissement rattaché.
Le champ Professeur.niveau_enseignement est dérivé (sync à l'enregistrement + migration).
"""
from __future__ import annotations

# Mapping type établissement → niveau_enseignement prof (aligné création professeur)
TYPE_ETABLISSEMENT_TO_NIVEAU = {
    'primary': 'primaire',
    'primaire': 'primaire',
    'collège': 'college',
    'college': 'college',
    'lycée': 'lycee',
    'lycee': 'lycee',
    'collège_lycée': 'lycee',
    'college_lycee': 'lycee',
    'lycee_college': 'lycee',
    'mixte': 'primaire',
    'superieur': 'superieur',
}


def niveau_enseignement_for_type_etablissement(type_etablissement) -> str:
    if not type_etablissement:
        return 'college'
    key = str(type_etablissement).strip()
    return TYPE_ETABLISSEMENT_TO_NIVEAU.get(key, 'college')


def is_etablissement_primaire(etablissement) -> bool:
    return getattr(etablissement, 'type_etablissement', None) == 'primary'


def is_professeur_etablissement_primaire(prof) -> bool:
    if not prof or not getattr(prof, 'etablissement_id', None):
        return False
    etab = getattr(prof, 'etablissement', None)
    if etab is None:
        return False
    return is_etablissement_primaire(etab)


def expected_niveau_enseignement(prof) -> str | None:
    if not prof or not getattr(prof, 'etablissement_id', None):
        return None
    etab = getattr(prof, 'etablissement', None)
    if etab is None:
        return None
    return niveau_enseignement_for_type_etablissement(etab.type_etablissement)


def professeur_niveau_coherent_avec_etablissement(prof) -> bool:
    """False si niveau_enseignement diverge du type d'établissement (incohérence données)."""
    expected = expected_niveau_enseignement(prof)
    if expected is None:
        return True
    return getattr(prof, 'niveau_enseignement', None) == expected


def sync_professeur_niveau_from_etablissement(prof):
    """Aligne niveau_enseignement sur le type d'établissement (sans save)."""
    expected = expected_niveau_enseignement(prof)
    if expected and getattr(prof, 'niveau_enseignement', None) != expected:
        prof.niveau_enseignement = expected
    return prof


def resolve_professeur_assistant_persona(prof):
    """
    Retourne le persona WS ou None si le prof n'a pas encore accès vocal.

    Uniquement ``type_etablissement == 'primary'`` → ``enseignant_primaire`` ;
    sinon ``enseignant`` (collège, lycée, supérieur, mixte, etc.).
    """
    if not prof or not getattr(prof, 'actif', False):
        return None
    if not getattr(prof, 'etablissement_id', None):
        return None
    etab = getattr(prof, 'etablissement', None)
    if not etab:
        return None
    if is_etablissement_primaire(etab):
        return 'enseignant_primaire'
    return 'enseignant'
