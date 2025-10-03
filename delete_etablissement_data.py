#!/usr/bin/env python
import os
import sys
import django
import json
from datetime import datetime

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.etablissement_model import Etablissement

def backup_and_delete_etablissements():
    """Sauvegarde et supprime tous les établissements"""
    
    # Compter les établissements existants
    count = Etablissement.objects.count()
    print(f"Nombre d'établissements trouvés : {count}")
    
    if count == 0:
        print("Aucun établissement à supprimer.")
        return
    
    # Sauvegarde des données (optionnel)
    print("Création de la sauvegarde...")
    etablissements_data = []
    for etab in Etablissement.objects.all():
        etablissements_data.append({
            'nom': etab.nom,
            'email': etab.email,
            'code_etablissement': etab.code_etablissement,
            'adresse': etab.adresse,
            'ville': etab.ville,
            'pays': etab.pays,
            'type_etablissement': etab.type_etablissement,
            'directeur_nom': etab.directeur_nom,
            'directeur_prenom': etab.directeur_prenom,
            'directeur_email': etab.directeur_email,
            'date_creation': etab.date_creation.isoformat() if etab.date_creation else None,
        })
    
    # Sauvegarder dans un fichier JSON
    backup_filename = f"backup_etablissements_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_filename, 'w', encoding='utf-8') as f:
        json.dump(etablissements_data, f, ensure_ascii=False, indent=2)
    print(f"Sauvegarde créée : {backup_filename}")
    
    # Demander confirmation
    confirmation = input(f"Êtes-vous sûr de vouloir supprimer {count} établissement(s) ? (oui/non): ")
    if confirmation.lower() not in ['oui', 'o', 'yes', 'y']:
        print("Suppression annulée.")
        return
    
    # Supprimer tous les établissements
    print("Suppression en cours...")
    deleted_count, _ = Etablissement.objects.all().delete()
    print(f"Suppression terminée ! {deleted_count} établissement(s) supprimé(s).")
    
    # Vérification
    remaining_count = Etablissement.objects.count()
    print(f"Établissements restants : {remaining_count}")

if __name__ == "__main__":
    backup_and_delete_etablissements()