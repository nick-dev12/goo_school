"""
Commande Django pour vider toutes les tables sauf CompteUser et Etablissement
"""

from django.core.management.base import BaseCommand
from django.db import transaction

# Import de tous les modèles depuis school_admin.model
from school_admin.model.personnel_administratif_model import PersonnelAdministratif
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.professeur_model import Professeur
from school_admin.model.matiere_model import Matiere
from school_admin.model.note_examen_model import NoteExamen
from school_admin.model.salle_model import Salle
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.affectation_salle_model import AffectationSalle
from school_admin.model.configuration_horaire_model import ConfigurationHoraire
from school_admin.model.presence_model import Presence, ListePresence
from school_admin.model.sanction_model import Sanction
from school_admin.model.parent_model import Parent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.demande_liaison_model import DemandeLiaisonParent
from school_admin.model.facturation_model import Facturation
from school_admin.model.depense_model import Depense
from school_admin.model.prospection_model import Prospection
from school_admin.model.note_commercial_model import NoteCommercial
from school_admin.model.rendez_vous_model import RendezVous
from school_admin.model.compte_rendu_model import CompteRendu


class Command(BaseCommand):
    help = 'Vide toutes les tables sauf CompteUser et Etablissement'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Executer sans confirmation',
        )

    def handle(self, *args, **options):
        # Liste des modèles à vider
        models_to_delete = [
            PersonnelAdministratif, NoteExamen, Parent, Eleve,
            DemandeLiaisonParent, LienFamilial, ConfigurationHoraire,
            AffectationProfesseur, Sanction, Presence, ListePresence,
            Professeur, AffectationSalle, Salle, Matiere, Classe,
            Depense, Facturation, Prospection, CompteRendu, RendezVous,
            NoteCommercial
        ]

        # Demander confirmation si pas de --force
        if not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    '\nATTENTION: Ce script va VIDER toutes les tables!\n'
                    'Sauf: CompteUser et Etablissement\n'
                )
            )
            confirm = input('Continuer? (oui/non): ')
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                self.stdout.write(self.style.ERROR('Operation annulee.'))
                return

        # Vider les tables
        total_deleted = 0

        try:
            with transaction.atomic():
                for model in models_to_delete:
                    count = model.objects.count()
                    if count > 0:
                        deleted = model.objects.all().delete()
                        deleted_count = deleted[0]
                        total_deleted += deleted_count
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'{model.__name__}: {deleted_count} entrees supprimees'
                            )
                        )
                    else:
                        self.stdout.write(
                            f'{model.__name__}: aucune entree (deja vide)'
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nTOTAL: {total_deleted} entrees supprimees'
                    )
                )

                # Afficher les tables conservees
                from school_admin.models import CompteUser, Etablissement
                self.stdout.write('\nTables CONSERVEES:')
                user_count = CompteUser.objects.count()
                etab_count = Etablissement.objects.count()
                self.stdout.write(f'  - CompteUser: {user_count} entrees')
                self.stdout.write(f'  - Etablissement: {etab_count} entrees')

                self.stdout.write(
                    self.style.SUCCESS('\nVidage termine avec succes!')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\nERREUR: {str(e)}')
            )
            self.stdout.write('Les modifications ont ete annulees (rollback).')

