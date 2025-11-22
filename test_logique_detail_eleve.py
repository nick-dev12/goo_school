"""
Script pour tester la logique exacte de detail_eleve_enseignant
et vérifier si les données sont bien récupérées
"""
import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur
from school_admin.model.affectation_model import AffectationProfesseur

def test_logique_detail_eleve():
    """Test de la logique exacte de detail_eleve_enseignant"""
    
    print("=" * 80)
    print("TEST DE LA LOGIQUE detail_eleve_enseignant")
    print("=" * 80)
    
    # Données de test
    eleve_id = 2230
    classe_id = 110
    professeur_id = 119
    matiere_id = 86  # Anglais
    
    print(f"\n1. Recuperation des objets")
    eleve = Eleve.objects.get(id=eleve_id, actif=True)
    classe = Classe.objects.get(id=classe_id)
    professeur = Professeur.objects.get(id=professeur_id)
    matiere = Matiere.objects.get(id=matiere_id, etablissement=classe.etablissement)
    
    print(f"   Eleve: {eleve.nom} {eleve.prenom}")
    print(f"   Classe: {classe.nom}")
    print(f"   Professeur: {professeur.nom_complet}")
    print(f"   Matiere: {matiere.nom}")
    
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
    print(f"   Est secondaire: {est_secondaire}")
    
    print(f"\n2. Recuperation des affectations")
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    print(f"   Nombre d'affectations: {affectations.count()}")
    
    print(f"\n3. Construction de matieres_list")
    matieres_list = []
    for aff in affectations:
        matiere_aff = aff.matiere if aff.matiere else professeur.matiere_principale
        if matiere_aff and matiere_aff not in matieres_list:
            matieres_list.append(matiere_aff)
            print(f"   - Matiere ajoutee: {matiere_aff.nom} (ID: {matiere_aff.id})")
    
    if not matieres_list and professeur.matiere_principale:
        matieres_list.append(professeur.matiere_principale)
        print(f"   - Matiere principale ajoutee: {professeur.matiere_principale.nom}")
    
    print(f"\n4. Verification de la matiere selectionnee dans matieres_list")
    matiere_selectionnee = matiere
    if matiere_selectionnee not in matieres_list:
        matieres_list.append(matiere_selectionnee)
        print(f"   [ATTENTION] Matiere selectionnee ajoutee a matieres_list")
    else:
        print(f"   [OK] Matiere selectionnee deja dans matieres_list")
    
    print(f"\n5. TEST DE LA LOGIQUE DE RECUPERATION DES PRESENCES")
    print(f"   Matieres a traiter: {[m.nom for m in matieres_list]}")
    
    presences_par_matiere = {}
    
    for matiere in matieres_list:
        print(f"\n   --- Traitement de la matiere: {matiere.nom} (ID: {matiere.id}) ---")
        
        # LOGIQUE EXACTE DE LA VUE
        filters_presence = {
            'eleve': eleve,
            'classe': classe,
        }
        
        if est_secondaire:
            if matiere:
                filters_presence['matiere'] = matiere
                presences_all = Presence.objects.filter(**filters_presence).select_related('matiere', 'eleve').order_by('-date')
            else:
                presences_all = Presence.objects.none()
        else:
            filters_presence['matiere__isnull'] = True
            presences_all = Presence.objects.filter(**filters_presence).select_related('eleve').order_by('-date')
        
        print(f"   Filtres utilises: {filters_presence}")
        print(f"   Nombre de presences trouvees: {presences_all.count()}")
        
        if presences_all.exists():
            print(f"   Details des presences:")
            for pres in presences_all[:10]:
                print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}, Matiere ID: {pres.matiere.id if pres.matiere else 'NULL'}")
        
        # Calculer les statistiques
        total_presences = presences_all.count()
        nombre_presents = presences_all.filter(statut='present').count()
        nombre_absences = presences_all.filter(statut__in=['absent', 'absent_justifie']).count()
        nombre_retards = presences_all.filter(statut='retard').count()
        taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
        
        print(f"   Statistiques:")
        print(f"     - Total: {total_presences}")
        print(f"     - Presents: {nombre_presents}")
        print(f"     - Absents: {nombre_absences}")
        print(f"     - Retards: {nombre_retards}")
        print(f"     - Taux: {taux_presence}%")
        
        # Stocker dans presences_par_matiere
        presences_par_matiere[matiere.id] = {
            'matiere': matiere,
            'presences': presences_all,  # Toutes les presences
            'presences_all': presences_all,
            'total_presences': total_presences,
            'nombre_absences': nombre_absences,
            'nombre_retards': nombre_retards,
            'nombre_presents': nombre_presents,
            'taux_presence': taux_presence,
        }
    
    print(f"\n6. VERIFICATION DE presences_par_matiere")
    print(f"   Clés dans presences_par_matiere: {list(presences_par_matiere.keys())}")
    print(f"   Matiere selectionnee ID: {matiere_selectionnee.id}")
    
    if matiere_selectionnee.id in presences_par_matiere:
        print(f"   [OK] Matiere selectionnee trouvee dans presences_par_matiere")
        presences_data = presences_par_matiere[matiere_selectionnee.id]
        print(f"   Donnees pour cette matiere:")
        print(f"     - Total presences: {presences_data['total_presences']}")
        print(f"     - Presents: {presences_data['nombre_presents']}")
        print(f"     - Absents: {presences_data['nombre_absences']}")
        print(f"     - Retards: {presences_data['nombre_retards']}")
        print(f"     - Taux: {presences_data['taux_presence']}%")
        print(f"     - Nombre de presences dans queryset: {presences_data['presences'].count()}")
        
        # Vérifier si on peut itérer sur les présences
        print(f"   Test d'iteration sur les presences:")
        try:
            count = 0
            for presence in presences_data['presences']:
                count += 1
                print(f"     - Presence {count}: ID={presence.id}, Date={presence.date}, Statut={presence.statut}")
                if count >= 5:
                    break
            print(f"   [OK] Iteration reussie, {count} presences trouvees")
        except Exception as e:
            print(f"   [ERREUR] Probleme lors de l'iteration: {str(e)}")
    else:
        print(f"   [ERREUR] Matiere selectionnee NON trouvee dans presences_par_matiere!")
        print(f"   Matieres disponibles: {list(presences_par_matiere.keys())}")
    
    print(f"\n7. VERIFICATION DIRECTE DANS LA BASE")
    presences_directes = Presence.objects.filter(
        eleve=eleve,
        classe=classe,
        matiere=matiere
    )
    print(f"   Nombre de presences directes (eleve + classe + matiere): {presences_directes.count()}")
    for pres in presences_directes:
        print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}, Numero appel: {pres.numero_appel}")
    
    print(f"\n" + "=" * 80)
    print("TEST TERMINE")
    print("=" * 80)

if __name__ == '__main__':
    test_logique_detail_eleve()


