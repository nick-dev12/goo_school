"""
Périmètre assistant élève (compte élève seul) — accès « moi-même » uniquement.
"""
from __future__ import annotations


def get_self_eleve(ctx):
    """Élève connecté porté par le contexte (persona eleve)."""
    if getattr(ctx, 'persona', '') != 'eleve':
        return None
    eleve = getattr(ctx, 'eleve', None)
    if not eleve or not getattr(eleve, 'actif', True):
        return None
    return eleve


def refus_acces_autre_eleve(eleve_id=None):
    return {
        'erreur': (
            "Tu ne peux consulter que ton propre espace élève. "
            "Les données d’un autre élève ne sont pas accessibles."
        ),
        'eleve_id': eleve_id,
        'statut': 'acces_refuse',
    }


def assert_self_only(ctx, eleve_id=None):
    """
    None si la cible est l’élève du contexte (ou absente).
    Refus si un eleve_id différent est demandé.
    """
    self_eleve = get_self_eleve(ctx)
    if not self_eleve:
        return {
            'erreur': 'Compte élève requis.',
            'statut': 'erreur',
        }
    if eleve_id is None:
        return None
    try:
        requested = int(eleve_id)
    except (TypeError, ValueError):
        return refus_acces_autre_eleve(eleve_id)
    if requested != self_eleve.pk:
        return refus_acces_autre_eleve(requested)
    return None
