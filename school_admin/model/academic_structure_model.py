# school_admin/model/academic_structure_model.py

from django.db import models
from django.utils.translation import gettext_lazy as _


class AcademicCycle(models.Model):
    """
    Cycle académique LMD : Licence, Master, Doctorat.
    Modèle africain (Sénégal, Gabon) - système LMD.
    """
    CODE_CHOICES = [
        ('L', 'Licence'),
        ('M', 'Master'),
        ('D', 'Doctorat'),
    ]

    nom = models.CharField(max_length=100, verbose_name="Nom du cycle")
    code = models.CharField(max_length=5, choices=CODE_CHOICES, verbose_name="Code")
    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='academic_cycles',
        verbose_name="Établissement"
    )
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    class Meta:
        verbose_name = "Cycle académique"
        verbose_name_plural = "Cycles académiques"
        ordering = ['etablissement', 'ordre', 'code']
        unique_together = ['etablissement', 'code']

    def __str__(self):
        return f"{self.get_code_display()} - {self.etablissement.nom}"


class Department(models.Model):
    """
    Spécialité (ex: Transport, Mines, Informatique).
    Optionnel pour établissements supérieurs.
    """
    nom = models.CharField(max_length=255, verbose_name="Nom de la spécialité")
    domaine = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Domaine",
        help_text="Ex: Sciences et Technologies, Sciences Humaines"
    )
    mention = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Mention",
        help_text="Ex: Informatique, Logistique"
    )
    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='departments',
        verbose_name="Établissement"
    )
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    class Meta:
        verbose_name = "Spécialité"
        verbose_name_plural = "Spécialités"
        ordering = ['etablissement', 'ordre', 'nom']
        unique_together = ['etablissement', 'nom']

    def __str__(self):
        return f"{self.nom} - {self.etablissement.nom}"


class AcademicLevel(models.Model):
    """
    Niveau académique LMD : L1, L2, L3, M1, M2, D1, D2, D3.
    """
    CODE_CHOICES = [
        ('L1', 'L1 (Licence 1)'),
        ('L2', 'L2 (Licence 2)'),
        ('L3', 'L3 (Licence 3)'),
        ('M1', 'M1 (Master 1)'),
        ('M2', 'M2 (Master 2)'),
        ('D1', 'D1 (Doctorat 1)'),
        ('D2', 'D2 (Doctorat 2)'),
        ('D3', 'D3 (Doctorat 3)'),
    ]

    nom = models.CharField(max_length=50, verbose_name="Nom du niveau")
    code = models.CharField(max_length=10, choices=CODE_CHOICES, verbose_name="Code")
    cycle = models.ForeignKey(
        AcademicCycle,
        on_delete=models.CASCADE,
        related_name='academic_levels',
        verbose_name="Cycle académique"
    )
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    class Meta:
        verbose_name = "Niveau académique"
        verbose_name_plural = "Niveaux académiques"
        ordering = ['cycle', 'ordre', 'code']
        unique_together = ['cycle', 'code']

    def __str__(self):
        return f"{self.code} - {self.cycle.get_code_display()}"
