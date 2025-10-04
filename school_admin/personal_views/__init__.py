from .commercial_view import commercial_ajouter_etablissement, commercial_liste_etablissements, commercial_detail_etablissement, dashboard_commercial
from .administrateur_view import *
from .comptable_view import *
from .directeur_view import *
from .administrateur_etablissement_view import *
from .personnel_administratif_view import *
from .secretaire_view import *

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
    'dashboard_directeur',
    'dashboard_administrateur_etablissement',
    'dashboard_personnel_administratif',
    'profil_personnel_administratif',
    'liste_eleves_personnel',
    'liste_enseignants_personnel',
    'dashboard_secretaire'
]