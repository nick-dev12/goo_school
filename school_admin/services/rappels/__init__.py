"""Rappels automatiques.

Une situation (carte) est définie une seule fois dans ``services/context_popups.py`` ;
ce paquet décide quand la rappeler hors connexion (cloche + push) et tient le journal.
Voir feuille_route_rappels_automatiques_2026-11-14.md.
"""
from .moteur import generer, rappels_dus, parametres  # noqa: F401
