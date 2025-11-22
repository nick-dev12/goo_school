"""
Script de débogage pour vérifier la logique de récupération des présences dans detail_eleve_enseignant
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur
from school_admin.model.affectation_model import AffectationProfesseur

def test_debug_presences():
    """Test de débogage pour la récupération des présences"""
    
    print("=" * 80)
    print("DEBUG - RECUPERATION DES PRESENCES POUR DETAIL ELEVE")
    print("=" * 80)
    
    # Données de test
    eleve_id = 2230
    classe_id = 110
    professeur_id = 119
    matiere_id = 86
    
    print(f"\n1. Recuperation de l'eleve ID: {eleve_id}")
    try:
        eleve = Eleve.objects.get(id=eleve_id, actif=True)
        print(f"   [OK] Eleve trouve: {eleve.nom} {eleve.prenom}")
    except Eleve.DoesNotExist:
        print(f"   [ERREUR] Eleve {eleve_id} non trouve")
        return
    
    print(f"\n2. Recuperation de la classe ID: {classe_id}")
    try:
        classe = Classe.objects.get(id=classe_id)
        print(f"   [OK] Classe trouvee: {classe.nom}")
        etablissement = classe.etablissement
        est_secondaire = etablissement.type_etablissement in ['lycee', 'college', 'college_lycee']
        print(f"   - Etablissement: {etablissement.nom}")
        print(f"   - Type: {etablissement.type_etablissement}")
        print(f"   - Est secondaire: {est_secondaire}")
    except Classe.DoesNotExist:
        print(f"   [ERREUR] Classe {classe_id} non trouvee")
        return
    
    print(f"\n3. Recuperation du professeur ID: {professeur_id}")
    try:
        professeur = Professeur.objects.get(id=professeur_id)
        print(f"   [OK] Professeur trouve: {professeur.nom_complet}")
    except Professeur.DoesNotExist:
        print(f"   [ERREUR] Professeur {professeur_id} non trouve")
        return
    
    print(f"\n4. Recuperation de la matiere ID: {matiere_id}")
    try:
        matiere = Matiere.objects.get(id=matiere_id, etablissement=etablissement)
        print(f"   [OK] Matiere trouvee: {matiere.nom}")
    except Matiere.DoesNotExist:
        print(f"   [ERREUR] Matiere {matiere_id} non trouvee")
        return
    
    print(f"\n5. Verification des affectations")
    affectations = AffectationProfesseur.objects.filter(
        professeur=professeur,
        classe=classe,
        actif=True
    )
    print(f"   Nombre d'affectations trouvees: {affectations.count()}")
    for aff in affectations:
        print(f"     - Affectation ID: {aff.id}, Matiere: {aff.matiere.nom if aff.matiere else 'N/A'}")
    
    print(f"\n6. TEST DE LA LOGIQUE DE RECUPERATION (comme dans detail_eleve_enseignant)")
    print(f"   Filtres utilises:")
    filters_presence = {
        'eleve': eleve,
        'classe': classe,
        'numero_appel': 1
    }
    
    if est_secondaire:
        if matiere:
            filters_presence['matiere'] = matiere
            print(f"     - eleve: {eleve.id}")
            print(f"     - classe: {classe.id}")
            print(f"     - numero_appel: 1")
            print(f"     - matiere: {matiere.id} ({matiere.nom})")
        else:
            print(f"     [ERREUR] Matiere manquante pour etablissement secondaire")
            return
    else:
        filters_presence['matiere__isnull'] = True
        print(f"     - matiere__isnull: True")
    
    print(f"\n7. Recuperation des presences avec ces filtres")
    presences_all = Presence.objects.filter(**filters_presence).select_related('matiere', 'eleve').order_by('-date')
    
    print(f"   Nombre de presences trouvees: {presences_all.count()}")
    
    if presences_all.exists():
        print(f"   Details des presences:")
        for pres in presences_all[:10]:
            print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}, Matiere ID: {pres.matiere.id if pres.matiere else 'NULL'}")
    else:
        print(f"   [ATTENTION] Aucune presence trouvee avec ces filtres!")
        print(f"\n   Verification alternative - toutes les presences de l'eleve:")
        presences_eleve_all = Presence.objects.filter(eleve=eleve, classe=classe).order_by('-date')
        print(f"   Nombre total de presences de l'eleve dans cette classe: {presences_eleve_all.count()}")
        if presences_eleve_all.exists():
            print(f"   Details:")
            for pres in presences_eleve_all[:10]:
                print(f"     - ID: {pres.id}, Date: {pres.date}, Statut: {pres.statut}, Matiere ID: {pres.matiere.id if pres.matiere else 'NULL'}, Numero appel: {pres.numero_appel}")
    
    print(f"\n8. Verification du numero_appel")
    presences_sans_numero = Presence.objects.filter(
        eleve=eleve,
        classe=classe,
        matiere=matiere
    ).exclude(numero_appel=1)
    print(f"   Presences avec numero_appel != 1: {presences_sans_numero.count()}")
    if presences_sans_numero.exists():
        for pres in presences_sans_numero[:5]:
            print(f"     - ID: {pres.id}, Date: {pres.date}, Numero appel: {pres.numero_appel}")
    
    print(f"\n" + "=" * 80)
    print("DEBUG TERMINE")
    print("=" * 80)

if __name__ == '__main__':
    test_debug_presences()


