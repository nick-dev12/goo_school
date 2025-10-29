"""
Modèle pour la gestion des périodes scolaires
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .etablissement_model import Etablissement


class PeriodeScolaire(models.Model):
    """
    Modèle pour définir les périodes scolaires de l'établissement
    (Trimestres, Semestres, etc.)
    """
    
    TYPE_PERIODE_CHOICES = [
        ('trimestre', 'Trimestre'),
        ('semestre', 'Semestre'),
        ('annee', 'Année complète'),
    ]
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='periodes_scolaires',
        verbose_name="Établissement"
    )
    
    nom_periode = models.CharField(
        max_length=100,
        verbose_name="Nom de la période",
        help_text="Ex: 1er Trimestre, Semestre 1"
    )
    
    type_periode = models.CharField(
        max_length=20,
        choices=TYPE_PERIODE_CHOICES,
        default='trimestre',
        verbose_name="Type de période"
    )
    
    date_debut = models.DateField(
        verbose_name="Date de début",
        help_text="Date de début de la période"
    )
    
    date_fin = models.DateField(
        verbose_name="Date de fin",
        help_text="Date de fin de la période"
    )
    
    annee_scolaire = models.CharField(
        max_length=20,
        verbose_name="Année scolaire",
        help_text="Ex: 2025-2026"
    )
    
    est_active = models.BooleanField(
        default=True,
        verbose_name="Période active",
        help_text="Indique si cette période est actuellement active"
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
        verbose_name = "Période scolaire"
        verbose_name_plural = "Périodes scolaires"
        ordering = ['annee_scolaire', 'date_debut']
        unique_together = ['etablissement', 'nom_periode', 'annee_scolaire']
    
    def __str__(self):
        return f"{self.nom_periode} ({self.annee_scolaire})"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que la date de fin est après la date de début
        if self.date_fin and self.date_debut and self.date_fin <= self.date_debut:
            raise ValidationError({
                'date_fin': "La date de fin doit être après la date de début."
            })
        
        # Vérifier qu'il n'y a pas de chevauchement avec d'autres périodes
        if self.etablissement:
            periodes_existantes = PeriodeScolaire.objects.filter(
                etablissement=self.etablissement,
                annee_scolaire=self.annee_scolaire
            )
            
            if self.pk:
                periodes_existantes = periodes_existantes.exclude(pk=self.pk)
            
            for periode in periodes_existantes:
                # Vérifier le chevauchement
                if (self.date_debut <= periode.date_fin and self.date_fin >= periode.date_debut):
                    raise ValidationError({
                        'date_debut': f"Cette période chevauche avec '{periode.nom_periode}'."
                    })
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour exécuter la validation
        """
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def duree_jours(self):
        """
        Calcule la durée de la période en jours
        """
        if self.date_debut and self.date_fin:
            return (self.date_fin - self.date_debut).days + 1
        return 0
    
    @property
    def est_en_cours(self):
        """
        Vérifie si la période est actuellement en cours
        """
        aujourdhui = timezone.now().date()
        return self.date_debut <= aujourdhui <= self.date_fin
    
    @property
    def est_future(self):
        """
        Vérifie si la période est dans le futur
        """
        aujourdhui = timezone.now().date()
        return self.date_debut > aujourdhui
    
    @property
    def est_passee(self):
        """
        Vérifie si la période est passée
        """
        aujourdhui = timezone.now().date()
        return self.date_fin < aujourdhui
    
    @property
    def statut_periode(self):
        """
        Retourne le statut de la période (en cours, à venir, terminée)
        """
        if self.est_en_cours:
            return 'en_cours'
        elif self.est_future:
            return 'a_venir'
        else:
            return 'terminee'
    
    @classmethod
    def get_periode_active(cls, etablissement):
        """
        Récupère la période actuellement active pour un établissement
        """
        aujourdhui = timezone.now().date()
        return cls.objects.filter(
            etablissement=etablissement,
            est_active=True,
            date_debut__lte=aujourdhui,
            date_fin__gte=aujourdhui
        ).first()
    
    @classmethod
    def get_periodes_annee(cls, etablissement, annee_scolaire):
        """
        Récupère toutes les périodes d'une année scolaire
        """
        return cls.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire
        ).order_by('date_debut')

