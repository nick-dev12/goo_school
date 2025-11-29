#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.db import connection

print("Vérification de l'existence de la colonne...")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='school_admin_moyenneperiode' 
        AND column_name='moyenne_avec_coefficient'
    """)
    exists = cursor.fetchone()
    
    if exists:
        print("✓ La colonne moyenne_avec_coefficient existe déjà.")
    else:
        print("✗ La colonne n'existe pas. Ajout en cours...")
        try:
            cursor.execute("""
                ALTER TABLE school_admin_moyenneperiode 
                ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL
            """)
            connection.commit()
            print("✓ Colonne moyenne_avec_coefficient ajoutée avec succès!")
        except Exception as e:
            print(f"✗ Erreur lors de l'ajout: {e}")
            sys.exit(1)

print("Vérification finale...")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='school_admin_moyenneperiode' 
        AND column_name='moyenne_avec_coefficient'
    """)
    exists = cursor.fetchone()
    if exists:
        print("✓ Vérification réussie: la colonne existe maintenant.")
    else:
        print("✗ ERREUR: La colonne n'existe toujours pas après l'ajout!")
        sys.exit(1)

