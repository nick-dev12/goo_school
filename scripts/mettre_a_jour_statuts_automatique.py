#!/usr/bin/env python
"""
Script pour mettre à jour automatiquement les statuts des factures
Ce script peut être exécuté via une tâche cron ou planifiée
"""

import os
import sys
import django

# Ajouter le répertoire du projet au path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'goo_school.settings')
django.setup()

from school_admin.model.facturation_model import Facturation
from django.utils import timezone
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/statuts_factures.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def mettre_a_jour_statuts():
    """Met à jour les statuts des factures automatiquement"""
    try:
        logger.info("Début de la mise à jour automatique des statuts de factures")
        
        # Compter les factures avant mise à jour
        factures_avant = Facturation.objects.filter(
            statut__in=['en_attente', 'en_retard', 'impaye', 'contentieux']
        ).count()
        
        # Exécuter la mise à jour
        nombre_mises_a_jour = Facturation.mettre_a_jour_tous_les_statuts()
        
        logger.info(f"✅ Mise à jour terminée: {nombre_mises_a_jour} factures mises à jour")
        
        # Log des statistiques
        factures_en_retard = Facturation.objects.filter(statut='en_retard').count()
        factures_impayees = Facturation.objects.filter(statut='impaye').count()
        factures_contentieux = Facturation.objects.filter(statut='contentieux').count()
        
        logger.info(f"📊 Statistiques après mise à jour:")
        logger.info(f"   - Factures en retard: {factures_en_retard}")
        logger.info(f"   - Factures impayées: {factures_impayees}")
        logger.info(f"   - Factures contentieux: {factures_contentieux}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la mise à jour des statuts: {str(e)}")
        return False

if __name__ == "__main__":
    # Créer le dossier logs s'il n'existe pas
    os.makedirs('logs', exist_ok=True)
    
    # Exécuter la mise à jour
    success = mettre_a_jour_statuts()
    
    if success:
        print("✅ Mise à jour des statuts terminée avec succès")
        sys.exit(0)
    else:
        print("❌ Erreur lors de la mise à jour des statuts")
        sys.exit(1)
