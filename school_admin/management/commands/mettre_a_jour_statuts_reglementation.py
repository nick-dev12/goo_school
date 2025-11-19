# school_admin/management/commands/mettre_a_jour_statuts_reglementation.py

from django.core.management.base import BaseCommand
from school_admin.model.etablissement_model import Etablissement


class Command(BaseCommand):
    help = 'Met à jour le statut de réglementation pour tous les établissements actifs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Affiche des informations détaillées sur chaque établissement',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Début de la mise à jour des statuts de réglementation...'))
        
        etablissements = Etablissement.objects.filter(actif=True)
        total = etablissements.count()
        compteur_modifies = 0
        
        for etablissement in etablissements:
            ancien_statut = etablissement.statut_reglementation
            nouveau_statut = etablissement.mettre_a_jour_statut_reglementation()
            
            if ancien_statut != nouveau_statut:
                compteur_modifies += 1
                if options['verbose']:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {etablissement.nom}: {ancien_statut} -> {nouveau_statut}"
                        )
                    )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nMise à jour terminée: {compteur_modifies}/{total} établissements modifiés'
            )
        )
        
        if compteur_modifies == 0:
            self.stdout.write(
                self.style.SUCCESS('Aucun changement nécessaire. Tous les statuts sont à jour.')
            )

