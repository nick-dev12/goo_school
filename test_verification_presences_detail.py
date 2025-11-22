"""
Script pour vérifier la récupération des présences dans detail_eleve_enseignant
"""
import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur

def test_recuperation_presences():
    """Test de la récupération des présences"""
    
    print("=" * 80)
    print("TEST DE RECUPERATION DES PRESENCES")
    print("=" * 80)
    
    # Données de test
    eleve_id = 2230
    classe_id = 110
    matiere_id = 86  # Anglais
    
    print(f"\n1. Recuperation des objets")
    eleve = Eleve.objects.get(id=eleve_id, actif=True)
    classe = Classe.objects.get(id=classe_id)
    matiere = Matiere.objects.get(id=matiere_id, etablissement=classe.etablissement)
    
    print(f"   Eleve: {eleve.nom} {eleve.prenom}")
    print(f"   Classe: {classe.nom}")
    print(f"   Matiere: {matiere.nom}")
    
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
    print(f"   Est secondaire: {est_secondaire}")
    
    # LOGIQUE IDENTIQUE À LA VUE
    today = date.today()
    if today.month >= 9:
        debut_annee = date(today.year, 9, 1)
        fin_annee = date(today.year + 1, 6, 30)
    else:
        debut_annee = date(today.year - 1, 9, 1)
        fin_annee = date(today.year, 6, 30)
    
    periode_filtree = 'annee'  # Par défaut
    
    # Filtres de base
    filters_base = {
        'eleve': eleve,
        'classe': classe,
    }
    
    # Ajouter le filtre matière
    if est_secondaire:
        if matiere:
            filters_base['matiere'] = matiere
        else:
            print("   [ERREUR] Etablissement secondaire sans matiere!")
            return
    else:
        filters_base['matiere__isnull'] = True
    
    print(f"\n2. Filtres utilises: {filters_base}")
    
    # Appliquer le filtre de période
    if est_secondaire and matiere:
        if periode_filtree == '30jours':
            date_debut = today - timedelta(days=30)
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=date_debut
            ).select_related('matiere', 'eleve').order_by('-date')
        elif periode_filtree == '7jours':
            date_debut = today - timedelta(days=7)
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=date_debut
            ).select_related('matiere', 'eleve').order_by('-date')
        else:  # annee
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=debut_annee,
                date__lte=fin_annee
            ).select_related('matiere', 'eleve').order_by('-date')
    elif not est_secondaire:
        if periode_filtree == '30jours':
            date_debut = today - timedelta(days=30)
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=date_debut
            ).select_related('eleve').order_by('-date')
        elif periode_filtree == '7jours':
            date_debut = today - timedelta(days=7)
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=date_debut
            ).select_related('eleve').order_by('-date')
        else:  # annee
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=debut_annee,
                date__lte=fin_annee
            ).select_related('eleve').order_by('-date')
    else:
        presences = Presence.objects.none()
    
    print(f"\n3. Resultats de la requete")
    print(f"   Nombre de presences trouvees: {presences.count()}")
    
    if presences.exists():
        print(f"   Details des presences:")
        for pres in presences:
            print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}, Matiere ID: {pres.matiere.id if pres.matiere else 'NULL'}")
        
        # Statistiques
        total_presences = presences.count()
        nombre_presents = presences.filter(statut='present').count()
        nombre_absences = presences.filter(statut='absent').count()
        nombre_absences_justifiees = presences.filter(statut='absent_justifie').count()
        nombre_retards = presences.filter(statut='retard').count()
        taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
        
        print(f"\n4. Statistiques:")
        print(f"   - Total: {total_presences}")
        print(f"   - Presents: {nombre_presents}")
        print(f"   - Absents: {nombre_absences}")
        print(f"   - Absents justifies: {nombre_absences_justifiees}")
        print(f"   - Retards: {nombre_retards}")
        print(f"   - Taux: {taux_presence}%")
        
        # Convertir en liste
        presences_list = list(presences)
        print(f"\n5. Conversion en liste:")
        print(f"   - Nombre d'elements dans la liste: {len(presences_list)}")
        print(f"   - Type: {type(presences_list)}")
    else:
        print(f"   [ATTENTION] Aucune presence trouvee!")
        print(f"   Verification directe dans la base:")
        presences_directes = Presence.objects.filter(
            eleve=eleve,
            classe=classe,
            matiere=matiere
        )
        print(f"   - Nombre sans filtre de date: {presences_directes.count()}")
        for pres in presences_directes:
            print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}")
    
    print(f"\n" + "=" * 80)
    print("TEST TERMINE")
    print("=" * 80)

if __name__ == '__main__':
    test_recuperation_presences()


