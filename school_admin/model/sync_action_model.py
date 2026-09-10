"""
Journal des actions de synchronisation hors ligne.
Garantit l'idempotence via client_uuid (replay sans doublon).
"""
from django.db import models


class SyncAction(models.Model):
    client_uuid = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="UUID client",
    )
    resource = models.CharField(max_length=64, verbose_name="Ressource")
    action = models.CharField(max_length=16, default="CREATE", verbose_name="Action")
    utilisateur_id = models.PositiveIntegerField(verbose_name="ID utilisateur")
    utilisateur_type = models.CharField(
        max_length=32,
        default="professeur",
        verbose_name="Type utilisateur",
    )
    resultat = models.JSONField(default=dict, blank=True, verbose_name="Résultat")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        verbose_name = "Action de synchronisation"
        verbose_name_plural = "Actions de synchronisation"
        ordering = ["-date_creation"]
        indexes = [
            models.Index(fields=["utilisateur_type", "utilisateur_id"]),
            models.Index(fields=["resource", "date_creation"]),
        ]

    def __str__(self):
        return f"{self.resource} {self.client_uuid}"
