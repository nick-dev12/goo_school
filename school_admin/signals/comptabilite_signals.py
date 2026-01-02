"""
Signals pour la gestion automatique de la comptabilité
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from ..model.parametres_comptabilite_model import ParametresComptabilite


@receiver(post_save, sender=ParametresComptabilite)
def mettre_a_jour_systeme_apres_sauvegarde_parametres(sender, instance, created, **kwargs):
    """
    Met à jour automatiquement tout le système de comptabilité après la sauvegarde des paramètres.
    Cette fonction est appelée automatiquement après chaque sauvegarde (création ou mise à jour).
    
    Actions effectuées :
    - Initialise automatiquement tous les élèves inscrits dans l'année scolaire active
    - Met à jour les frais d'inscription et mensualités existants avec les nouveaux montants
    - Recalcule les statuts de paiement
    """
    try:
        instance.mettre_a_jour_systeme_comptabilite()
    except Exception as e:
        # En cas d'erreur, on log mais on ne bloque pas la sauvegarde
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la mise à jour automatique du système de comptabilité : {str(e)}")

