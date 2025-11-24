"""
Modèle pour la gestion des années scolaires
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .etablissement_model import Etablissement


class AnneeScolaire(models.Model):
    """
    Modèle pour gérer les années scolaires d'un établissement
    Format: 2025-2026
    """
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='annees_scolaires',
        verbose_name="Établissement"
    )
    
    libelle = models.CharField(
        max_length=20,
        verbose_name="Libellé",
        help_text="Format: 2025-2026"
    )
    
    annee_debut = models.IntegerField(
        verbose_name="Année de début",
        help_text="Année de début (ex: 2025)"
    )
    
    annee_fin = models.IntegerField(
        verbose_name="Année de fin",
        help_text="Année de fin (ex: 2026)"
    )
    
    date_debut = models.DateField(
        verbose_name="Date de début",
        help_text="Date de début de l'année scolaire"
    )
    
    date_fin = models.DateField(
        verbose_name="Date de fin",
        help_text="Date de fin de l'année scolaire"
    )
    
    est_active = models.BooleanField(
        default=False,
        verbose_name="Session active",
        help_text="Indique si cette année scolaire est la session active pour l'établissement"
    )
    
    est_ouverte = models.BooleanField(
        default=False,
        verbose_name="Session ouverte",
        help_text="Indique si la session est ouverte (peut être créée avant le début)"
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
        verbose_name = "Année scolaire"
        verbose_name_plural = "Années scolaires"
        ordering = ['-annee_debut', '-date_debut']
        unique_together = ['etablissement', 'libelle']
        indexes = [
            models.Index(fields=['etablissement', 'est_active']),
            models.Index(fields=['etablissement', 'date_debut', 'date_fin']),
        ]
    
    def __str__(self):
        return f"{self.libelle} - {self.etablissement.nom}"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que annee_fin = annee_debut + 1
        if self.annee_debut and self.annee_fin:
            if self.annee_fin != self.annee_debut + 1:
                raise ValidationError({
                    'annee_fin': "L'année de fin doit être égale à l'année de début + 1."
                })
        
        # Vérifier que date_fin > date_debut
        if self.date_fin and self.date_debut and self.date_fin <= self.date_debut:
            raise ValidationError({
                'date_fin': "La date de fin doit être après la date de début."
            })
        
        # Vérifier qu'il n'y a pas de chevauchement avec d'autres années scolaires du même établissement
        if self.etablissement and self.date_debut and self.date_fin:
            annees_existantes = AnneeScolaire.objects.filter(
                etablissement=self.etablissement
            )
            
            if self.pk:
                annees_existantes = annees_existantes.exclude(pk=self.pk)
            
            for annee in annees_existantes:
                # Vérifier le chevauchement
                if (self.date_debut <= annee.date_fin and self.date_fin >= annee.date_debut):
                    raise ValidationError({
                        'date_debut': f"Cette année scolaire chevauche avec '{annee.libelle}' ({annee.date_debut} - {annee.date_fin})."
                    })
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour exécuter la validation
        """
        self.clean()
        
        # Si cette année est activée, désactiver les autres
        if self.est_active:
            AnneeScolaire.objects.filter(
                etablissement=self.etablissement
            ).exclude(pk=self.pk).update(est_active=False)
        
        super().save(*args, **kwargs)
    
    @property
    def est_en_cours(self):
        """
        Vérifie si l'année scolaire est actuellement en cours
        """
        aujourdhui = timezone.now().date()
        return self.date_debut <= aujourdhui <= self.date_fin
    
    @property
    def est_future(self):
        """
        Vérifie si l'année scolaire est dans le futur
        """
        aujourdhui = timezone.now().date()
        return self.date_debut > aujourdhui
    
    @property
    def est_passee(self):
        """
        Vérifie si l'année scolaire est passée
        """
        aujourdhui = timezone.now().date()
        return self.date_fin < aujourdhui
    
    @property
    def statut_annee(self):
        """
        Retourne le statut de l'année scolaire (en cours, à venir, terminée)
        """
        if self.est_en_cours:
            return 'en_cours'
        elif self.est_future:
            return 'a_venir'
        else:
            return 'terminee'
    
    @property
    def duree_jours(self):
        """
        Calcule la durée de l'année scolaire en jours
        """
        if self.date_debut and self.date_fin:
            return (self.date_fin - self.date_debut).days + 1
        return 0
    
    @classmethod
    def get_session_active(cls, etablissement):
        """
        Récupère la session active pour un établissement
        """
        return cls.objects.filter(
            etablissement=etablissement,
            est_active=True
        ).first()
    
    @classmethod
    def get_session_ouverte(cls, etablissement):
        """
        Récupère la session ouverte (est_ouverte=True) pour un établissement
        """
        aujourdhui = timezone.now().date()
        return cls.objects.filter(
            etablissement=etablissement,
            est_ouverte=True,
            date_debut__lte=aujourdhui
        ).first()
    
    @classmethod
    def get_annees_etablissement(cls, etablissement):
        """
        Récupère toutes les années scolaires d'un établissement, triées par date
        """
        return cls.objects.filter(
            etablissement=etablissement
        ).order_by('-annee_debut', '-date_debut')

