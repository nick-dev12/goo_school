#!/usr/bin/env python
"""
Script pour supprimer toutes les factures de la table Facturation
"""
import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from school_admin.model.facturation_model import Facturation

def supprimer_toutes_factures():
    """Supprimer toutes les factures de la base de données"""
    try:
        print("=== Suppression de toutes les factures ===")
        
        # Compter les factures existantes
        nombre_factures = Facturation.objects.count()
        print(f"📊 Nombre de factures trouvées: {nombre_factures}")
        
        if nombre_factures == 0:
            print("✅ Aucune facture à supprimer")
            return True
        
        # Afficher les détails des factures avant suppression
        print("\n📋 Détails des factures à supprimer:")
        factures = Facturation.objects.all()
        for i, facture in enumerate(factures, 1):
            print(f"   {i}. {facture.numero_facture} - {facture.type_facture} - {facture.montant_total} FCFA - {facture.statut}")
        
        # Demander confirmation
        print(f"\n⚠️  ATTENTION: Vous êtes sur le point de supprimer {nombre_factures} facture(s)")
        print("Cette action est IRRÉVERSIBLE !")
        
        confirmation = input("\nÊtes-vous sûr de vouloir continuer ? (tapez 'OUI' pour confirmer): ")
        
        if confirmation != 'OUI':
            print("❌ Suppression annulée par l'utilisateur")
            return False
        
        # Supprimer toutes les factures
        print("\n🗑️  Suppression en cours...")
        factures_supprimees = Facturation.objects.all().delete()
        
        print(f"✅ Suppression terminée !")
        print(f"   - Factures supprimées: {factures_supprimees[0]}")
        
        # Vérifier que toutes les factures ont été supprimées
        factures_restantes = Facturation.objects.count()
        if factures_restantes == 0:
            print("✅ Toutes les factures ont été supprimées avec succès")
        else:
            print(f"⚠️  Il reste {factures_restantes} facture(s) dans la base de données")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la suppression: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚨 SCRIPT DE SUPPRESSION DE TOUTES LES FACTURES 🚨")
    print("=" * 50)
    
    success = supprimer_toutes_factures()
    
    if success:
        print("\n🎉 Suppression réussie !")
        print("Toutes les factures ont été supprimées de la base de données.")
    else:
        print("\n💥 Suppression échouée !")
        print("Veuillez vérifier les erreurs ci-dessus.")
        sys.exit(1)