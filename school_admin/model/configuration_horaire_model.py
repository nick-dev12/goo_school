# school_admin/model/configuration_horaire_model.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class ConfigurationHoraire(models.Model):
    """
    Configuration des horaires pour un établissement
    Définit les heures de début/fin et les périodes standards
    """
    
    etablissement = models.OneToOneField(
        'Etablissement',
        on_delete=models.CASCADE,
        related_name='configuration_horaire',
        verbose_name="Établissement"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='configurations_horaires',
        verbose_name="Année scolaire"
    )
    
    # Horaires globaux
    heure_debut_cours = models.TimeField(
        verbose_name="Heure de début des cours",
        help_text="Ex: 08:00"
    )
    heure_fin_cours = models.TimeField(
        verbose_name="Heure de fin des cours",
        help_text="Ex: 16:00"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Configuration active"
    )
    
    class Meta:
        verbose_name = "Configuration horaire"
        verbose_name_plural = "Configurations horaires"
    
    def __str__(self):
        return f"Horaires {self.etablissement.nom} ({self.heure_debut_cours} - {self.heure_fin_cours})"


class PeriodeEtablissement(models.Model):
    """
    Période de cours ou de pause au niveau de l'établissement
    Ces périodes sont utilisées par toutes les classes
    """
    
    TYPE_PERIODE_CHOICES = [
        ('cours', 'Période de cours'),
        ('pause', 'Pause/Récréation'),
        ('dejeuner', 'Pause déjeuner'),
    ]
    
    configuration_horaire = models.ForeignKey(
        ConfigurationHoraire,
        on_delete=models.CASCADE,
        related_name='periodes',
        verbose_name="Configuration horaire"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='periodes_etablissement',
        verbose_name="Année scolaire"
    )
    
    # Informations de la période
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de la période",
        help_text="Ex: Période 1, Récréation, Pause déjeuner"
    )
    
    type_periode = models.CharField(
        max_length=20,
        choices=TYPE_PERIODE_CHOICES,
        verbose_name="Type de période"
    )
    
    # Horaires
    heure_debut = models.TimeField(verbose_name="Heure de début")
    heure_fin = models.TimeField(verbose_name="Heure de fin")
    
    # Ordre d'affichage
    ordre = models.IntegerField(
        verbose_name="Ordre d'affichage",
        help_text="Détermine l'ordre d'affichage dans l'emploi du temps"
    )
    
    # Jours concernés
    JOUR_CHOICES = [
        ('lundi', 'Lundi'),
        ('mardi', 'Mardi'),
        ('mercredi', 'Mercredi'),
        ('jeudi', 'Jeudi'),
        ('vendredi', 'Vendredi'),
        ('samedi', 'Samedi'),
        ('dimanche', 'Dimanche'),
    ]
    
    # Si vide, la période s'applique à tous les jours
    # Sinon, on peut spécifier des jours spécifiques
    jours = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Jours concernés",
        help_text="Si vide, s'applique à tous les jours. Format: lundi,mardi,..."
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    class Meta:
        verbose_name = "Période d'établissement"
        verbose_name_plural = "Périodes d'établissement"
        ordering = ['ordre', 'heure_debut']
        unique_together = ['configuration_horaire', 'nom', 'heure_debut']
    
    def __str__(self):
        return f"{self.nom} ({self.heure_debut} - {self.heure_fin})"
    
    @property
    def duree_minutes(self):
        """Retourne la durée de la période en minutes"""
        from datetime import datetime, time
        
        # Convertir en objet time si nécessaire
        if isinstance(self.heure_debut, str):
            heure_d = datetime.strptime(self.heure_debut, '%H:%M').time()
        else:
            heure_d = self.heure_debut
        
        if isinstance(self.heure_fin, str):
            heure_f = datetime.strptime(self.heure_fin, '%H:%M').time()
        else:
            heure_f = self.heure_fin
        
        debut = datetime.combine(datetime.today(), heure_d)
        fin = datetime.combine(datetime.today(), heure_f)
        duree = (fin - debut).total_seconds() / 60
        return int(duree)
    
    @property
    def est_pause(self):
        """Retourne True si c'est une période de pause"""
        return self.type_periode in ['pause', 'dejeuner']
    
    def clean(self):
        """Valide que heure_fin > heure_debut"""
        if self.heure_fin <= self.heure_debut:
            raise ValidationError("L'heure de fin doit être après l'heure de début")

