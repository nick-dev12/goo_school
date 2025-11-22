#!/usr/bin/env python
"""
Script de test pour récupérer les présences d'un élève selon une matière
"""
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence, SoumissionListePresence
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur
from datetime import date

def test_presences_eleve():
    """Test de récupération des présences d'un élève par matière"""
    
    print("=" * 80)
    print("TEST DE RÉCUPÉRATION DES PRÉSENCES D'UN ÉLÈVE PAR MATIÈRE")
    print("=" * 80)
    
    # Données de test depuis l'image
    eleve_id = 2230
    classe_id = 110
    etablissement_id = 34
    professeur_id = 119
    matiere_id_1 = 86  # Anglais
    matiere_id_2 = 89  # Histoire-Géographie
    
    print(f"\n1. Récupération de l'élève ID: {eleve_id}")
    try:
        eleve = Eleve.objects.get(id=eleve_id, actif=True)
        print(f"   [OK] Eleve trouve: {eleve.nom} {eleve.prenom}")
        print(f"   - Classe: {eleve.classe.nom if eleve.classe else 'N/A'}")
    except Eleve.DoesNotExist:
        print(f"   [ERREUR] Eleve {eleve_id} non trouve")
        return
    
    print(f"\n2. Récupération de la classe ID: {classe_id}")
    try:
        classe = Classe.objects.get(id=classe_id)
        print(f"   [OK] Classe trouvee: {classe.nom}")
        print(f"   - Etablissement: {classe.etablissement.nom}")
        print(f"   - Type: {classe.etablissement.type_etablissement}")
    except Classe.DoesNotExist:
        print(f"   [ERREUR] Classe {classe_id} non trouvee")
        return
    
    print(f"\n3. Récupération du professeur ID: {professeur_id}")
    try:
        professeur = Professeur.objects.get(id=professeur_id)
        print(f"   [OK] Professeur trouve: {professeur.nom_complet}")
    except Professeur.DoesNotExist:
        print(f"   [ERREUR] Professeur {professeur_id} non trouve")
        return
    
    # Test pour chaque matière
    for matiere_id in [matiere_id_1, matiere_id_2]:
        print(f"\n{'=' * 80}")
        print(f"TEST POUR LA MATIÈRE ID: {matiere_id}")
        print(f"{'=' * 80}")
        
        try:
            matiere = Matiere.objects.get(id=matiere_id, etablissement=classe.etablissement)
            print(f"   [OK] Matiere trouvee: {matiere.nom}")
        except Matiere.DoesNotExist:
            print(f"   [ERREUR] Matiere {matiere_id} non trouvee")
            continue
        
        # 1. Vérifier les soumissions
        print(f"\n4. Vérification des soumissions pour la matière {matiere.nom}")
        soumissions = SoumissionListePresence.objects.filter(
            classe=classe,
            professeur=professeur,
            matiere=matiere
        ).order_by('-date')
        
        print(f"   Nombre de soumissions trouvées: {soumissions.count()}")
        if soumissions.exists():
            print("   Dates des soumissions:")
            for soum in soumissions[:5]:  # Afficher les 5 premières
                print(f"     - {soum.date} (ID: {soum.id})")
        else:
            print("   [ATTENTION] Aucune soumission trouvee pour cette matiere")
        
        # 2. Récupérer toutes les présences de l'élève pour cette matière
        print(f"\n5. Récupération des présences de l'élève pour la matière {matiere.nom}")
        presences_all = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            matiere=matiere
        ).order_by('-date')
        
        print(f"   Nombre total de présences trouvées: {presences_all.count()}")
        if presences_all.exists():
            print("   Détails des présences:")
            for pres in presences_all[:10]:  # Afficher les 10 premières
                print(f"     - Date: {pres.date}, Statut: {pres.statut}, Matière ID: {pres.matiere.id if pres.matiere else 'NULL'}")
        else:
            print("   [ATTENTION] Aucune presence trouvee pour cette matiere")
        
        # 3. Filtrer par dates de soumissions
        if soumissions.exists():
            dates_soumissions = list(soumissions.values_list('date', flat=True).distinct())
            print(f"\n6. Filtrage par dates de soumissions ({len(dates_soumissions)} dates)")
            presences_filtrees = presences_all.filter(date__in=dates_soumissions)
            print(f"   Nombre de présences après filtrage: {presences_filtrees.count()}")
            
            if presences_filtrees.exists():
                print("   Présences filtrées:")
                for pres in presences_filtrees[:10]:
                    print(f"     - Date: {pres.date}, Statut: {pres.statut}")
            else:
                print("   [ATTENTION] Aucune presence trouvee apres filtrage par dates de soumissions")
        else:
            print(f"\n6. Pas de filtrage par dates (aucune soumission)")
            presences_filtrees = Presence.objects.none()
        
        # 4. Calculer les statistiques
        print(f"\n7. Statistiques pour la matière {matiere.nom}")
        total = presences_filtrees.count() if soumissions.exists() else presences_all.count()
        presents = (presences_filtrees if soumissions.exists() else presences_all).filter(statut='present').count()
        absents = (presences_filtrees if soumissions.exists() else presences_all).filter(statut__in=['absent', 'absent_justifie']).count()
        retards = (presences_filtrees if soumissions.exists() else presences_all).filter(statut='retard').count()
        
        print(f"   Total: {total}")
        print(f"   Présents: {presents}")
        print(f"   Absents: {absents}")
        print(f"   Retards: {retards}")
        if total > 0:
            taux = round((presents / total * 100), 2)
            print(f"   Taux de présence: {taux}%")
    
    print(f"\n{'=' * 80}")
    print("TEST TERMINÉ")
    print(f"{'=' * 80}")

if __name__ == '__main__':
    test_presences_eleve()

