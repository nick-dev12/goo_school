#!/usr/bin/env python
"""Script pour ajouter directement la colonne dans la base de données"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.db import connection

print("=" * 50)
print("Ajout de la colonne moyenne_avec_coefficient")
print("=" * 50)

try:
    with connection.cursor() as cursor:
        # Vérifier si la colonne existe
        print("\n1. Vérification de l'existence de la colonne...")
        cursor.execute("""
            SELECT column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns 
            WHERE table_name='school_admin_moyenneperiode' 
            AND column_name='moyenne_avec_coefficient'
        """)
        result = cursor.fetchone()
        
        if result:
            print(f"   ✓ La colonne existe déjà: {result}")
        else:
            print("   ✗ La colonne n'existe pas. Ajout en cours...")
            
            # Ajouter la colonne
            cursor.execute("""
                ALTER TABLE school_admin_moyenneperiode 
                ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL
            """)
            connection.commit()
            print("   ✓ Colonne ajoutée avec succès!")
            
            # Vérification finale
            cursor.execute("""
                SELECT column_name, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns 
                WHERE table_name='school_admin_moyenneperiode' 
                AND column_name='moyenne_avec_coefficient'
            """)
            result = cursor.fetchone()
            if result:
                print(f"   ✓ Vérification réussie: {result}")
            else:
                print("   ✗ ERREUR: La colonne n'a pas été créée!")
                
except Exception as e:
    print(f"\n✗ ERREUR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 50)
print("Terminé!")
print("=" * 50)

