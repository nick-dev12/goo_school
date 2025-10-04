from django.db import models
from .model.etablissement_model import Etablissement
from .model.compte_user import CompteUser
from .model.personnel_administratif_model import PersonnelAdministratif
from .model.classe_model import Classe
from .model.eleve_model import Eleve
from .model.prospection_model import Prospection
from .model.note_commercial_model import NoteCommercial
from .model.rendez_vous_model import RendezVous

# Exposer les modèles au niveau du module
__all__ = ['CompteUser', 'Etablissement', 'PersonnelAdministratif', 'Classe', 'Eleve', 'Prospection', 'NoteCommercial', 'RendezVous']