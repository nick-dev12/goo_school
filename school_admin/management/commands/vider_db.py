"""
Commande Django pour vider toutes les tables sauf CompteUser et Etablissement
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.apps import apps


class Command(BaseCommand):
    help = 'Vide toutes les tables sauf CompteUser et Etablissement'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Executer sans confirmation',
        )

    def handle(self, *args, **options):
        # Obtenir tous les modèles de l'application school_admin
        app_models = apps.get_app_config('school_admin').get_models()
        
        # Modèles à exclure (ne pas supprimer)
        excluded_models = {'CompteUser', 'Etablissement'}
        
        # Filtrer les modèles à supprimer
        models_to_delete = [
            model for model in app_models
            if model.__name__ not in excluded_models
        ]
        
        # Trier les modèles par ordre alphabétique pour un affichage cohérent
        models_to_delete.sort(key=lambda m: m.__name__)
        
        # Demander confirmation si pas de --force
        if not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    '\n' + '='*60 + '\n'
                    'ATTENTION: Ce script va VIDER toutes les tables!\n'
                    'Sauf: CompteUser et Etablissement\n'
                    '='*60 + '\n'
                )
            )
            self.stdout.write(f'Nombre de tables a vider: {len(models_to_delete)}\n')
            confirm = input('Continuer? (oui/non): ')
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                self.stdout.write(self.style.ERROR('Operation annulee.'))
                return

        # Vider les tables
        total_deleted = 0
        models_processed = []

        try:
            with transaction.atomic():
                for model in models_to_delete:
                    try:
                        count = model.objects.count()
                        if count > 0:
                            deleted = model.objects.all().delete()
                            deleted_count = deleted[0]
                            total_deleted += deleted_count
                            models_processed.append({
                                'name': model.__name__,
                                'count': deleted_count,
                                'status': 'deleted'
                            })
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  {model.__name__}: {deleted_count} entrees supprimees'
                                )
                            )
                        else:
                            models_processed.append({
                                'name': model.__name__,
                                'count': 0,
                                'status': 'empty'
                            })
                            self.stdout.write(
                                f'  {model.__name__}: aucune entree (deja vide)'
                            )
                    except Exception as e:
                        models_processed.append({
                            'name': model.__name__,
                            'count': 0,
                            'status': f'error: {str(e)}'
                        })
                        self.stdout.write(
                            self.style.ERROR(
                                f'  {model.__name__}: ERREUR - {str(e)}'
                            )
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n' + '='*60 + '\n'
                        f'TOTAL: {total_deleted} entrees supprimees\n'
                        f'Nombre de tables traitees: {len(models_processed)}\n'
                        + '='*60
                    )
                )

                # Afficher les tables conservees
                from school_admin.model.compte_user import CompteUser
                from school_admin.model.etablissement_model import Etablissement
                
                self.stdout.write('\nTables CONSERVEES:')
                try:
                    user_count = CompteUser.objects.count()
                    self.stdout.write(f'  - CompteUser: {user_count} entrees')
                except Exception as e:
                    self.stdout.write(f'  - CompteUser: ERREUR - {str(e)}')
                
                try:
                    etab_count = Etablissement.objects.count()
                    self.stdout.write(f'  - Etablissement: {etab_count} entrees')
                except Exception as e:
                    self.stdout.write(f'  - Etablissement: ERREUR - {str(e)}')

                self.stdout.write(
                    self.style.SUCCESS('\nVidage termine avec succes!')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\nERREUR CRITIQUE: {str(e)}')
            )
            self.stdout.write('Les modifications ont ete annulees (rollback).')
            raise
