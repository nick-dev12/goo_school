"""Efface le mot de passe provisoire en clair dès que la personne en a choisi un autre."""
from django.db.models.signals import post_save

from school_admin.model.eleve_model import Eleve
from school_admin.model.parent_model import Parent
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.professeur_model import Professeur
from school_admin.services.mots_de_passe import effacer_si_remplace

for _modele in (Eleve, Parent, Professeur, PersonnelAdministratif):
    post_save.connect(effacer_si_remplace, sender=_modele, dispatch_uid=f'mdp_provisoire_{_modele.__name__}')
