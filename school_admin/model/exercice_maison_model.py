"""
Modèle représentant un exercice de maison programmé par un enseignant.
"""

from django.db import models
from django.utils import timezone

from .professeur_model import Professeur
from .classe_model import Classe
from .matiere_model import Matiere
from .periode_model import PeriodeScolaire
from .etablissement_model import Etablissement


class ExerciceMaison(models.Model):
    """
    Exercice de maison à réaliser par les élèves d'une classe.
    """

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name="exercices_maison",
        verbose_name="Établissement",
    )

    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name="exercices_maison",
        verbose_name="Professeur",
    )

    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name="exercices_maison",
        verbose_name="Classe",
    )

    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name="exercices_maison",
        verbose_name="Matière",
    )

    periode_scolaire = models.ForeignKey(
        PeriodeScolaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exercices_maison",
        verbose_name="Période scolaire",
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exercices_maison_annee_scolaire',
        verbose_name="Année scolaire"
    )

    titre = models.CharField(
        max_length=255,
        verbose_name="Titre de l'exercice",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description / Consignes",
    )

    date_rendu = models.DateField(
        verbose_name="Date de rendu",
        help_text="Date à laquelle l'exercice doit être rendu",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
    )

    class Meta:
        verbose_name = "Exercice de maison"
        verbose_name_plural = "Exercices de maison"
        ordering = ["-date_rendu", "-date_creation"]
        indexes = [
            models.Index(fields=["classe", "matiere"]),
            models.Index(fields=["professeur", "date_rendu"]),
        ]

    def __str__(self) -> str:
        return f"{self.titre} - {self.classe.nom}"

    @property
    def est_en_retard(self) -> bool:
        """Indique si la date de rendu est dépassée."""
        return self.date_rendu < timezone.now().date()

