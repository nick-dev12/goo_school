"""
Signals pour l'application school_admin
"""
from .examen_signals import (
    creer_notes_examen_automatiques_classes,
    creer_notes_examen_automatiques_matieres
)

__all__ = [
    'creer_notes_examen_automatiques_classes',
    'creer_notes_examen_automatiques_matieres',
]

