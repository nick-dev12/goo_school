"""Modèle de notification pour les élèves."""

from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class NotificationEleve(models.Model):
    TYPE_NOTIFICATION_CHOICES = [
        ("annonce", "Annonce"),
        ("bulletin", "Bulletin"),
        ("note", "Note"),
        ("sanction", "Sanction"),
        ("evaluation", "Évaluation programmée"),
        ("information", "Information"),
    ]

    STATUT_CHOICES = [
        ("non_lu", "Non lu"),
        ("lu", "Lu"),
        ("archive", "Archivé"),
    ]

    eleve = models.ForeignKey(
        "Eleve",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Élève",
    )

    titre = models.CharField(max_length=180, verbose_name="Titre de la notification")
    message = models.TextField(verbose_name="Contenu de la notification")

    type_notification = models.CharField(
        max_length=20,
        choices=TYPE_NOTIFICATION_CHOICES,
        default="information",
        verbose_name="Type d'évènement",
    )

    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="non_lu",
        verbose_name="Statut",
    )

    date_evenement = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de l'évènement",
    )

    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de lecture",
    )

    donnees = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données supplémentaires",
    )

    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_eleves",
        verbose_name="Type de contenu source",
    )
    source_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Identifiant source",
    )
    source_object = GenericForeignKey("source_content_type", "source_object_id")

    notification_push_envoyee = models.BooleanField(
        default=False,
        verbose_name="Notification push envoyée",
    )

    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = "notifications_eleves"
        verbose_name = "Notification élève"
        verbose_name_plural = "Notifications élèves"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(fields=["eleve", "statut"]),
            models.Index(fields=["type_notification"]),
            models.Index(fields=["date_creation"]),
        ]

    def __str__(self):
        return f"Notification élève {self.eleve} ({self.get_type_notification_display()})"

    def marquer_comme_lue(self):
        if self.statut != "lu":
            self.statut = "lu"
            self.date_lecture = timezone.now()
            self.save(update_fields=["statut", "date_lecture", "date_modification"])
