# school_admin/model/classe_parcours_examen_model.py
"""
Catalogue national des examens / concours / voies d'accès qu'une classe LMD peut viser en parallèle
(ex. Licence 2 QHSE éligible au concours BTS, BT, etc.).
"""

from django.db import models


class CatalogueExamenConcours(models.Model):
    """
    Référentiel des types d'examens, concours ou certifications associables à une classe.
    """

    code = models.CharField(max_length=40, unique=True, verbose_name="Code")
    libelle = models.CharField(max_length=160, verbose_name="Libellé")
    description = models.TextField(blank=True, verbose_name="Description")
    categorie = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="Catégorie",
        help_text="ex. diplome_pro, concours, certification",
    )
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre d'affichage")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Examen / concours (catalogue)"
        verbose_name_plural = "Examens et concours (catalogue)"
        ordering = ['ordre', 'libelle']

    def __str__(self):
        return self.libelle


class ClasseParcoursExamen(models.Model):
    """
    Liaison : une classe peut préparer plusieurs examens ou concours (hors son diplôme LMD principal).
    """

    classe = models.ForeignKey(
        'school_admin.Classe',
        on_delete=models.CASCADE,
        related_name='liens_examens_concours',
        verbose_name="Classe",
    )
    option = models.ForeignKey(
        CatalogueExamenConcours,
        on_delete=models.CASCADE,
        related_name='liens_classes',
        verbose_name="Examen ou concours",
    )

    class Meta:
        verbose_name = "Classe — examen ou concours"
        verbose_name_plural = "Classes — examens et concours"
        unique_together = [['classe', 'option']]

    def __str__(self):
        return f"{self.classe} → {self.option}"
