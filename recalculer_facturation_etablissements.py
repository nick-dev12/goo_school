#!/usr/bin/env python
"""
Script de migration pour recalculer les montants de facturation
et le nombre d'élèves facturés pour tous les établissements.

Ce script met à jour :
- montant_total_facturation = nombre d'élèves actifs × montant_par_eleve
- nombre_eleves_factures = nombre d'élèves actifs

Usage:
    python manage.py shell < recalculer_facturation_etablissements.py
    ou
    python recalculer_facturation_etablissements.py
"""

import os
import sys
import django

# Configuration de Django
if __name__ == '__main__':
    # Ajouter le répertoire parent au path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Configuration de l'environnement Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
    django.setup()

from school_admin.model.etablissement_model import Etablissement
from school_admin.model.eleve_model import Eleve
from decimal import Decimal

def recalculer_tous_etablissements():
    """
    Recalcule la facturation pour tous les établissements.
    """
    print("=" * 80)
    print("RECALCUL DE LA FACTURATION POUR TOUS LES ETABLISSEMENTS")
    print("=" * 80)
    print()
    
    etablissements = Etablissement.objects.all()
    total_etablissements = etablissements.count()
    etablissements_modifies = 0
    erreurs = []
    
    print(f"Nombre total d'etablissements a traiter : {total_etablissements}")
    print()
    
    for index, etablissement in enumerate(etablissements, 1):
        try:
            # Compter les élèves actifs
            nombre_eleves_actifs = Eleve.objects.filter(
                etablissement=etablissement,
                actif=True
            ).count()
            
            # Calculer le montant total
            montant_total = Decimal(str(nombre_eleves_actifs)) * etablissement.montant_par_eleve
            
            # Récupérer les anciennes valeurs
            ancien_montant = etablissement.montant_total_facturation
            ancien_nombre = etablissement.nombre_eleves_factures
            
            # Mettre à jour
            etablissement.montant_total_facturation = montant_total
            etablissement.nombre_eleves_factures = nombre_eleves_actifs
            
            # Sauvegarder
            etablissement.save(update_fields=['montant_total_facturation', 'nombre_eleves_factures'])
            
            # Vérifier si des changements ont été effectués
            if ancien_montant != montant_total or ancien_nombre != nombre_eleves_actifs:
                etablissements_modifies += 1
                print(f"[{index}/{total_etablissements}] OK {etablissement.nom}")
                print(f"    Eleves actifs : {nombre_eleves_actifs}")
                print(f"    Montant par eleve : {etablissement.montant_par_eleve} FCFA")
                print(f"    Montant total : {montant_total} FCFA (etait {ancien_montant} FCFA)")
                print(f"    Nombre factures : {nombre_eleves_actifs} (etait {ancien_nombre})")
                print()
            else:
                print(f"[{index}/{total_etablissements}] - {etablissement.nom} (deja a jour)")
                
        except Exception as e:
            erreur_msg = f"Erreur pour {etablissement.nom}: {str(e)}"
            erreurs.append(erreur_msg)
            print(f"[{index}/{total_etablissements}] ERREUR: {etablissement.nom}")
            print(f"    {erreur_msg}")
            print()
    
    # Résumé
    print("=" * 80)
    print("RESUME")
    print("=" * 80)
    print(f"Total d'etablissements traites : {total_etablissements}")
    print(f"Etablissements modifies : {etablissements_modifies}")
    print(f"Etablissements deja a jour : {total_etablissements - etablissements_modifies - len(erreurs)}")
    print(f"Erreurs : {len(erreurs)}")
    
    if erreurs:
        print()
        print("ERREURS RENCONTREES :")
        for erreur in erreurs:
            print(f"  - {erreur}")
    
    print()
    print("=" * 80)
    print("RECALCUL TERMINE")
    print("=" * 80)
    
    return etablissements_modifies, len(erreurs)

if __name__ == '__main__':
    try:
        modifies, erreurs = recalculer_tous_etablissements()
        sys.exit(0 if erreurs == 0 else 1)
    except Exception as e:
        print(f"ERREUR FATALE : {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

