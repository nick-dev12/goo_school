# school_admin/model/moyenne_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .eleve_model import Eleve
from .classe_model import Classe
from .matiere_model import Matiere
from .professeur_model import Professeur


class Moyenne(models.Model):
    """
    Modèle pour enregistrer les moyennes calculées des élèves
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
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='moyennes',
        verbose_name="Élève"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='moyennes',
        verbose_name="Classe"
    )
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='moyennes',
        verbose_name="Matière"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='moyennes_calculees',
        verbose_name="Professeur"
    )
    periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        default='trimestre1',
        verbose_name="Période"
    )
    moyenne = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Moyenne sur 20"
    )
    nombre_notes = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de notes utilisées"
    )
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name="Date du calcul"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    class Meta:
        verbose_name = "Moyenne"
        verbose_name_plural = "Moyennes"
        unique_together = ['eleve', 'classe', 'matiere', 'periode']
        ordering = ['-date_calcul']
    
    def __str__(self):
        return f"{self.eleve.nom_complet} - {self.matiere.nom} : {self.moyenne}/20"
    
    @property
    def appreciation(self):
        """Retourne une appréciation selon la moyenne"""
        if self.moyenne >= 16:
            return "Excellent travail, continuez ainsi !"
        elif self.moyenne >= 14:
            return "Très bon niveau, félicitations !"
        elif self.moyenne >= 12:
            return "Bon travail, continuez vos efforts."
        elif self.moyenne >= 10:
            return "Travail satisfaisant, peut mieux faire."
        elif self.moyenne >= 8:
            return "Résultats fragiles, des efforts sont nécessaires."
        else:
            return "Résultats insuffisants, un soutien est recommandé."

