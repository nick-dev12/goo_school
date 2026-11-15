"""
Signals pour l'application school_admin
"""
from .examen_signals import (
    creer_notes_examen_automatiques_classes,
    creer_notes_examen_automatiques_matieres
)
# Importer les signals de comptabilité pour qu'ils soient enregistrés
from . import comptabilite_signals
from . import auth_user_type  # noqa: F401 — session `_auth_user_type`
from . import push_lifecycle  # noqa: F401
from . import family_events  # noqa: F401
from . import context_popup  # noqa: F401

__all__ = [
    'creer_notes_examen_automatiques_classes',
    'creer_notes_examen_automatiques_matieres',
]

