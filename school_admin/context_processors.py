"""Context processors pour l'application school_admin."""

from __future__ import annotations

from typing import Dict

from django.utils.functional import SimpleLazyObject


def notifications_enseignant(request) -> Dict[str, int]:
    """Retourne le nombre de notifications non lues pour l'enseignant connecté."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    # Importer localement pour éviter les problèmes d'import circulaire
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.notification_enseignant_model import NotificationEnseignant

    if not isinstance(user, Professeur):
        return {}

    def _count() -> int:
        return NotificationEnseignant.objects.filter(
            enseignant=user, statut='non_lu'
        ).count()

    return {
        'notifications_enseignant_non_lues': SimpleLazyObject(_count),
    }


def notifications_parent(request) -> Dict[str, int]:
    """Retourne le nombre de notifications non lues pour le parent connecté."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    from school_admin.model.parent_model import Parent
    from school_admin.model.notification_parent_model import NotificationParent

    if not isinstance(user, Parent):
        return {}

    def _count() -> int:
        return NotificationParent.objects.filter(
            parent=user, statut='non_lu'
        ).count()

    return {
        'notifications_parent_non_lues': SimpleLazyObject(_count),
    }


def notifications_eleve(request) -> Dict[str, int]:
    """Retourne le nombre de notifications non lues pour l'élève connecté."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    from school_admin.model.eleve_model import Eleve
    from school_admin.model.notification_eleve_model import NotificationEleve

    if not isinstance(user, Eleve):
        return {}

    def _count() -> int:
        return NotificationEleve.objects.filter(
            eleve=user, statut='non_lu'
        ).count()

    return {
        'notifications_eleve_non_lues': SimpleLazyObject(_count),
    }
