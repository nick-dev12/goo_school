from django.db import models
from .model.etablissement_model import Etablissement
from .model.compte_user import CompteUser
from .model.personnel_administratif_model import PersonnelAdministratif
from .model.classe_model import Classe
from .model.eleve_model import Eleve
from .model.parent_model import Parent
from .model.lien_familial_model import LienFamilial
from .model.demande_liaison_model import DemandeLiaisonParent
from .model.prospection_model import Prospection
from .model.note_commercial_model import NoteCommercial
from .model.rendez_vous_model import RendezVous
from .model.facturation_model import Facturation
from .model.professeur_model import Professeur
from .model.matiere_model import Matiere
from .model.note_examen_model import NoteExamen
from .model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
from .model.evaluation_primaire_model import EvaluationPrimaire
from .model.note_primaire_model import NotePrimaire, MoyenneMatierePrimaire
from .model.convocation_model import Convocation

# Exposer les modèles au niveau du module
__all__ = [
    'CompteUser', 'Etablissement', 'PersonnelAdministratif', 'Classe', 'Eleve', 
    'Parent', 'LienFamilial', 'DemandeLiaisonParent',
    'Prospection', 'NoteCommercial', 'RendezVous', 'Facturation', 'Professeur', 
    'Matiere', 'NoteExamen', 'AffectationProfesseurPrimaire', 'EvaluationPrimaire', 
    'NotePrimaire', 'MoyenneMatierePrimaire', 'Convocation'
]