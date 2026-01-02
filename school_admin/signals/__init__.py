"""
Signals pour l'application school_admin
"""
from .examen_signals import (
    creer_notes_examen_automatiques_classes,
    creer_notes_examen_automatiques_matieres
)
# Importer les signals de comptabilité pour qu'ils soient enregistrés
from . import comptabilite_signals

__all__ = [
    'creer_notes_examen_automatiques_classes',
    'creer_notes_examen_automatiques_matieres',
]

