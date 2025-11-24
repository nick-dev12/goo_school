from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation


class JustificationNote(models.Model):
    """
    Demande de justification (ou rectification) d'une note.
    Les enseignants soumettent une demande qui est ensuite validée
    par la direction. Une fois validée, la note d'origine est mise à jour.
    """

    STATUT_EN_ATTENTE = "en_attente"
    STATUT_VALIDEE = "validee"
    STATUT_REFUSEE = "refusee"

    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE, "En attente"),
        (STATUT_VALIDEE, "Validée"),
        (STATUT_REFUSEE, "Refusée"),
    ]

    note = models.ForeignKey(
        "Note",
        on_delete=models.CASCADE,
        related_name="justifications",
        null=True,
        blank=True,
        verbose_name="Note (collège / lycée)",
    )
    note_primaire = models.ForeignKey(
        "NotePrimaire",
        on_delete=models.CASCADE,
        related_name="justifications",
        null=True,
        blank=True,
        verbose_name="Note (primaire)",
    )
    classe = models.ForeignKey(
        "Classe",
        on_delete=models.CASCADE,
        related_name="justifications_notes",
        verbose_name="Classe",
    )
    evaluation = models.ForeignKey(
        "Evaluation",
        on_delete=models.SET_NULL,
        related_name="justifications_notes",
        null=True,
        blank=True,
        verbose_name="Évaluation (secondaire)",
    )
    evaluation_primaire = models.ForeignKey(
        "EvaluationPrimaire",
        on_delete=models.SET_NULL,
        related_name="justifications_notes",
        null=True,
        blank=True,
        verbose_name="Évaluation (primaire)",
    )
    eleve = models.ForeignKey(
        "Eleve",
        on_delete=models.CASCADE,
        related_name="justifications_notes",
        verbose_name="Élève",
    )
    matiere = models.ForeignKey(
        "Matiere",
        on_delete=models.SET_NULL,
        related_name="justifications_notes",
        null=True,
        blank=True,
        verbose_name="Matière",
    )
    professeur = models.ForeignKey(
        "Professeur",
        on_delete=models.CASCADE,
        related_name="justifications_notes",
        verbose_name="Professeur demandeur",
    )
    etablissement = models.ForeignKey(
        "Etablissement",
        on_delete=models.CASCADE,
        related_name="justifications_notes",
        verbose_name="Établissement",
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='justifications_notes_annee_scolaire',
        verbose_name="Année scolaire"
    )
    ancienne_note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valeur initiale",
    )
    nouvelle_note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Valeur proposée",
    )
    motif = models.CharField(
        max_length=255,
        verbose_name="Motif de la justification",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Détails complémentaires",
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default=STATUT_EN_ATTENTE,
        verbose_name="Statut",
    )
    commentaire_direction = models.TextField(
        blank=True,
        verbose_name="Commentaire de la direction",
    )
    valide_par = models.ForeignKey(
        "Etablissement",
        on_delete=models.SET_NULL,
        related_name="justifications_notes_validees",
        null=True,
        blank=True,
        verbose_name="Validé par",
    )
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation / refus",
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
    )

    class Meta:
        verbose_name = "Justification de note"
        verbose_name_plural = "Justifications de notes"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["classe", "statut"]),
            models.Index(fields=["professeur", "statut"]),
        ]

    def clean(self):
        super().clean()

        if not self.note and not self.note_primaire:
            raise ValidationError("Une justification doit cibler une note.")

        if self.note and self.note_primaire:
            raise ValidationError("Une justification ne peut cibler qu'un seul type de note.")

        if self.nouvelle_note is None:
            raise ValidationError({"nouvelle_note": "Veuillez proposer une nouvelle valeur pour la note."})

        try:
            nouvelle_note_decimal = Decimal(str(self.nouvelle_note))
        except (InvalidOperation, TypeError):
            raise ValidationError({"nouvelle_note": "La note proposée est invalide."})

        bareme = None
        if self.note and self.note.evaluation:
            bareme = self.note.evaluation.bareme
        elif self.note_primaire and self.note_primaire.evaluation_primaire:
            bareme = self.note_primaire.evaluation_primaire.bareme

        if bareme is not None and nouvelle_note_decimal > bareme:
            raise ValidationError({"nouvelle_note": f"La note proposée ne peut pas dépasser le barème ({bareme})."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def derniere_valeur(self):
        return self.nouvelle_note if self.statut == self.STATUT_VALIDEE else self.ancienne_note


