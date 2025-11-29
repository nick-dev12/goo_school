#!/usr/bin/env python
"""
Script pour ajouter la colonne moyenne_avec_coefficient à la table MoyennePeriode
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.db import connection

def add_column():
    with connection.cursor() as cursor:
        try:
            # Vérifier si la colonne existe déjà
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='school_admin_moyenneperiode' 
                AND column_name='moyenne_avec_coefficient'
            """)
            exists = cursor.fetchone()
            
            if exists:
                print("La colonne moyenne_avec_coefficient existe déjà.")
            else:
                # Ajouter la colonne
                cursor.execute("""
                    ALTER TABLE school_admin_moyenneperiode 
                    ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL
                """)
                print("Colonne moyenne_avec_coefficient ajoutée avec succès.")
                
                # Ajouter le commentaire
                cursor.execute("""
                    COMMENT ON COLUMN school_admin_moyenneperiode.moyenne_avec_coefficient 
                    IS 'Moyenne de l''élève multipliée par le coefficient de la matière'
                """)
                print("Commentaire ajouté.")
        except Exception as e:
            print(f"Erreur: {e}")

if __name__ == '__main__':
    print("Début de l'ajout de la colonne...")
    add_column()
    print("Fin du script.")

