"""
Modèle pour gérer les liens familiaux entre parents et élèves
"""
from django.db import models
from django.utils import timezone


class LienFamilial(models.Model):
    """
    Modèle pour gérer les liens entre parents et élèves
    Permet à plusieurs parents d'être liés à un même élève
    """
    STATUT_CHOICES = [
        ('valide', 'Validé'),
        ('en_attente', 'En attente de validation'),
        ('refuse', 'Refusé'),
    ]
    
    TYPE_LIEN_CHOICES = [
        ('mere', 'Mère'),
        ('pere', 'Père'),
        ('tuteur', 'Tuteur/Tutrice'),
    ]
    
    parent = models.ForeignKey(
        'Parent',
        on_delete=models.CASCADE,
        related_name='liens_enfants',
        verbose_name="Parent"
    )
    
    eleve = models.ForeignKey(
        'Eleve',
        on_delete=models.CASCADE,
        related_name='liens_parents',
        verbose_name="Élève"
    )
    
    type_lien = models.CharField(
        max_length=10,
        choices=TYPE_LIEN_CHOICES,
        verbose_name="Type de lien familial"
    )
    
    statut = models.CharField(
        max_length=15,
        choices=STATUT_CHOICES,
        default='valide',
        verbose_name="Statut"
    )
    
    est_inscripteur = models.BooleanField(
        default=False,
        verbose_name="Parent inscripteur",
        help_text="Indique si c'est le parent qui a inscrit l'élève initialement"
    )
    
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    class Meta:
        unique_together = ['parent', 'eleve']
        verbose_name = "Lien familial"
        verbose_name_plural = "Liens familiaux"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.parent.nom_complet} ({self.get_type_lien_display()}) → {self.eleve.nom_complet}"
    
    def valider(self):
        """Valide le lien familial"""
        self.statut = 'valide'
        self.date_validation = timezone.now()
        self.save()
    
    def refuser(self):
        """Refuse le lien familial"""
        self.statut = 'refuse'
        self.actif = False
        self.save()

