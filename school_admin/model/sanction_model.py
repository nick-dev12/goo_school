# school_admin/model/sanction_model.py

from django.db import models
from django.utils import timezone
from .eleve_model import Eleve
from .classe_model import Classe
from .professeur_model import Professeur
from .etablissement_model import Etablissement


class Sanction(models.Model):
    """
    Modèle pour gérer les sanctions disciplinaires des élèves
    """
    
    TYPE_SANCTION_CHOICES = [
        ('avertissement', 'Avertissement'),
        ('blame', 'Blâme'),
        ('exclusion_cours', 'Exclusion de cours'),
        ('exclusion_temporaire', 'Exclusion temporaire'),
        ('travaux_interet_general', 'Travaux d\'intérêt général'),
        ('retenue', 'Retenue'),
        ('convocation_parents', 'Convocation des parents'),
        ('avertissement_conduite', 'Avertissement de conduite'),
    ]
    
    RAISON_SANCTION_CHOICES = [
        ('indiscipline', 'Indiscipline'),
        ('absence_non_justifiee', 'Absence non justifiée répétée'),
        ('retards_repetes', 'Retards répétés'),
        ('manque_respect', 'Manque de respect envers le personnel'),
        ('violence', 'Violence physique ou verbale'),
        ('triche', 'Tricherie lors d\'une évaluation'),
        ('desobeissance', 'Désobéissance'),
        ('perturbation_cours', 'Perturbation du cours'),
        ('degradation_materiel', 'Dégradation du matériel'),
        ('vol', 'Vol'),
        ('comportement_inapproprie', 'Comportement inapproprié'),
        ('non_respect_reglement', 'Non-respect du règlement intérieur'),
        ('autre', 'Autre raison'),
    ]
    
    GRAVITE_CHOICES = [
        ('legere', 'Légère'),
        ('moyenne', 'Moyenne'),
        ('grave', 'Grave'),
        ('tres_grave', 'Très grave'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='sanctions',
        verbose_name="Élève"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='sanctions',
        verbose_name="Classe"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='sanctions_donnees',
        verbose_name="Professeur"
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='sanctions',
        verbose_name="Établissement"
    )
    type_sanction = models.CharField(
        max_length=30,
        choices=TYPE_SANCTION_CHOICES,
        verbose_name="Type de sanction"
    )
    raison = models.CharField(
        max_length=40,
        choices=RAISON_SANCTION_CHOICES,
        verbose_name="Raison de la sanction"
    )
    gravite = models.CharField(
        max_length=20,
        choices=GRAVITE_CHOICES,
        default='moyenne',
        verbose_name="Gravité"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description détaillée"
    )
    date_sanction = models.DateField(
        default=timezone.now,
        verbose_name="Date de la sanction"
    )
    duree_jours = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Durée (en jours)",
        help_text="Pour exclusions temporaires ou retenues"
    )
    date_debut_execution = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date de début d'exécution"
    )
    date_fin_execution = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date de fin d'exécution"
    )
    executee = models.BooleanField(
        default=False,
        verbose_name="Sanction exécutée"
    )
    date_execution = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date d'exécution"
    )
    parents_informes = models.BooleanField(
        default=False,
        verbose_name="Parents informés"
    )
    date_information_parents = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date d'information des parents"
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    class Meta:
        verbose_name = "Sanction"
        verbose_name_plural = "Sanctions"
        ordering = ['-date_sanction', '-date_creation']
    
    def __str__(self):
        return f"{self.get_type_sanction_display()} - {self.eleve.nom_complet} ({self.date_sanction.strftime('%d/%m/%Y')})"
    
    @staticmethod
    def get_nombre_sanctions(eleve):
        """Retourne le nombre total de sanctions d'un élève"""
        return Sanction.objects.filter(eleve=eleve).count()
    
    @staticmethod
    def get_sanctions_graves(eleve):
        """Retourne le nombre de sanctions graves d'un élève"""
        return Sanction.objects.filter(
            eleve=eleve,
            gravite__in=['grave', 'tres_grave']
        ).count()

