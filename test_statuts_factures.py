#!/usr/bin/env python
"""
Script de test pour la mise à jour automatique des statuts de factures
Ce script teste toutes les fonctionnalités du système de gestion des statuts
"""

import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal

# Configuration Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'goo_school.settings')

# Ajouter le répertoire du projet au PYTHONPATH
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

django.setup()

from school_admin.model.facturation_model import Facturation
from school_admin.model.etablissement_model import Etablissement
from django.utils import timezone

def test_creation_factures_test():
    """Crée des factures de test avec différentes dates d'échéance"""
    print("🧪 Test 1: Création de factures de test")
    print("=" * 50)
    
    # Récupérer un établissement existant ou en créer un
    try:
        etablissement = Etablissement.objects.filter(actif=True).first()
        if not etablissement:
            print("❌ Aucun établissement trouvé. Création d'un établissement de test...")
            etablissement = Etablissement.objects.create(
                nom="École Test",
                type_etablissement="primaire",
                ville="Douala",
                pays="Cameroun",
                directeur_nom="Directeur Test",
                telephone="+237 6XX XX XX XX",
                email="test@ecole.com",
                actif=True,
                type_facturation="mensuel",
                montant_par_eleve=Decimal('3000.00')
            )
            print(f"✅ Établissement de test créé: {etablissement.nom}")
        else:
            print(f"✅ Établissement trouvé: {etablissement.nom}")
    except Exception as e:
        print(f"❌ Erreur lors de la création/récupération de l'établissement: {e}")
        return False
    
    # Créer des factures de test avec différentes dates
    factures_test = []
    
    # Facture 1: Échue il y a 5 jours (doit être "en_retard")
    date_retard = timezone.now() - timedelta(days=5)
    facture1 = Facturation.objects.create(
        etablissement=etablissement,
        type_facture="frais_service_mensuel",
        description="Frais de service mensuel - Test retard",
        montant_unitaire=Decimal('3000.00'),
        quantite=10,
        date_echeance=date_retard,
        statut="en_attente"
    )
    factures_test.append(facture1)
    print(f"✅ Facture 1 créée: {facture1.numero_facture} (échéance: {date_retard.strftime('%d/%m/%Y')}) - Statut: {facture1.statut}")
    
    # Facture 2: Échue il y a 35 jours (doit être "impaye")
    date_impaye = timezone.now() - timedelta(days=35)
    facture2 = Facturation.objects.create(
        etablissement=etablissement,
        type_facture="frais_service_mensuel",
        description="Frais de service mensuel - Test impayé",
        montant_unitaire=Decimal('3000.00'),
        quantite=15,
        date_echeance=date_impaye,
        statut="en_attente"
    )
    factures_test.append(facture2)
    print(f"✅ Facture 2 créée: {facture2.numero_facture} (échéance: {date_impaye.strftime('%d/%m/%Y')}) - Statut: {facture2.statut}")
    
    # Facture 3: Échue il y a 65 jours (doit être "contentieux")
    date_contentieux = timezone.now() - timedelta(days=65)
    facture3 = Facturation.objects.create(
        etablissement=etablissement,
        type_facture="frais_service_mensuel",
        description="Frais de service mensuel - Test contentieux",
        montant_unitaire=Decimal('3000.00'),
        quantite=20,
        date_echeance=date_contentieux,
        statut="en_attente"
    )
    factures_test.append(facture3)
    print(f"✅ Facture 3 créée: {facture3.numero_facture} (échéance: {date_contentieux.strftime('%d/%m/%Y')}) - Statut: {facture3.statut}")
    
    # Facture 4: Échue dans 10 jours (doit rester "en_attente")
    date_future = timezone.now() + timedelta(days=10)
    facture4 = Facturation.objects.create(
        etablissement=etablissement,
        type_facture="frais_service_mensuel",
        description="Frais de service mensuel - Test future",
        montant_unitaire=Decimal('3000.00'),
        quantite=25,
        date_echeance=date_future,
        statut="en_attente"
    )
    factures_test.append(facture4)
    print(f"✅ Facture 4 créée: {facture4.numero_facture} (échéance: {date_future.strftime('%d/%m/%Y')}) - Statut: {facture4.statut}")
    
    # Facture 5: Avec reste à payer échu il y a 40 jours
    date_reste_impaye = timezone.now() - timedelta(days=40)
    facture5 = Facturation.objects.create(
        etablissement=etablissement,
        type_facture="frais_service_mensuel",
        description="Frais de service mensuel - Test reste impayé",
        montant_unitaire=Decimal('3000.00'),
        quantite=12,
        date_echeance=timezone.now() + timedelta(days=30),  # Échéance principale future
        date_echeance_reste=date_reste_impaye,  # Reste échu
        reste_a_payer=Decimal('15000.00'),
        paiement_partiel=True,
        statut="paye"  # Déjà payée partiellement
    )
    factures_test.append(facture5)
    print(f"✅ Facture 5 créée: {facture5.numero_facture} (reste échu: {date_reste_impaye.strftime('%d/%m/%Y')}) - Statut: {facture5.statut}")
    
    return factures_test

def test_mise_a_jour_automatique():
    """Teste la mise à jour automatique des statuts"""
    print("\n🧪 Test 2: Mise à jour automatique des statuts")
    print("=" * 50)
    
    # Afficher les statuts avant mise à jour
    print("📊 Statuts avant mise à jour:")
    factures = Facturation.objects.all()
    for facture in factures:
        print(f"   - {facture.numero_facture}: {facture.get_statut_display()} (échéance: {facture.date_echeance.strftime('%d/%m/%Y') if facture.date_echeance else 'N/A'})")
    
    # Exécuter la mise à jour automatique
    print("\n🔄 Exécution de la mise à jour automatique...")
    try:
        nombre_mises_a_jour = Facturation.mettre_a_jour_tous_les_statuts()
        print(f"✅ Mise à jour terminée: {nombre_mises_a_jour} factures mises à jour")
    except Exception as e:
        print(f"❌ Erreur lors de la mise à jour: {e}")
        return False
    
    # Afficher les statuts après mise à jour
    print("\n📊 Statuts après mise à jour:")
    factures = Facturation.objects.all()
    for facture in factures:
        print(f"   - {facture.numero_facture}: {facture.get_statut_display()} (échéance: {facture.date_echeance.strftime('%d/%m/%Y') if facture.date_echeance else 'N/A'})")
    
    return True

def test_verification_statuts():
    """Vérifie que les statuts sont corrects après mise à jour"""
    print("\n🧪 Test 3: Vérification des statuts")
    print("=" * 50)
    
    factures = Facturation.objects.all()
    erreurs = []
    
    for facture in factures:
        statut_attendu = None
        jours_retard = 0
        
        # Calculer le retard
        if facture.date_echeance and facture.date_echeance < timezone.now():
            jours_retard = (timezone.now() - facture.date_echeance).days
        elif facture.date_echeance_reste and facture.date_echeance_reste < timezone.now():
            jours_retard = (timezone.now() - facture.date_echeance_reste).days
        
        # Déterminer le statut attendu
        if jours_retard >= 60:
            statut_attendu = "contentieux"
        elif jours_retard >= 30:
            statut_attendu = "impaye"
        elif jours_retard > 0:
            statut_attendu = "en_retard"
        else:
            statut_attendu = "en_attente"
        
        # Vérifier si le statut est correct
        if facture.statut != statut_attendu:
            erreurs.append({
                'facture': facture.numero_facture,
                'statut_actuel': facture.statut,
                'statut_attendu': statut_attendu,
                'jours_retard': jours_retard
            })
    
    if erreurs:
        print("❌ Erreurs détectées:")
        for erreur in erreurs:
            print(f"   - {erreur['facture']}: {erreur['statut_actuel']} (attendu: {erreur['statut_attendu']}, retard: {erreur['jours_retard']} jours)")
        return False
    else:
        print("✅ Tous les statuts sont corrects!")
        return True

def test_statistiques():
    """Affiche les statistiques des statuts"""
    print("\n🧪 Test 4: Statistiques des statuts")
    print("=" * 50)
    
    stats = {
        'en_attente': Facturation.objects.filter(statut='en_attente').count(),
        'en_retard': Facturation.objects.filter(statut='en_retard').count(),
        'impaye': Facturation.objects.filter(statut='impaye').count(),
        'contentieux': Facturation.objects.filter(statut='contentieux').count(),
        'paye': Facturation.objects.filter(statut='paye').count(),
    }
    
    print("📊 Répartition des statuts:")
    for statut, count in stats.items():
        print(f"   - {statut}: {count} factures")
    
    total = sum(stats.values())
    print(f"\n📈 Total: {total} factures")
    
    return stats

def nettoyer_factures_test():
    """Nettoie les factures de test créées"""
    print("\n🧹 Nettoyage des factures de test")
    print("=" * 50)
    
    try:
        # Supprimer les factures de test (celles avec "Test" dans la description)
        factures_test = Facturation.objects.filter(description__icontains="Test")
        nombre_supprimees = factures_test.count()
        factures_test.delete()
        print(f"✅ {nombre_supprimees} factures de test supprimées")
        
        # Supprimer l'établissement de test s'il existe
        etablissement_test = Etablissement.objects.filter(nom="École Test")
        if etablissement_test.exists():
            etablissement_test.delete()
            print("✅ Établissement de test supprimé")
        
        return True
    except Exception as e:
        print(f"❌ Erreur lors du nettoyage: {e}")
        return False

def main():
    """Fonction principale de test"""
    print("🚀 DÉBUT DES TESTS - Mise à jour automatique des statuts de factures")
    print("=" * 80)
    
    try:
        # Test 1: Création de factures de test
        factures_test = test_creation_factures_test()
        if not factures_test:
            print("❌ Échec de la création des factures de test")
            return False
        
        # Test 2: Mise à jour automatique
        if not test_mise_a_jour_automatique():
            print("❌ Échec de la mise à jour automatique")
            return False
        
        # Test 3: Vérification des statuts
        if not test_verification_statuts():
            print("❌ Échec de la vérification des statuts")
            return False
        
        # Test 4: Statistiques
        stats = test_statistiques()
        
        # Nettoyage
        nettoyer_factures_test()
        
        print("\n🎉 TOUS LES TESTS SONT PASSÉS AVEC SUCCÈS!")
        print("✅ Le système de mise à jour automatique des statuts fonctionne correctement")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR GÉNÉRALE: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
