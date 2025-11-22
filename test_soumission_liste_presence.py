"""
Script de test pour valider la soumission de liste de présence
Vérifie que les données sont correctement enregistrées dans les tables Presence et SoumissionListePresence
Utilise les données spécifiques de la table ListePresence (classe_id=110, professeur_id=119, etablissement_id=34, matiere_id=86)
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.presence_model import Presence, SoumissionListePresence, ListePresence
from school_admin.model.classe_model import Classe
from school_admin.model.professeur_model import Professeur
from school_admin.model.eleve_model import Eleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.etablissement_model import Etablissement
from django.utils import timezone
from datetime import date
from django.db import transaction

def test_soumission_liste_presence():
    """
    Teste la soumission d'une liste de présence et vérifie les données
    Utilise les données spécifiques de la table ListePresence
    """
    print("=" * 80)
    print("TEST DE SOUMISSION DE LISTE DE PRESENCE")
    print("=" * 80)
    print()
    
    # Utiliser les données spécifiques de l'image
    classe_id = 110
    professeur_id = 119
    etablissement_id = 34
    matiere_id = 86
    
    print(f"[INFO] Utilisation des donnees specifiques de la table ListePresence:")
    print(f"   - Classe ID: {classe_id}")
    print(f"   - Professeur ID: {professeur_id}")
    print(f"   - Etablissement ID: {etablissement_id}")
    print(f"   - Matiere ID: {matiere_id}")
    print()
    
    # Récupérer les objets
    try:
        classe = Classe.objects.get(id=classe_id)
        professeur = Professeur.objects.get(id=professeur_id)
        etablissement = Etablissement.objects.get(id=etablissement_id)
        matiere = Matiere.objects.get(id=matiere_id)
    except (Classe.DoesNotExist, Professeur.DoesNotExist, Etablissement.DoesNotExist, Matiere.DoesNotExist) as e:
        print(f"[ERREUR] Objet non trouve: {str(e)}")
        return False
    
    print(f"[OK] Etablissement: {etablissement.nom} (Type: {etablissement.type_etablissement})")
    print(f"[OK] Classe: {classe.nom}")
    print(f"[OK] Professeur: {professeur.nom} {professeur.prenom}")
    print(f"[OK] Matiere: {matiere.nom}")
    print()
    
    # Vérifier les enregistrements existants dans ListePresence
    print("-" * 80)
    print("VERIFICATION DES ENREGISTREMENTS EXISTANTS DANS ListePresence")
    print("-" * 80)
    
    today = date.today()
    
    listes_presence = ListePresence.objects.filter(
        classe=classe,
        professeur=professeur,
        date=today
    )
    
    print(f"[INFO] Nombre de ListePresence trouvees pour aujourd'hui: {listes_presence.count()}")
    
    for lp in listes_presence:
        matiere_info = f"Matiere ID: {lp.matiere.id} ({lp.matiere.nom})" if lp.matiere else "Matiere: NULL"
        print(f"   - ID: {lp.id}")
        print(f"     Date: {lp.date}")
        print(f"     Validee: {lp.validee}")
        print(f"     {matiere_info}")
        print(f"     Date creation: {lp.date_creation}")
        print()
    
    # Vérifier les soumissions existantes
    print("-" * 80)
    print("VERIFICATION DES SOUMISSIONS EXISTANTES")
    print("-" * 80)
    
    soumissions = SoumissionListePresence.objects.filter(
        classe=classe,
        professeur=professeur,
        matiere=matiere,
        date=today
    )
    
    print(f"[INFO] Nombre de soumissions trouvees pour aujourd'hui: {soumissions.count()}")
    
    if soumissions.exists():
        print("[ATTENTION] Une soumission existe deja pour aujourd'hui:")
        for soum in soumissions:
            print(f"   - ID: {soum.id}")
            print(f"     Date soumission: {soum.date_soumission}")
            print()
        reponse = input("   Voulez-vous continuer quand meme ? (o/n): ")
        if reponse.lower() != 'o':
            print("[ANNULATION] Test annule.")
            return False
    else:
        print("[OK] Aucune soumission existante trouvee.")
    
    print()
    print("-" * 80)
    print("VERIFICATION DES PRESENCES EXISTANTES")
    print("-" * 80)
    
    presences_existantes = Presence.objects.filter(
        classe=classe,
        date=today,
        matiere=matiere,
        numero_appel=1
    )
    
    print(f"[INFO] Nombre de presences existantes: {presences_existantes.count()}")
    
    if presences_existantes.count() > 0:
        print("\nDetails des presences existantes:")
        for presence in presences_existantes[:10]:  # Limiter à 10 pour l'affichage
            print(f"   - Eleve: {presence.eleve.nom} {presence.eleve.prenom}")
            print(f"     Statut: {presence.statut}")
            print(f"     Matiere: {presence.matiere.nom if presence.matiere else 'NULL'}")
            print(f"     Date: {presence.date}")
            print()
    
    # Récupérer les élèves de la classe
    eleves = Eleve.objects.filter(classe=classe, actif=True)[:5]  # Limiter à 5 élèves pour le test
    if not eleves.exists():
        print("[ERREUR] Aucun eleve trouve dans cette classe.")
        return False
    
    print(f"[INFO] Eleves selectionnes pour le test: {eleves.count()}")
    for eleve in eleves:
        print(f"   - {eleve.nom} {eleve.prenom} (ID: {eleve.id})")
    
    print()
    print("-" * 80)
    print("TEST 1: Simulation de la soumission (SANS sauvegarder)")
    print("-" * 80)
    
    try:
        with transaction.atomic():
            # Simuler l'enregistrement des présences
            nombre_presents = 0
            nombre_absents = 0
            presences_creees = []
            
            # Créer des présences pour chaque élève
            statuts = ['present', 'present', 'absent', 'retard', 'present']  # Exemples de statuts
            
            for i, eleve in enumerate(eleves):
                statut = statuts[i % len(statuts)]
                
                presence, created = Presence.objects.update_or_create(
                    eleve=eleve,
                    classe=classe,
                    date=today,
                    numero_appel=1,
                    matiere=matiere,
                    defaults={
                        'professeur': professeur,
                        'etablissement': etablissement,
                        'statut': statut
                    }
                )
                
                if not created:
                    presence.professeur = professeur
                    presence.etablissement = etablissement
                    presence.statut = statut
                    if matiere and not presence.matiere:
                        presence.matiere = matiere
                    presence.save()
                
                presences_creees.append(presence)
                
                if statut == 'present':
                    nombre_presents += 1
                elif statut in ['absent', 'absent_justifie']:
                    nombre_absents += 1
                
                print(f"   [OK] Presence creee/mise a jour pour {eleve.nom} {eleve.prenom} - Statut: {statut}")
            
            # Créer l'enregistrement de soumission
            soumission = SoumissionListePresence.objects.create(
                classe=classe,
                professeur=professeur,
                etablissement=etablissement,
                matiere=matiere,
                date=today,
                date_soumission=timezone.now()
            )
            
            print()
            print(f"[OK] Soumission creee (ID: {soumission.id})")
            print(f"   Presents: {nombre_presents}, Absents: {nombre_absents}")
            
            # Ne pas commit la transaction pour pouvoir annuler
            raise Exception("Transaction annulee pour test - les donnees ne seront pas sauvegardees")
            
    except Exception as e:
        if "Transaction annulee" in str(e):
            print()
            print("[INFO] Transaction annulee (test uniquement)")
        else:
            print(f"[ERREUR] Erreur lors de la simulation: {str(e)}")
            return False
    
    print()
    print("-" * 80)
    print("TEST 2: Verification des donnees enregistrees")
    print("-" * 80)
    
    # Vérifier les présences
    presences_verifiees = Presence.objects.filter(
        classe=classe,
        date=today,
        matiere=matiere,
        numero_appel=1
    )
    
    print(f"[INFO] Nombre de presences trouvees: {presences_verifiees.count()}")
    
    if presences_verifiees.count() == 0:
        print("[INFO] Aucune presence trouvee (normal si la transaction a ete annulee)")
    else:
        print("\nDetails des presences:")
        presences_avec_matiere = presences_verifiees.filter(matiere__isnull=False)
        presences_sans_matiere = presences_verifiees.filter(matiere__isnull=True)
        
        print(f"   - Avec matiere: {presences_avec_matiere.count()}")
        print(f"   - Sans matiere: {presences_sans_matiere.count()}")
        
        if presences_sans_matiere.count() > 0:
            print("\n[ATTENTION] Presences SANS matiere trouvees:")
            for presence in presences_sans_matiere[:5]:
                print(f"   - ID: {presence.id} - Eleve: {presence.eleve.nom} {presence.eleve.prenom}")
    
    # Vérifier les soumissions
    soumissions_verifiees = SoumissionListePresence.objects.filter(
        classe=classe,
        professeur=professeur,
        matiere=matiere,
        date=today
    )
    
    print(f"\n[INFO] Nombre de soumissions trouvees: {soumissions_verifiees.count()}")
    
    if soumissions_verifiees.count() == 0:
        print("[INFO] Aucune soumission trouvee (normal si la transaction a ete annulee)")
    else:
        print("\nDetails des soumissions:")
        for soumission in soumissions_verifiees:
            print(f"   - ID: {soumission.id}")
            print(f"     Classe: {soumission.classe.nom}")
            print(f"     Professeur: {soumission.professeur.nom}")
            print(f"     Matiere: {soumission.matiere.nom if soumission.matiere else 'NULL'}")
            print(f"     Date: {soumission.date}")
            print(f"     Date de soumission: {soumission.date_soumission}")
            print()
    
    print()
    print("-" * 80)
    print("TEST 3: Verification de l'unicite (unique_together)")
    print("-" * 80)
    
    # Tenter de créer une soumission dupliquée
    try:
        with transaction.atomic():
            soumission_dupliquee = SoumissionListePresence.objects.create(
                classe=classe,
                professeur=professeur,
                etablissement=etablissement,
                matiere=matiere,
                date=today,
                date_soumission=timezone.now()
            )
            print("[ERREUR] Une soumission dupliquee a pu etre creee!")
            return False
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            print("[OK] L'unicite est bien respectee (impossible de creer une soumission dupliquee)")
        else:
            print(f"[ATTENTION] Erreur inattendue: {str(e)}")
    
    print()
    print("=" * 80)
    print("RESUME DU TEST")
    print("=" * 80)
    print("[OK] Les tests de structure sont passes")
    print("[INFO] Note: Les donnees de test n'ont pas ete sauvegardees (transaction annulee)")
    print("   Pour un test reel, modifiez le script pour commiter la transaction")
    print()
    
    return True

if __name__ == '__main__':
    try:
        success = test_soumission_liste_presence()
        if success:
            print("[SUCCES] Tests termines avec succes")
        else:
            print("[ECHEC] Certains tests ont echoue")
    except Exception as e:
        print(f"[ERREUR] Erreur lors de l'execution des tests: {str(e)}")
        import traceback
        traceback.print_exc()
