# school_admin/model/classe_model.py

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Classe(models.Model):
    """
    Modèle représentant une classe dans un établissement
    """
    NIVEAU_CHOICES = [
        ('maternelle', 'Maternelle'),
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('superieur', 'Supérieur'),
    ]
    
    # Informations de base
    nom = models.CharField(max_length=100, verbose_name="Nom de la classe")
    niveau = models.CharField(max_length=20, choices=NIVEAU_CHOICES, verbose_name="Niveau")
    code_classe = models.CharField(max_length=20, unique=True, verbose_name="Code de la classe")
    capacite_max = models.PositiveIntegerField(default=30, verbose_name="Capacité maximale")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    
    # Relation avec l'établissement
    etablissement = models.ForeignKey(
        'school_admin.Etablissement', 
        on_delete=models.CASCADE,
        related_name='classes',
        verbose_name="Établissement"
    )
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    def __str__(self):
        return f"{self.nom} - {self.get_niveau_display()}"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de la classe"""
        return f"{self.nom} ({self.get_niveau_display()})"
    
    @property
    def nombre_eleves(self):
        """Retourne le nombre d'élèves dans cette classe"""
        from .eleve_model import Eleve
        return Eleve.objects.filter(classe=self, actif=True).count()
    
    @property
    def places_disponibles(self):
        """Retourne le nombre de places disponibles"""
        return max(0, self.capacite_max - self.nombre_eleves)
    
    @property
    def taux_occupation(self):
        """Retourne le taux d'occupation en pourcentage"""
        if self.capacite_max == 0:
            return 0
        return round((self.nombre_eleves / self.capacite_max) * 100, 1)
    
    class Meta:
        verbose_name = "Classe"
        verbose_name_plural = "Classes"
        ordering = ['niveau', 'nom']
        unique_together = ['nom', 'etablissement']
