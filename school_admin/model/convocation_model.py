from django.db import models
from .eleve_model import Eleve
from .etablissement_model import Etablissement


class Convocation(models.Model):
    """
    Modèle pour enregistrer les convocations des élèves
    """
    
    # Relations
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='convocations',
        verbose_name="Élève",
        help_text="Élève concerné par la convocation"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='convocations',
        verbose_name="Établissement",
        help_text="Établissement émetteur de la convocation"
    )
    
    # Informations de la convocation
    objet = models.CharField(
        max_length=200,
        verbose_name="Objet",
        help_text="Objet de la convocation"
    )
    
    motif = models.TextField(
        verbose_name="Motif",
        help_text="Motif détaillé de la convocation"
    )
    
    date_convocation = models.DateField(
        verbose_name="Date de convocation",
        help_text="Date du rendez-vous"
    )
    
    heure_convocation = models.TimeField(
        verbose_name="Heure de convocation",
        help_text="Heure du rendez-vous"
    )
    
    lieu = models.CharField(
        max_length=200,
        default="Bureau du Directeur",
        verbose_name="Lieu",
        help_text="Lieu du rendez-vous"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Date de création de la convocation"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('vue', 'Vue par le parent'),
        ('honoree', 'Honorée'),
        ('non_honoree', 'Non honorée'),
    ]
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut",
        help_text="Statut de la convocation"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Convocation active ou archivée"
    )
    
    convocation_classe = models.BooleanField(
        default=False,
        verbose_name="Convocation de classe",
        help_text="Indique si cette convocation concerne toute une classe"
    )
    
    class Meta:
        verbose_name = "Convocation"
        verbose_name_plural = "Convocations"
        ordering = ['-date_convocation', '-heure_convocation']
        indexes = [
            models.Index(fields=['eleve', 'date_convocation']),
            models.Index(fields=['etablissement', 'date_convocation']),
            models.Index(fields=['statut']),
        ]
    
    def __str__(self):
        return f"Convocation - {self.eleve.nom_complet} - {self.date_convocation}"
    
    @property
    def est_passee(self):
        """Vérifie si la date de convocation est passée"""
        from datetime import datetime, date
        return self.date_convocation < date.today()

