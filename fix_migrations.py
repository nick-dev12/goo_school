import os
import django
import sys

# Configurer l'environnement Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

# Importer les modèles après avoir configuré Django
from django.db import connection

# Afficher toutes les migrations dans la table django_migrations
with connection.cursor() as cursor:
    cursor.execute("SELECT app, name FROM django_migrations WHERE app='school_admin' ORDER BY id")
    rows = cursor.fetchall()
    
    print("Migrations actuelles dans la base de données :")
    print("-" * 40)
    for row in rows:
        print(f"App: {row[0]}, Migration: {row[1]}")
    print("-" * 40)
    
    # Vérifier si la migration problématique existe
    cursor.execute("SELECT COUNT(*) FROM django_migrations WHERE app='school_admin' AND name='0007_generate_etablissement_codes'")
    count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"La migration problématique existe ({count} entrées).")
        
        # Supprimer la migration problématique
        user_input = input("Voulez-vous supprimer cette migration de la base de données ? (oui/non): ")
        if user_input.lower() == 'oui':
            cursor.execute("DELETE FROM django_migrations WHERE app='school_admin' AND name='0007_generate_etablissement_codes'")
            print("Migration supprimée.")
        else:
            print("Aucune modification n'a été effectuée.")
    else:
        print("La migration problématique n'existe pas dans la base de données.")
