"""Efface le texte en clair des mots de passe provisoires qui ne servent plus.

Un mot de passe provisoire est « périmé » quand la personne en a déjà choisi un autre par un ancien
parcours (page profil, réinitialisation) qui ne l'effaçait pas. Ceux qui sont encore en vigueur sont
gardés : la personne devra les remplacer à sa prochaine connexion.

Par défaut, simple simulation. Pour effacer réellement : --appliquer.
Chaque vérification calcule un hachage : compter environ une demi-seconde par compte.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from school_admin.services.mots_de_passe import INDICATEURS


class Command(BaseCommand):
    help = "Efface les mots de passe provisoires en clair qui ne correspondent plus au mot de passe du compte."

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true', help='Effacer réellement (sinon simulation).')

    def handle(self, *args, **options):
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.parent_model import Parent
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif
        from school_admin.model.professeur_model import Professeur

        total_perimes = total_en_vigueur = 0
        for modele in (Eleve, Parent, Professeur, PersonnelAdministratif):
            perimes = en_vigueur = 0
            comptes = modele.objects.exclude(Q(mot_de_passe_provisoire='') | Q(mot_de_passe_provisoire__isnull=True))
            for compte in comptes.only('pk', 'password', 'mot_de_passe_provisoire').iterator():
                if compte.check_password(compte.mot_de_passe_provisoire):
                    en_vigueur += 1
                    continue
                perimes += 1
                if options['appliquer']:
                    valeurs = {'mot_de_passe_provisoire': ''}
                    indicateur = INDICATEURS.get(modele._meta.model_name)
                    if indicateur:
                        valeurs[indicateur] = True
                    modele.objects.filter(pk=compte.pk).update(**valeurs)
            total_perimes += perimes
            total_en_vigueur += en_vigueur
            self.stdout.write(f'{modele.__name__:24} périmés : {perimes:4}   encore en vigueur : {en_vigueur:4}')
        action = 'effacés' if options['appliquer'] else 'à effacer (simulation, rien n’a été modifié)'
        self.stdout.write(self.style.SUCCESS(
            f'{total_perimes} mot(s) de passe provisoire(s) périmé(s) {action} ; {total_en_vigueur} encore en vigueur.'))
