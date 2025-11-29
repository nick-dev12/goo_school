"""
Commande Django pour ajouter la colonne moyenne_avec_coefficient
Usage: python manage.py add_moyenne_coefficient_column
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Ajoute la colonne moyenne_avec_coefficient à la table MoyennePeriode si elle n\'existe pas'

    def handle(self, *args, **options):
        self.stdout.write("Vérification de l'existence de la colonne...")
        
        with connection.cursor() as cursor:
            # Vérifier si la colonne existe
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='school_admin_moyenneperiode' 
                AND column_name='moyenne_avec_coefficient'
            """)
            result = cursor.fetchone()
            
            if result:
                self.stdout.write(
                    self.style.SUCCESS('✓ La colonne moyenne_avec_coefficient existe déjà.')
                )
            else:
                self.stdout.write("La colonne n'existe pas. Ajout en cours...")
                try:
                    cursor.execute("""
                        ALTER TABLE school_admin_moyenneperiode 
                        ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL
                    """)
                    connection.commit()
                    self.stdout.write(
                        self.style.SUCCESS('✓ Colonne moyenne_avec_coefficient ajoutée avec succès!')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Erreur lors de l\'ajout: {e}')
                    )
                    return
        
        # Vérification finale
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='school_admin_moyenneperiode' 
                AND column_name='moyenne_avec_coefficient'
            """)
            result = cursor.fetchone()
            if result:
                self.stdout.write(
                    self.style.SUCCESS('✓ Vérification réussie: la colonne existe maintenant.')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('✗ ERREUR: La colonne n\'existe toujours pas après l\'ajout!')
                )

