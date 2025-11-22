"""
Script pour simuler exactement ce que fait la vue detail_eleve_enseignant
"""
import os
import django
from datetime import date
import calendar

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur

def simuler_vue_detail():
    """Simule exactement la logique de detail_eleve_enseignant"""
    
    print("=" * 80)
    print("SIMULATION DE LA VUE detail_eleve_enseignant")
    print("=" * 80)
    
    # Données
    eleve_id = 2230
    classe_id = 110
    professeur_id = 119
    matiere_id = 86
    
    eleve = Eleve.objects.get(id=eleve_id, actif=True)
    classe = Classe.objects.get(id=classe_id)
    professeur = Professeur.objects.get(id=professeur_id)
    matiere = Matiere.objects.get(id=matiere_id, etablissement=classe.etablissement)
    
    etablissement = classe.etablissement
    est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
    today = date.today()
    
    print(f"\nEleve: {eleve.nom} {eleve.prenom}")
    print(f"Classe: {classe.nom}")
    print(f"Matiere: {matiere.nom}")
    print(f"Est secondaire: {est_secondaire}")
    print(f"Date aujourd'hui: {today}")
    
    # LOGIQUE EXACTE DE LA VUE
    filters_presence = {
        'eleve': eleve,
        'classe': classe,
        'numero_appel': 1
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
    
    print(f"\nFiltres utilises: {filters_presence}")
    print(f"Nombre de presences trouvees: {presences_all.count()}")
    
    if presences_all.exists():
        print(f"\nDetails des presences:")
        for pres in presences_all:
            print(f"  - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}")
        
        # Extraire les mois
        mois_avec_presences = set()
        presences_list = list(presences_all[:100])
        for presence in presences_list:
            mois_avec_presences.add((presence.date.year, presence.date.month))
        
        print(f"\nMois avec presences: {mois_avec_presences}")
        
        # Créer la liste des mois disponibles
        noms_mois = [
            'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
        ]
        mois_disponibles = []
        for annee, mois in sorted(mois_avec_presences, reverse=True):
            mois_disponibles.append({
                'annee': annee,
                'mois': mois,
                'nom': noms_mois[mois - 1],
                'annee_mois': f"{annee}-{mois:02d}"
            })
        
        print(f"Mois disponibles: {mois_disponibles}")
        
        # Déterminer le mois sélectionné
        if mois_disponibles:
            annee_sel = mois_disponibles[0]['annee']
            mois_sel = mois_disponibles[0]['mois']
        elif presences_all.exists():
            premiere_presence = presences_all.first()
            annee_sel = premiere_presence.date.year
            mois_sel = premiere_presence.date.month
            mois_disponibles.append({
                'annee': annee_sel,
                'mois': mois_sel,
                'nom': noms_mois[mois_sel - 1],
                'annee_mois': f"{annee_sel}-{mois_sel:02d}"
            })
        else:
            annee_sel = today.year
            mois_sel = today.month
        
        print(f"\nMois selectionne: {annee_sel}-{mois_sel:02d}")
        
        # Filtrer les présences pour le mois sélectionné
        premier_jour = date(annee_sel, mois_sel, 1)
        dernier_jour = date(annee_sel, mois_sel, calendar.monthrange(annee_sel, mois_sel)[1])
        
        print(f"Plage du mois: {premier_jour} a {dernier_jour}")
        
        presences_mois = presences_all.filter(
            date__gte=premier_jour,
            date__lte=dernier_jour
        ).order_by('-date')
        
        print(f"Presences du mois selectionne: {presences_mois.count()}")
        for pres in presences_mois:
            print(f"  - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}")
        
        # Statistiques
        total_presences = presences_all.count()
        nombre_presents = presences_all.filter(statut='present').count()
        nombre_absences = presences_all.filter(statut__in=['absent', 'absent_justifie']).count()
        nombre_retards = presences_all.filter(statut='retard').count()
        
        print(f"\nStatistiques globales:")
        print(f"  Total: {total_presences}")
        print(f"  Presents: {nombre_presents}")
        print(f"  Absents: {nombre_absences}")
        print(f"  Retards: {nombre_retards}")
        
        # Stocker dans presences_par_matiere
        presences_par_matiere = {
            matiere.id: {
                'matiere': matiere,
                'presences': presences_mois,
                'presences_all': presences_all,
                'total_presences': total_presences,
                'nombre_absences': nombre_absences,
                'nombre_retards': nombre_retards,
                'nombre_presents': nombre_presents,
                'taux_presence': round((nombre_presents / total_presences * 100), 2) if total_presences > 0 else 0,
                'mois_disponibles': mois_disponibles,
            }
        }
        
        print(f"\nDonnees stockees dans presences_par_matiere[{matiere.id}]:")
        print(f"  - Total presences: {presences_par_matiere[matiere.id]['total_presences']}")
        print(f"  - Presences du mois: {presences_par_matiere[matiere.id]['presences'].count()}")
        print(f"  - Toutes les presences: {presences_par_matiere[matiere.id]['presences_all'].count()}")
        print(f"  - Mois disponibles: {len(presences_par_matiere[matiere.id]['mois_disponibles'])}")
    
    print(f"\n" + "=" * 80)
    print("SIMULATION TERMINEE")
    print("=" * 80)

if __name__ == '__main__':
    simuler_vue_detail()


