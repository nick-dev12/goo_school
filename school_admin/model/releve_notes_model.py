"""
Modèle pour la gestion des relevés de notes et leur soumission
"""
from django.db import models
from .classe_model import Classe
from .professeur_model import Professeur
from .matiere_model import Matiere
from .etablissement_model import Etablissement


class ReleveNotes(models.Model):
    """
    Modèle pour gérer la soumission des relevés de notes par période
    Un relevé regroupe toutes les notes d'une classe pour une matière sur une période
    Système adapté au Sénégal : Trimestres (Primaire/Collège) et Semestres (Lycée)
    """
    
    PERIODE_CHOICES = [
        # Système trimestre (Primaire & Collège)
        ('trimestre1', '1er Trimestre'),
        ('trimestre2', '2ème Trimestre'),
        ('trimestre3', '3ème Trimestre'),
        # Système semestre (Lycée)
        ('semestre1', '1er Semestre'),
        ('semestre2', '2ème Semestre'),
        # Annuel
        ('annuel', 'Année complète'),
    ]
    
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='releves_notes',
        verbose_name="Classe"
    )
    
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='releves_soumis',
        verbose_name="Professeur"
    )
    
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='releves_matiere',
        verbose_name="Matière"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='releves_etablissement',
        verbose_name="Établissement"
    )
    
    periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        default='trimestre1',
        verbose_name="Période"
    )
    
    soumis = models.BooleanField(
        default=False,
        verbose_name="Soumis"
    )
    
    date_soumission = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de soumission"
    )
    
    commentaire = models.TextField(
        blank=True,
        null=True,
        verbose_name="Commentaire"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
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
        verbose_name = "Relevé de notes"
        verbose_name_plural = "Relevés de notes"
        unique_together = ['classe', 'professeur', 'matiere', 'periode']
        ordering = ['-date_creation']
    
    def __str__(self):
        statut = "Soumis" if self.soumis else "En cours"
        return f"{self.classe.nom} - {self.matiere.nom} ({self.get_periode_display()}) - {statut}"
    
    def soumettre(self):
        """
        Soumet le relevé de notes (verrouillage)
        """
        from django.utils import timezone
        self.soumis = True
        self.date_soumission = timezone.now()
        self.save()
    
    def rouvrir(self):
        """
        Rouvre le relevé pour modification
        """
        self.soumis = False
        self.date_soumission = None
        self.save()

