"""
Modèle de notification dédié aux parents d'élèves.
Permet de suivre toutes les alertes envoyées pour chacun des enfants suivis.
"""

from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class NotificationParent(models.Model):
    """Notification envoyée à un parent pour un évènement concernant un enfant."""

    TYPE_NOTIFICATION_CHOICES = [
        ("presence", "Présence / Absence"),
        ("note", "Note individuelle"),
        ("moyenne", "Moyenne de période"),
        ("bulletin", "Bulletin disponible"),
        ("sanction", "Sanction appliquée"),
        ("evaluation", "Évaluation programmée"),
        ("information", "Information générale"),
    ]

    STATUT_CHOICES = [
        ("non_lu", "Non lu"),
        ("lu", "Lu"),
        ("archive", "Archivé"),
    ]

    parent = models.ForeignKey(
        "Parent",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Parent"
    )

    eleve = models.ForeignKey(
        "Eleve",
        on_delete=models.CASCADE,
        related_name="notifications_parents",
        verbose_name="Élève"
    )

    titre = models.CharField(
        max_length=180,
        verbose_name="Titre de la notification"
    )

    message = models.TextField(
        verbose_name="Contenu de la notification"
    )

    type_notification = models.CharField(
        max_length=20,
        choices=TYPE_NOTIFICATION_CHOICES,
        verbose_name="Type d'évènement"
    )

    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="non_lu",
        verbose_name="Statut"
    )

    date_evenement = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de l'évènement"
    )

    date_lecture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de lecture"
    )

    donnees = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données supplémentaires"
    )

    # Lien optionnel vers l'objet source (présence, note, bulletin, sanction, etc.)
    source_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_parents",
        verbose_name="Type de contenu source"
    )
    source_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Identifiant source"
    )
    source_object = GenericForeignKey("source_content_type", "source_object_id")

    # Indicateurs techniques
    notification_push_envoyee = models.BooleanField(
        default=False,
        verbose_name="Notification push envoyée"
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
        db_table = "notifications_parents"
        verbose_name = "Notification parent"
        verbose_name_plural = "Notifications parents"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(fields=["parent", "statut"]),
            models.Index(fields=["eleve", "type_notification"]),
            models.Index(fields=["date_creation"]),
        ]

    def __str__(self):
        return f"Notification parent {self.parent} → {self.eleve} ({self.get_type_notification_display()})"

    def marquer_comme_lue(self):
        """Met à jour le statut de la notification en la marquant comme lue."""
        if self.statut != "lu":
            self.statut = "lu"
            self.date_lecture = timezone.now()
            self.save(update_fields=["statut", "date_lecture", "date_modification"])


