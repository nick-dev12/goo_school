#!/usr/bin/env python
import os
import sys
import django
from django.db import connection

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

def delete_etablissements_cascade():
    """Supprime tous les établissements en gérant les contraintes de clé étrangère"""
    
    with connection.cursor() as cursor:
        # Compter les établissements
        cursor.execute("SELECT COUNT(*) FROM school_admin_etablissement")
        count = cursor.fetchone()[0]
        print(f"Nombre d'établissements trouvés : {count}")
        
        if count == 0:
            print("Aucun établissement à supprimer.")
            return
        
        # Demander confirmation
        confirmation = input(f"Êtes-vous sûr de vouloir supprimer {count} établissement(s) et toutes les données liées ? (oui/non): ")
        if confirmation.lower() not in ['oui', 'o', 'yes', 'y']:
            print("Suppression annulée.")
            return
        
        print("Suppression en cours...")
        
        try:
            # Désactiver temporairement les contraintes de clé étrangère
            cursor.execute("SET session_replication_role = replica;")
            
            # Supprimer tous les établissements
            cursor.execute("DELETE FROM school_admin_etablissement")
            deleted_count = cursor.rowcount
            print(f"Suppression terminée ! {deleted_count} établissement(s) supprimé(s).")
            
            # Réactiver les contraintes de clé étrangère
            cursor.execute("SET session_replication_role = DEFAULT;")
            
        except Exception as e:
            print(f"Erreur lors de la suppression : {e}")
            # Réactiver les contraintes en cas d'erreur
            cursor.execute("SET session_replication_role = DEFAULT;")
            return
        
        # Vérification
        cursor.execute("SELECT COUNT(*) FROM school_admin_etablissement")
        remaining_count = cursor.fetchone()[0]
        print(f"Établissements restants : {remaining_count}")

if __name__ == "__main__":
    delete_etablissements_cascade()