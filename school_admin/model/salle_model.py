from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

class Salle(models.Model):
    """Modèle pour représenter une salle dans l'établissement"""
    
    TYPE_SALLE_CHOICES = [
        ('classe', 'Salle de Classe'),
        ('laboratoire', 'Laboratoire'),
        ('bibliotheque', 'Bibliothèque'),
        ('salle_informatique', 'Salle d\'Informatique'),
        ('salle_art', 'Salle d\'Arts'),
        ('salle_musique', 'Salle de Musique'),
        ('salle_sport', 'Salle de Sport'),
        ('amphitheatre', 'Amphithéâtre'),
        ('salle_reunion', 'Salle de Réunion'),
        ('bureau', 'Bureau'),
        ('autre', 'Autre'),
    ]
    
    ETAT_CHOICES = [
        ('disponible', 'Disponible'),
        ('occupee', 'Occupée'),
        ('maintenance', 'En Maintenance'),
        ('fermee', 'Fermée'),
    ]

    # Informations de base
    nom = models.CharField(max_length=100, verbose_name="Nom de la salle")
    numero = models.CharField(max_length=20, verbose_name="Numéro de salle")
    type_salle = models.CharField(
        max_length=20,
        choices=TYPE_SALLE_CHOICES,
        default='classe',
        verbose_name="Type de salle"
    )
    
    # Capacité
    capacite_max = models.PositiveIntegerField(
        default=30,
        verbose_name="Capacité maximale"
    )
    
    # État et disponibilité
    etat = models.CharField(
        max_length=15,
        choices=ETAT_CHOICES,
        default='disponible',
        verbose_name="État de la salle"
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    # Relations
    etablissement = models.ForeignKey(
        'Etablissement',
        on_delete=models.CASCADE,
        related_name='salles',
        verbose_name="Établissement"
    )
    
    # Dates
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    
    class Meta:
        verbose_name = "Salle"
        verbose_name_plural = "Salles"
        ordering = ['numero', 'nom']
        unique_together = ('numero', 'etablissement')  # Un numéro unique par établissement
    
    def __str__(self):
        return f"{self.nom} ({self.numero})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de la salle"""
        return f"{self.nom} - {self.numero}"
    
    @property
    def type_display(self):
        """Retourne le type de salle formaté"""
        return self.get_type_salle_display()
    
    @property
    def etat_display(self):
        """Retourne l'état formaté"""
        return self.get_etat_display()
    
    @property
    def est_disponible(self):
        """Vérifie si la salle est disponible"""
        return self.etat == 'disponible' and self.actif
    
    @property
    def capacite_actuelle(self):
        """Retourne la capacité actuelle (pour l'instant, retourne la capacité max)"""
        # TODO: Implémenter la logique pour calculer la capacité actuelle
        # basée sur les réservations ou occupations actuelles
        return self.capacite_max
    
    def clean(self):
        """Validation personnalisée"""
        super().clean()
        
        # Vérifier que la capacité est positive
        if self.capacite_max <= 0:
            raise ValidationError("La capacité maximale doit être positive.")
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation"""
        self.full_clean()
        super().save(*args, **kwargs)
