# school_admin/model/emploi_du_temps_model.py

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class EmploiDuTemps(models.Model):
    """
    Modèle représentant un emploi du temps pour une classe
    """
    JOUR_CHOICES = [
        ('lundi', 'Lundi'),
        ('mardi', 'Mardi'),
        ('mercredi', 'Mercredi'),
        ('jeudi', 'Jeudi'),
        ('vendredi', 'Vendredi'),
        ('samedi', 'Samedi'),
        ('dimanche', 'Dimanche'),
    ]
    
    # Relation avec la classe
    classe = models.ForeignKey(
        'school_admin.Classe',
        on_delete=models.CASCADE,
        related_name='emplois_du_temps',
        verbose_name="Classe"
    )
    
    # Informations de base
    annee_scolaire = models.CharField(
        max_length=20,
        verbose_name="Année scolaire",
        help_text="Ex: 2023-2024"
    )
    
    # Statut
    est_actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si cet emploi du temps est actuellement utilisé"
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
    
    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Notes ou commentaires sur cet emploi du temps"
    )
    
    class Meta:
        verbose_name = "Emploi du temps"
        verbose_name_plural = "Emplois du temps"
        ordering = ['-est_actif', '-date_creation']
        unique_together = ['classe', 'annee_scolaire', 'est_actif']
    
    def __str__(self):
        return f"Emploi du temps - {self.classe.nom} ({self.annee_scolaire})"
    
    @property
    def nombre_creneaux(self):
        """Retourne le nombre de créneaux dans cet emploi du temps"""
        return self.creneaux.count()


class CreneauEmploiDuTemps(models.Model):
    """
    Modèle représentant un créneau horaire dans un emploi du temps
    """
    JOUR_CHOICES = EmploiDuTemps.JOUR_CHOICES
    
    # Relation avec l'emploi du temps
    emploi_du_temps = models.ForeignKey(
        EmploiDuTemps,
        on_delete=models.CASCADE,
        related_name='creneaux',
        verbose_name="Emploi du temps"
    )
    
    # Jour de la semaine
    jour = models.CharField(
        max_length=10,
        choices=JOUR_CHOICES,
        verbose_name="Jour"
    )
    
    # Horaires
    heure_debut = models.TimeField(verbose_name="Heure de début")
    heure_fin = models.TimeField(verbose_name="Heure de fin")
    
    # Matière
    matiere = models.ForeignKey(
        'school_admin.Matiere',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_emploi_temps',
        verbose_name="Matière"
    )
    
    # Professeur
    professeur = models.ForeignKey(
        'school_admin.Professeur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_emploi_temps',
        verbose_name="Professeur"
    )
    
    # Salle
    salle = models.ForeignKey(
        'school_admin.Salle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_emploi_temps',
        verbose_name="Salle"
    )
    
    # Type de cours
    TYPE_COURS_CHOICES = [
        ('cours', 'Cours'),
        ('td', 'Travaux Dirigés'),
        ('tp', 'Travaux Pratiques'),
        ('controle', 'Contrôle'),
        ('examen', 'Examen'),
        ('sport', 'Sport'),
        ('pause', 'Pause'),
        ('autre', 'Autre'),
    ]
    
    type_cours = models.CharField(
        max_length=20,
        choices=TYPE_COURS_CHOICES,
        default='cours',
        verbose_name="Type de cours"
    )
    
    # Couleur (pour l'affichage)
    couleur = models.CharField(
        max_length=7,
        default='#3b82f6',
        verbose_name="Couleur",
        help_text="Code couleur hexadécimal pour l'affichage"
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    
    class Meta:
        verbose_name = "Créneau d'emploi du temps"
        verbose_name_plural = "Créneaux d'emploi du temps"
        ordering = ['jour', 'heure_debut']
    
    def __str__(self):
        matiere_nom = self.matiere.nom if self.matiere else "Sans matière"
        return f"{self.get_jour_display()} {self.heure_debut}-{self.heure_fin} - {matiere_nom}"
    
    @property
    def duree_minutes(self):
        """Retourne la durée du créneau en minutes"""
        from datetime import datetime, timedelta
        debut = datetime.combine(datetime.today(), self.heure_debut)
        fin = datetime.combine(datetime.today(), self.heure_fin)
        duree = (fin - debut).total_seconds() / 60
        return int(duree)

