from .commercial_view import commercial_ajouter_etablissement, commercial_liste_etablissements, commercial_detail_etablissement, dashboard_commercial
from .administrateur_view import *
from .comptable_view import *
from .directeur_view import *

__all__ = [
    'commercial_ajouter_etablissement',
    'commercial_liste_etablissements',
    'commercial_detail_etablissement',
    'dashboard_commercial',
    'dashboard_administrateur',
    'add_team_member',
    'parametres',
    'management_equipes',
    'etablissements',
    'ajout_etablissement',
    'detaille_etablissement',
    'message_etablissement',
    'detail_message',
    'annonces',
    'dashboard_comptable',
    'dashboard_directeur'
]