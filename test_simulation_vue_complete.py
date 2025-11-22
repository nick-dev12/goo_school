"""
Script pour simuler exactement la vue detail_eleve_enseignant
et vérifier la structure des données passées au template
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
from school_admin.model.affectation_model import AffectationProfesseur

def test_simulation_vue():
    """Simulation exacte de la vue"""
    
    print("=" * 80)
    print("SIMULATION COMPLETE DE LA VUE detail_eleve_enseignant")
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
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
    
    print(f"   Eleve: {eleve.nom} {eleve.prenom}")
    print(f"   Classe: {classe.nom}")
    print(f"   Professeur: {professeur.nom_complet}")
    print(f"   Est secondaire: {est_secondaire}")
    
    # Récupérer les affectations
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    
    # Construire matieres_list
    matieres_list = []
    for aff in affectations:
        matiere_aff = aff.matiere if aff.matiere else professeur.matiere_principale
        if matiere_aff and matiere_aff not in matieres_list:
            matieres_list.append(matiere_aff)
    
    if not matieres_list and professeur.matiere_principale:
        matieres_list.append(professeur.matiere_principale)
    
    print(f"\n2. Matieres list: {[m.nom for m in matieres_list]}")
    
    # Déterminer matiere_selectionnee
    matiere_selectionnee = None
    try:
        matiere_selectionnee = Matiere.objects.get(id=int(matiere_id), etablissement=etablissement)
        affectation_matiere = affectations.filter(matiere=matiere_selectionnee).first()
        if not affectation_matiere:
            print(f"   [ATTENTION] Matiere {matiere_id} ne correspond pas à une affectation")
            matiere_selectionnee = None
        elif matiere_selectionnee not in matieres_list:
            matieres_list.append(matiere_selectionnee)
    except (Matiere.DoesNotExist, ValueError, TypeError):
        print(f"   [ERREUR] Matiere {matiere_id} non trouvee")
    
    if not matiere_selectionnee and matieres_list:
        matiere_selectionnee = matieres_list[0]
    
    if matiere_selectionnee and matiere_selectionnee not in matieres_list:
        matieres_list.append(matiere_selectionnee)
    
    print(f"   Matiere selectionnee: {matiere_selectionnee.nom if matiere_selectionnee else 'None'}")
    
    # LOGIQUE DE RECUPERATION DES PRESENCES (identique à la vue)
    today = date.today()
    if today.month >= 9:
        debut_annee = date(today.year, 9, 1)
        fin_annee = date(today.year + 1, 6, 30)
    else:
        debut_annee = date(today.year - 1, 9, 1)
        fin_annee = date(today.year, 6, 30)
    
    periode_filtree = 'annee'  # Par défaut
    
    presences_par_matiere = {}
    mois_disponibles_par_matiere = {}
    
    print(f"\n3. Traitement des matieres pour les presences")
    for matiere in matieres_list:
        print(f"   --- Traitement: {matiere.nom} (ID: {matiere.id}) ---")
        
        filters_base = {
            'eleve': eleve,
            'classe': classe,
        }
        
        if est_secondaire:
            if matiere:
                filters_base['matiere'] = matiere
            else:
                print(f"     [SKIP] Pas de matiere pour secondaire")
                continue
        else:
            filters_base['matiere__isnull'] = True
        
        # Appliquer le filtre de période
        if est_secondaire and matiere:
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=debut_annee,
                date__lte=fin_annee
            ).select_related('matiere', 'eleve').order_by('-date')
        elif not est_secondaire:
            presences = Presence.objects.filter(
                **filters_base,
                date__gte=debut_annee,
                date__lte=fin_annee
            ).select_related('eleve').order_by('-date')
        else:
            presences = Presence.objects.none()
        
        # Statistiques
        total_presences = presences.count()
        nombre_presents = presences.filter(statut='present').count()
        nombre_absences = presences.filter(statut='absent').count()
        nombre_absences_justifiees = presences.filter(statut='absent_justifie').count()
        nombre_retards = presences.filter(statut='retard').count()
        taux_presence = round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0
        
        print(f"     Total: {total_presences}, Presents: {nombre_presents}, Absents: {nombre_absences}")
        
        # Extraire les mois
        mois_avec_presences = set()
        presences_list = list(presences[:100])
        for presence in presences_list:
            mois_avec_presences.add((presence.date.year, presence.date.month))
        
        noms_mois = [
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        mois_disponibles = []
        for annee, mois in sorted(mois_avec_presences, reverse=True):
            mois_disponibles.append({
                'annee': annee,
                'mois': mois,
                'nom': noms_mois[mois - 1],
                'annee_mois': f"{annee}-{mois:02d}"
            })
        
        # Convertir en liste
        presences_list_final = list(presences)
        
        # Stocker dans presences_par_matiere
        presences_par_matiere[matiere.id] = {
            'matiere': matiere,
            'presences': presences_list_final,
            'total_presences': total_presences,
            'nombre_absences': nombre_absences,
            'nombre_absences_justifiees': nombre_absences_justifiees,
            'nombre_retards': nombre_retards,
            'nombre_presents': nombre_presents,
            'taux_presence': taux_presence,
            'mois_disponibles': mois_disponibles,
            'periode_filtree': periode_filtree,
        }
        mois_disponibles_par_matiere[matiere.id] = mois_disponibles
    
    print(f"\n4. Verification de presences_par_matiere")
    print(f"   Clés: {list(presences_par_matiere.keys())}")
    print(f"   Matiere selectionnee ID: {matiere_selectionnee.id if matiere_selectionnee else 'None'}")
    
    if matiere_selectionnee and matiere_selectionnee.id in presences_par_matiere:
        presences_data = presences_par_matiere[matiere_selectionnee.id]
        print(f"   [OK] Donnees trouvees pour matiere {matiere_selectionnee.id}")
        print(f"   - Total presences: {presences_data['total_presences']}")
        print(f"   - Nombre de presences dans la liste: {len(presences_data['presences'])}")
        print(f"   - Type de presences: {type(presences_data['presences'])}")
        if presences_data['presences']:
            print(f"   - Premier element: {presences_data['presences'][0]}")
            print(f"   - Premier element type: {type(presences_data['presences'][0])}")
    else:
        print(f"   [ERREUR] Matiere selectionnee NON trouvee dans presences_par_matiere!")
        if presences_par_matiere:
            print(f"   Matieres disponibles: {list(presences_par_matiere.keys())}")
    
    print(f"\n" + "=" * 80)
    print("SIMULATION TERMINE")
    print("=" * 80)

if __name__ == '__main__':
    test_simulation_vue()


