from django.db import models
from django.utils import timezone


class StandardsReussite(models.Model):
    etablissement = models.OneToOneField(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='standards_reussite',
        verbose_name="Établissement"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='standards_reussite',
        verbose_name="Année scolaire"
    )
    moyenne_passage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        verbose_name="Moyenne minimale de passage"
    )
    moyenne_redoublement = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=8,
        verbose_name="Moyenne de redoublement"
    )
    appreciation_conseil = models.TextField(
        blank=True,
        null=True,
        verbose_name="Appréciation du conseil de classe"
    )
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification"
    )

    class Meta:
        verbose_name = "Standards de réussite"
        verbose_name_plural = "Standards de réussite"

    def __str__(self):
        return f"Standards de réussite - {self.etablissement.nom}"


class AppreciationMatiereStandard(models.Model):
    standards = models.ForeignKey(
        StandardsReussite,
        on_delete=models.CASCADE,
        related_name='appreciations_matieres',
        verbose_name="Standards associés"
    )
    note_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Note minimale"
    )
    note_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Note maximale"
    )
    appreciation = models.CharField(
        max_length=150,
        verbose_name="Appréciation"
    )

    class Meta:
        verbose_name = "Palier d'appréciation"
        verbose_name_plural = "Paliers d'appréciation"
        ordering = ['note_min']

    def __str__(self):
        return f"{self.note_min} - {self.note_max} : {self.appreciation}"


class AppreciationConseilStandard(models.Model):
    standards = models.ForeignKey(
        StandardsReussite,
        on_delete=models.CASCADE,
        related_name='appreciations_conseil',
        verbose_name="Standards associés"
    )
    note_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Note minimale"
    )
    appreciation = models.CharField(
        max_length=200,
        verbose_name="Appréciation"
    )

    class Meta:
        verbose_name = "Appréciation conseil"
        verbose_name_plural = "Appréciations conseil"
        ordering = ['note_min']

    def __str__(self):
        return f"≥ {self.note_min} : {self.appreciation}"

