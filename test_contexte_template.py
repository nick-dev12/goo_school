"""
Script pour tester exactement ce qui est passé au template
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

def test_contexte_template():
    """Test du contexte exact passé au template"""
    
    print("=" * 80)
    print("TEST DU CONTEXTE TEMPLATE")
    print("=" * 80)
    
    # Données de test
    eleve_id = 2230
    classe_id = 110
    professeur_id = 119
    matiere_id = 89  # Histoire-Géographie
    
    eleve = Eleve.objects.get(id=eleve_id, actif=True)
    classe = Classe.objects.get(id=classe_id)
    professeur = Professeur.objects.get(id=professeur_id)
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
    
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
    
    print(f"\n1. Matiere selectionnee: {matiere_selectionnee.nom if matiere_selectionnee else 'None'} (ID: {matiere_selectionnee.id if matiere_selectionnee else 'None'})")
    
    # LOGIQUE DE RECUPERATION DES PRESENCES
    today = date.today()
    if today.month >= 9:
        debut_annee = date(today.year, 9, 1)
        fin_annee = date(today.year + 1, 6, 30)
    else:
        debut_annee = date(today.year - 1, 9, 1)
        fin_annee = date(today.year, 6, 30)
    
    periode_filtree = 'annee'  # Par défaut
    
    presences_par_matiere = {}
    
    for matiere in matieres_list:
        filters_base = {
            'eleve': eleve,
            'classe': classe,
        }
        
        if est_secondaire:
            if matiere:
                filters_base['matiere'] = matiere
            else:
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
    
    print(f"\n2. Presences par matiere keys: {list(presences_par_matiere.keys())}")
    
    # Simuler l'accès du template avec get_item
    from school_admin.templatetags.notes_tags import get_item
    
    if matiere_selectionnee and matiere_selectionnee.id in presences_par_matiere:
        presences_data = get_item(presences_par_matiere, matiere_selectionnee.id)
        print(f"\n3. Test avec get_item:")
        print(f"   presences_data: {presences_data}")
        if presences_data:
            print(f"   - Type: {type(presences_data)}")
            print(f"   - Total presences: {presences_data.get('total_presences', 'NOT FOUND')}")
            print(f"   - Nombre presents: {presences_data.get('nombre_presents', 'NOT FOUND')}")
            print(f"   - Nombre absences: {presences_data.get('nombre_absences', 'NOT FOUND')}")
            print(f"   - Presences list length: {len(presences_data.get('presences', []))}")
            print(f"   - Periode filtree: {presences_data.get('periode_filtree', 'NOT FOUND')}")
        else:
            print(f"   [ERREUR] presences_data est None!")
    else:
        print(f"\n3. [ERREUR] Matiere selectionnee {matiere_selectionnee.id if matiere_selectionnee else 'None'} pas dans presences_par_matiere!")
        print(f"   Keys disponibles: {list(presences_par_matiere.keys())}")
    
    # Vérifier l'accès direct
    if matiere_selectionnee and matiere_selectionnee.id in presences_par_matiere:
        presences_data_direct = presences_par_matiere[matiere_selectionnee.id]
        print(f"\n4. Test acces direct:")
        print(f"   - Total presences: {presences_data_direct['total_presences']}")
        print(f"   - Nombre presents: {presences_data_direct['nombre_presents']}")
        print(f"   - Nombre absences: {presences_data_direct['nombre_absences']}")
        print(f"   - Presences list length: {len(presences_data_direct['presences'])}")
    
    print(f"\n" + "=" * 80)
    print("TEST TERMINE")
    print("=" * 80)

if __name__ == '__main__':
    test_contexte_template()


