"""Rappels automatiques : journal des envois, réglages par établissement, notifications du personnel."""
from datetime import time

from django.db import models
from django.utils import timezone


class RappelEnvoye(models.Model):
    """Un rappel émis pour une personne, une situation et un seuil : jamais deux fois."""

    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    etablissement = models.ForeignKey('Etablissement', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='rappels_envoyes')
    key = models.CharField(max_length=190)
    stage = models.CharField(max_length=40)
    code = models.CharField(max_length=60, blank=True)
    version = models.CharField(max_length=64, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    titre = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['content_type', 'object_id', 'key', 'stage'],
                                               name='unique_rappel_envoye')]
        indexes = [models.Index(fields=['content_type', 'object_id', 'created_at'], name='rappel_owner_date_idx')]
        ordering = ['-created_at']


class ParametresRappels(models.Model):
    """Réglages des rappels automatiques d'un établissement."""

    etablissement = models.OneToOneField('Etablissement', on_delete=models.CASCADE, related_name='parametres_rappels')
    actif = models.BooleanField(default=True, verbose_name="Rappels automatiques activés")
    debut_heures_calmes = models.TimeField(default=time(21, 0))
    fin_heures_calmes = models.TimeField(default=time(6, 30))
    plafond_quotidien = models.PositiveSmallIntegerField(default=4)
    familles_desactivees = models.JSONField(default=list, blank=True)
    rappel_cours_demain = models.BooleanField(default=False, verbose_name="Rappeler les cours du lendemain")
    dernier_passage = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Paramètres des rappels"
        verbose_name_plural = "Paramètres des rappels"

    def __str__(self):
        return f"Rappels — {self.etablissement}"


class NotificationPersonnel(models.Model):
    """Notification destinée à un membre du personnel administratif."""

    personnel = models.ForeignKey('PersonnelAdministratif', on_delete=models.CASCADE,
                                  related_name='notifications_personnel')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='notifications_personnel')
    titre = models.CharField(max_length=180)
    message = models.TextField()
    type_notification = models.CharField(max_length=20, default='rappel',
                                         choices=[('rappel', 'Rappel'), ('information', 'Information générale')])
    statut = models.CharField(max_length=10, default='non_lu',
                              choices=[('non_lu', 'Non lu'), ('lu', 'Lu'), ('archive', 'Archivé')])
    lu = models.BooleanField(default=False)
    date_evenement = models.DateTimeField(default=timezone.now)
    date_lecture = models.DateTimeField(null=True, blank=True)
    donnees = models.JSONField(default=dict, blank=True)
    notification_push_envoyee = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_evenement']
        indexes = [models.Index(fields=['personnel', 'lu'], name='notif_personnel_lu_idx')]

    def __str__(self):
        return f"{self.titre} → {self.personnel}"

    def marquer_comme_lu(self):
        if not self.lu:
            self.lu = True
            self.statut = 'lu'
            self.date_lecture = timezone.now()
            self.save(update_fields=['lu', 'statut', 'date_lecture', 'date_modification'])
