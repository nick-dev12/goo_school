# school_admin/controllers/annee_scolaire_controller.py

from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import date
import logging

from ..model.annee_scolaire_model import AnneeScolaire
from ..model.etablissement_model import Etablissement

logger = logging.getLogger(__name__)


class AnneeScolaireController:
    """
    Contrôleur pour gérer les années scolaires d'un établissement
    """
    
    @staticmethod
    def generer_libelle_annee(annee_debut):
        """
        Génère le libellé d'une année scolaire au format "2025-2026"
        
        Args:
            annee_debut (int): Année de début (ex: 2025)
            
        Returns:
            str: Libellé au format "2025-2026"
        """
        annee_fin = annee_debut + 1
        return f"{annee_debut}-{annee_fin}"
    
    @staticmethod
    def get_annee_scolaire_suivante(etablissement):
        """
        Suggère la prochaine année scolaire pour un établissement
        Basé sur la dernière année scolaire créée ou l'année actuelle
        
        Args:
            etablissement (Etablissement): L'établissement concerné
            
        Returns:
            dict: Dictionnaire avec les informations suggérées
        """
        # Récupérer la dernière année scolaire
        derniere_annee = AnneeScolaire.objects.filter(
            etablissement=etablissement
        ).order_by('-annee_debut').first()
        
        maintenant = timezone.now().date()
        annee_actuelle = maintenant.year
        mois_actuel = maintenant.month
        
        if derniere_annee:
            # Suggérer l'année suivante
            annee_debut_suggeree = derniere_annee.annee_fin
        else:
            # Si aucune année n'existe, suggérer basé sur la date actuelle
            # Si on est après septembre, suggérer l'année suivante
            if mois_actuel >= 9:
                annee_debut_suggeree = annee_actuelle + 1
            else:
                annee_debut_suggeree = annee_actuelle
        
        libelle_suggere = AnneeScolaireController.generer_libelle_annee(annee_debut_suggeree)
        
        # Dates suggérées (début septembre, fin juin)
        date_debut_suggeree = date(annee_debut_suggeree, 9, 1)
        date_fin_suggeree = date(annee_debut_suggeree + 1, 6, 30)
        
        return {
            'annee_debut': annee_debut_suggeree,
            'annee_fin': annee_debut_suggeree + 1,
            'libelle': libelle_suggere,
            'date_debut': date_debut_suggeree,
            'date_fin': date_fin_suggeree,
        }
    
    @staticmethod
    @transaction.atomic
    def creer_annee_scolaire(etablissement, libelle, annee_debut, annee_fin, 
                            date_debut, date_fin, est_ouverte=False):
        """
        Crée une nouvelle année scolaire pour un établissement
        
        Args:
            etablissement (Etablissement): L'établissement
            libelle (str): Libellé de l'année (ex: "2025-2026")
            annee_debut (int): Année de début
            annee_fin (int): Année de fin
            date_debut (date): Date de début
            date_fin (date): Date de fin
            est_ouverte (bool): Si la session est ouverte
            
        Returns:
            AnneeScolaire: L'année scolaire créée
            
        Raises:
            ValidationError: Si les données sont invalides
        """
        try:
            annee_scolaire = AnneeScolaire(
                etablissement=etablissement,
                libelle=libelle,
                annee_debut=annee_debut,
                annee_fin=annee_fin,
                date_debut=date_debut,
                date_fin=date_fin,
                est_active=False,  # Par défaut non active
                est_ouverte=est_ouverte,
            )
            annee_scolaire.full_clean()  # Valide le modèle
            annee_scolaire.save()
            
            logger.info(f"Année scolaire {libelle} créée pour l'établissement {etablissement.nom}")
            return annee_scolaire
            
        except ValidationError as e:
            logger.error(f"Erreur de validation lors de la création de l'année scolaire: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'année scolaire: {e}")
            raise
    
    @staticmethod
    @transaction.atomic
    def activer_annee_scolaire(etablissement, annee_scolaire, initialiser=True):
        """
        Active une année scolaire pour un établissement
        Désactive automatiquement les autres années scolaires
        Initialise automatiquement les classes, matières, salles si demandé
        
        Args:
            etablissement (Etablissement): L'établissement
            annee_scolaire (AnneeScolaire): L'année scolaire à activer
            initialiser (bool): Si True, initialise automatiquement les structures
            
        Returns:
            tuple: (AnneeScolaire activée, dict statistiques d'initialisation)
            
        Raises:
            ValidationError: Si l'année scolaire n'appartient pas à l'établissement
        """
        if annee_scolaire.etablissement != etablissement:
            raise ValidationError("L'année scolaire n'appartient pas à cet établissement")
        
        # Désactiver toutes les autres années scolaires
        AnneeScolaire.objects.filter(
            etablissement=etablissement
        ).exclude(pk=annee_scolaire.pk).update(est_active=False)
        
        # Activer cette année scolaire
        annee_scolaire.est_active = True
        annee_scolaire.save()
        
        # Initialiser automatiquement les structures si demandé
        stats_initialisation = {}
        if initialiser:
            stats_initialisation = AnneeScolaireController.initialiser_annee_scolaire(
                etablissement, annee_scolaire
            )
        
        logger.info(f"Année scolaire {annee_scolaire.libelle} activée pour l'établissement {etablissement.nom}")
        return annee_scolaire, stats_initialisation
    
    @staticmethod
    def ouvrir_session(etablissement, annee_scolaire):
        """
        Ouvre une session (est_ouverte=True)
        
        Args:
            etablissement (Etablissement): L'établissement
            annee_scolaire (AnneeScolaire): L'année scolaire à ouvrir
            
        Returns:
            AnneeScolaire: L'année scolaire ouverte
        """
        if annee_scolaire.etablissement != etablissement:
            raise ValidationError("L'année scolaire n'appartient pas à cet établissement")
        
        annee_scolaire.est_ouverte = True
        annee_scolaire.save()
        
        logger.info(f"Session {annee_scolaire.libelle} ouverte pour l'établissement {etablissement.nom}")
        return annee_scolaire
    
    @staticmethod
    def fermer_session(etablissement, annee_scolaire):
        """
        Ferme une session (est_ouverte=False)
        
        Args:
            etablissement (Etablissement): L'établissement
            annee_scolaire (AnneeScolaire): L'année scolaire à fermer
            
        Returns:
            AnneeScolaire: L'année scolaire fermée
        """
        if annee_scolaire.etablissement != etablissement:
            raise ValidationError("L'année scolaire n'appartient pas à cet établissement")
        
        annee_scolaire.est_ouverte = False
        annee_scolaire.save()
        
        logger.info(f"Session {annee_scolaire.libelle} fermée pour l'établissement {etablissement.nom}")
        return annee_scolaire
    
    @staticmethod
    def get_statistiques_annee(annee_scolaire):
        """
        Récupère les statistiques d'une année scolaire
        
        Args:
            annee_scolaire (AnneeScolaire): L'année scolaire
            
        Returns:
            dict: Dictionnaire avec les statistiques
        """
        from ..model.evaluation_model import Evaluation, Note
        from ..model.moyenne_model import Moyenne
        from ..model.presence_model import Presence
        from ..model.eleve_model import Eleve
        
        stats = {
            'nombre_evaluations': Evaluation.objects.filter(annee_scolaire=annee_scolaire).count(),
            'nombre_notes': Note.objects.filter(annee_scolaire=annee_scolaire).count(),
            'nombre_moyennes': Moyenne.objects.filter(annee_scolaire=annee_scolaire).count(),
            'nombre_presences': Presence.objects.filter(annee_scolaire=annee_scolaire).count(),
            'nombre_eleves': Eleve.objects.filter(
                etablissement=annee_scolaire.etablissement,
                date_inscription__gte=annee_scolaire.date_debut,
                date_inscription__lte=annee_scolaire.date_fin
            ).count(),
        }
        
        return stats
    
    @staticmethod
    @transaction.atomic
    def initialiser_annee_scolaire(etablissement, annee_scolaire):
        """
        Initialise automatiquement une année scolaire en copiant :
        - Les classes actives
        - Les matières actives
        - Les salles actives
        - Les affectations enseignants (optionnel, peut être fait manuellement)
        
        Args:
            etablissement (Etablissement): L'établissement
            annee_scolaire (AnneeScolaire): L'année scolaire à initialiser
            
        Returns:
            dict: Statistiques de l'initialisation
        """
        from ..model.classe_model import Classe
        from ..model.matiere_model import Matiere
        from ..model.salle_model import Salle
        
        stats = {
            'classes_copiees': 0,
            'matieres_copiees': 0,
            'salles_copiees': 0,
        }
        
        # Les classes, matières et salles sont déjà liées à l'établissement
        # et n'ont pas besoin d'être copiées car elles sont réutilisables
        # On vérifie juste qu'elles existent et sont actives
        
        classes_actives = Classe.objects.filter(etablissement=etablissement, actif=True).count()
        matieres_actives = Matiere.objects.filter(etablissement=etablissement, actif=True).count()
        salles_actives = Salle.objects.filter(etablissement=etablissement, actif=True).count()
        
        stats['classes_copiees'] = classes_actives
        stats['matieres_copiees'] = matieres_actives
        stats['salles_copiees'] = salles_actives
        
        logger.info(
            f"Initialisation de l'année scolaire {annee_scolaire.libelle} : "
            f"{classes_actives} classes, {matieres_actives} matières, {salles_actives} salles"
        )
        
        return stats

