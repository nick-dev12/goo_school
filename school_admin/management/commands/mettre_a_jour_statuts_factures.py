from django.core.management.base import BaseCommand
from school_admin.model.facturation_model import Facturation


class Command(BaseCommand):
    help = 'Met à jour automatiquement les statuts des factures basés sur les dates d\'échéance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les factures qui seraient mises à jour sans les modifier',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('Mode dry-run activé - Aucune modification ne sera effectuée')
            )
            
            # Afficher les factures qui seraient mises à jour
            factures_a_mettre_a_jour = Facturation.objects.filter(
                statut__in=['en_attente', 'en_retard', 'impaye', 'contentieux']
            )
            
            self.stdout.write(f'Factures à mettre à jour: {factures_a_mettre_a_jour.count()}')
            
            for facture in factures_a_mettre_a_jour:
                self.stdout.write(
                    f'- Facture {facture.numero_facture} ({facture.etablissement.nom}) - '
                    f'Statut actuel: {facture.get_statut_display()}'
                )
        else:
            # Exécuter la mise à jour
            nombre_mises_a_jour = Facturation.mettre_a_jour_tous_les_statuts()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Mise à jour terminée: {nombre_mises_a_jour} factures mises à jour'
                )
            )
