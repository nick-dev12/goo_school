# school_admin/model/evaluation_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .professeur_model import Professeur
from .classe_model import Classe


class Evaluation(models.Model):
    """
    Modèle pour gérer les évaluations créées par les professeurs
    """
    
    TYPE_CHOICES = [
        ('controle', 'Contrôle écrit'),
        ('interrogation', 'Interrogation'),
        ('devoir_maison', 'Devoir maison'),
        ('projet', 'Projet'),
        ('oral', 'Évaluation orale'),
        ('pratique', 'Évaluation pratique'),
    ]
    
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
    
    titre = models.CharField(
        max_length=200,
        verbose_name="Titre de l'évaluation"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description"
    )
    type_evaluation = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='controle',
        verbose_name="Type d'évaluation"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='evaluations',
        verbose_name="Classe"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='evaluations',
        verbose_name="Professeur"
    )
    date_evaluation = models.DateField(
        verbose_name="Date de l'évaluation"
    )
    bareme = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(0)],
        verbose_name="Barème (points maximum)"
    )
    periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        default='trimestre1',
        verbose_name="Période scolaire"
    )
    duree = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Durée (en minutes)"
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
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
        ordering = ['-date_evaluation']
    
    def __str__(self):
        return f"{self.titre} - {self.classe.nom} ({self.date_evaluation})"
    
    @property
    def type_display(self):
        """Retourne l'affichage du type"""
        return dict(self.TYPE_CHOICES).get(self.type_evaluation, self.type_evaluation)
    
    @property
    def est_passe(self):
        """Vérifie si l'évaluation est passée"""
        from datetime import date
        return self.date_evaluation < date.today()
    
    @property
    def est_a_venir(self):
        """Vérifie si l'évaluation est à venir"""
        from datetime import date
        return self.date_evaluation > date.today()


class Note(models.Model):
    """
    Modèle pour gérer les notes des élèves
    """
    from .eleve_model import Eleve
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name="Élève"
    )
    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name="Évaluation"
    )
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Note obtenue"
    )
    appreciation = models.TextField(
        blank=True,
        null=True,
        verbose_name="Appréciation"
    )
    absent = models.BooleanField(
        default=False,
        verbose_name="Absent"
    )
    date_saisie = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de saisie"
    )
    
    class Meta:
        verbose_name = "Note"
        verbose_name_plural = "Notes"
        unique_together = ['eleve', 'evaluation']
        ordering = ['-evaluation__date_evaluation']
    
    def __str__(self):
        return f"{self.eleve.nom_complet} - {self.evaluation.titre} : {self.note}/{self.evaluation.bareme}"
    
    @property
    def note_sur_20(self):
        """Convertit la note sur 20"""
        if self.evaluation.bareme > 0:
            return (self.note / self.evaluation.bareme) * 20
        return 0
    
    @property
    def pourcentage(self):
        """Calcul du pourcentage"""
        if self.evaluation.bareme > 0:
            return (self.note / self.evaluation.bareme) * 100
        return 0

