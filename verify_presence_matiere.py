"""
Script de vérification pour identifier les présences sans matière
dans les établissements secondaires (lycée, collège, collège_lycée)
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence
from school_admin.model.etablissement_model import Etablissement
from django.db.models import Q, Count
from datetime import date, timedelta

def verifier_presences_sans_matiere():
    """
    Vérifie les présences sans matière dans les établissements secondaires
    """
    print("=" * 80)
    print("VÉRIFICATION DES PRÉSENCES SANS MATIÈRE")
    print("=" * 80)
    print()
    
    # Types d'établissements secondaires
    types_secondaires = ['lycée', 'collège', 'collège_lycée']
    
    # Récupérer tous les établissements secondaires
    etablissements_secondaires = Etablissement.objects.filter(
        type_etablissement__in=types_secondaires
    )
    
    print(f"Nombre d'établissements secondaires: {etablissements_secondaires.count()}")
    print()
    
    # Statistiques globales
    total_presences_secondaires = 0
    total_presences_sans_matiere = 0
    total_presences_avec_matiere = 0
    
    # Par établissement
    for etablissement in etablissements_secondaires:
        print(f"\n{'=' * 80}")
        print(f"Établissement: {etablissement.nom} (Type: {etablissement.type_etablissement})")
        print(f"{'=' * 80}")
        
        # Toutes les présences de cet établissement
        presences_etablissement = Presence.objects.filter(
            etablissement=etablissement
        )
        
        # Présences avec matière
        presences_avec_matiere = presences_etablissement.filter(
            matiere__isnull=False
        )
        
        # Présences sans matière
        presences_sans_matiere = presences_etablissement.filter(
            matiere__isnull=True
        )
        
        total_etablissement = presences_etablissement.count()
        avec_matiere = presences_avec_matiere.count()
        sans_matiere = presences_sans_matiere.count()
        
        total_presences_secondaires += total_etablissement
        total_presences_avec_matiere += avec_matiere
        total_presences_sans_matiere += sans_matiere
        
        print(f"Total présences: {total_etablissement}")
        print(f"  - Avec matière: {avec_matiere} ({avec_matiere*100/total_etablissement if total_etablissement > 0 else 0:.2f}%)")
        print(f"  - Sans matière: {sans_matiere} ({sans_matiere*100/total_etablissement if total_etablissement > 0 else 0:.2f}%)")
        
        if sans_matiere > 0:
            print(f"\nPROBLEME DETECTE: {sans_matiere} presences sans matiere!")
            print("\nDétails des présences sans matière:")
            print("-" * 80)
            
            # Détails des présences sans matière
            for presence in presences_sans_matiere.select_related('eleve', 'classe', 'professeur')[:20]:
                print(f"  ID: {presence.id} | Élève: {presence.eleve.nom} {presence.eleve.prenom} | "
                      f"Classe: {presence.classe.nom} | Date: {presence.date} | "
                      f"Prof: {presence.professeur.nom} | Statut: {presence.statut}")
            
            if sans_matiere > 20:
                print(f"  ... et {sans_matiere - 20} autres présences sans matière")
            
            # Grouper par date
            print("\nRépartition par date:")
            presences_par_date = presences_sans_matiere.values('date').annotate(
                count=Count('id')
            ).order_by('-date')[:10]
            
            for item in presences_par_date:
                print(f"  {item['date']}: {item['count']} présences sans matière")
            
            # Grouper par classe
            print("\nRépartition par classe:")
            presences_par_classe = presences_sans_matiere.values(
                'classe__nom'
            ).annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            for item in presences_par_classe:
                print(f"  {item['classe__nom']}: {item['count']} présences sans matière")
            
            # Grouper par professeur
            print("\nRépartition par professeur:")
            presences_par_prof = presences_sans_matiere.values(
                'professeur__nom', 'professeur__prenom'
            ).annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            for item in presences_par_prof:
                print(f"  {item['professeur__nom']} {item['professeur__prenom']}: {item['count']} présences sans matière")
    
    # Résumé global
    print()
    print("=" * 80)
    print("RÉSUMÉ GLOBAL")
    print("=" * 80)
    print(f"Total présences dans établissements secondaires: {total_presences_secondaires}")
    print(f"  - Avec matière: {total_presences_avec_matiere} ({total_presences_avec_matiere*100/total_presences_secondaires if total_presences_secondaires > 0 else 0:.2f}%)")
    print(f"  - Sans matière: {total_presences_sans_matiere} ({total_presences_sans_matiere*100/total_presences_secondaires if total_presences_secondaires > 0 else 0:.2f}%)")
    
    if total_presences_sans_matiere > 0:
        print()
        print("ATTENTION: Des presences sans matiere ont ete detectees!")
        print("   Ces presences devraient avoir une matiere pour les etablissements secondaires.")
    else:
        print()
        print("OK: Aucun probleme detecte. Toutes les presences ont une matiere.")
    
    print()
    print("=" * 80)
    
    # Vérifier les présences récentes (7 derniers jours)
    print("\nVÉRIFICATION DES PRÉSENCES RÉCENTES (7 derniers jours)")
    print("=" * 80)
    
    date_limite = date.today() - timedelta(days=7)
    
    presences_recentes_sans_matiere = Presence.objects.filter(
        etablissement__type_etablissement__in=types_secondaires,
        matiere__isnull=True,
        date__gte=date_limite
    ).select_related('eleve', 'classe', 'professeur', 'etablissement')
    
    print(f"Nombre de présences sans matière dans les 7 derniers jours: {presences_recentes_sans_matiere.count()}")
    
    if presences_recentes_sans_matiere.count() > 0:
        print("\nDétails des présences récentes sans matière:")
        print("-" * 80)
        
        for presence in presences_recentes_sans_matiere[:20]:
            print(f"  ID: {presence.id} | Établissement: {presence.etablissement.nom} | "
                  f"Élève: {presence.eleve.nom} {presence.eleve.prenom} | "
                  f"Classe: {presence.classe.nom} | Date: {presence.date} | "
                  f"Prof: {presence.professeur.nom} | Statut: {presence.statut} | "
                  f"Date création: {presence.date_creation}")
    
    print()
    print("=" * 80)

if __name__ == '__main__':
    verifier_presences_sans_matiere()

