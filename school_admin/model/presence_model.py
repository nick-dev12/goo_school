"""
Modèle pour la gestion des présences/absences des élèves
Permet de suivre quotidiennement la présence de chaque élève dans chaque classe
"""

from django.db import models
from django.utils import timezone
from .eleve_model import Eleve
from .classe_model import Classe
from .professeur_model import Professeur
from .etablissement_model import Etablissement


class Presence(models.Model):
    """
    Modèle pour enregistrer la présence/absence quotidienne d'un élève
    Une entrée par élève par jour
    """
    
    STATUT_CHOICES = [
        ('present', 'Présent'),
        ('absent', 'Absent'),
        ('retard', 'Retard'),
        ('absent_justifie', 'Absent Justifié'),
    ]
    
    TYPE_JUSTIFICATIF_CHOICES = [
        ('certificat_medical', 'Certificat médical'),
        ('raison_familiale', 'Raison familiale'),
        ('deces_famille', 'Décès dans la famille'),
        ('maladie', 'Maladie (sans certificat)'),
        ('rendez_vous_medical', 'Rendez-vous médical'),
        ('evenement_religieux', 'Événement religieux'),
        ('probleme_transport', 'Problème de transport'),
        ('autre', 'Autre raison'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='presences',
        verbose_name="Élève"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='presences',
        verbose_name="Classe"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='presences_prises',
        verbose_name="Professeur"
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='presences',
        verbose_name="Établissement"
    )
    date = models.DateField(
        default=timezone.now,
        verbose_name="Date",
        db_index=True
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='present',
        verbose_name="Statut"
    )
    remarque = models.TextField(
        blank=True,
        null=True,
        verbose_name="Remarque"
    )
    type_justificatif = models.CharField(
        max_length=30,
        choices=TYPE_JUSTIFICATIF_CHOICES,
        blank=True,
        null=True,
        verbose_name="Type de justificatif"
    )
    justificatif_valide = models.BooleanField(
        default=False,
        verbose_name="Justificatif validé"
    )
    date_justification = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date de justification"
    )
    heure_enregistrement = models.TimeField(
        auto_now_add=True,
        verbose_name="Heure d'enregistrement"
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
        verbose_name = "Présence"
        verbose_name_plural = "Présences"
        unique_together = ('eleve', 'classe', 'date')
        ordering = ['-date', 'eleve__nom', 'eleve__prenom']
        indexes = [
            models.Index(fields=['date', 'classe']),
            models.Index(fields=['eleve', 'date']),
        ]
    
    def __str__(self):
        return f"{self.eleve.nom_complet} - {self.get_statut_display()} - {self.date}"
    
    @property
    def est_absent(self):
        """Retourne True si l'élève est absent (justifié ou non)"""
        return self.statut in ['absent', 'absent_justifie']
    
    @staticmethod
    def get_nombre_absences(eleve, date_debut=None, date_fin=None):
        """
        Retourne le nombre d'absences NON JUSTIFIÉES d'un élève sur une période
        Si aucune période n'est spécifiée, retourne le total
        """
        queryset = Presence.objects.filter(
            eleve=eleve,
            statut='absent'
        )
        
        if date_debut:
            queryset = queryset.filter(date__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date__lte=date_fin)
        
        return queryset.count()
    
    @staticmethod
    def get_taux_presence(eleve, classe, date_debut=None, date_fin=None):
        """
        Calcule le taux de présence d'un élève dans une classe
        Retourne un pourcentage (0-100)
        """
        queryset = Presence.objects.filter(eleve=eleve, classe=classe)
        
        if date_debut:
            queryset = queryset.filter(date__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date__lte=date_fin)
        
        total = queryset.count()
        if total == 0:
            return None
        
        presents = queryset.filter(statut='present').count()
        return round((presents / total) * 100, 2)


class ListePresence(models.Model):
    """
    Modèle pour regrouper les présences d'une classe à une date donnée
    Permet de marquer une liste comme validée/soumise
    """
    
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='listes_presences',
        verbose_name="Classe"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='listes_presences',
        verbose_name="Professeur"
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='listes_presences',
        verbose_name="Établissement"
    )
    date = models.DateField(
        default=timezone.now,
        verbose_name="Date",
        db_index=True
    )
    validee = models.BooleanField(
        default=False,
        verbose_name="Liste validée"
    )
    date_validation = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date de validation"
    )
    nombre_presents = models.IntegerField(
        default=0,
        verbose_name="Nombre de présents"
    )
    nombre_absents = models.IntegerField(
        default=0,
        verbose_name="Nombre d'absents"
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
        verbose_name = "Liste de présence"
        verbose_name_plural = "Listes de présence"
        unique_together = ('classe', 'date')
        ordering = ['-date', 'classe__nom']
    
    def __str__(self):
        return f"Présence {self.classe.nom} - {self.date} ({'Validée' if self.validee else 'En cours'})"
    
    def valider(self):
        """Marque la liste comme validée et enregistre la date"""
        if not self.validee:
            self.validee = True
            self.date_validation = timezone.now()
            self.calculer_statistiques()
            self.save()
    
    def calculer_statistiques(self):
        """Calcule le nombre de présents et absents pour cette liste"""
        presences = Presence.objects.filter(classe=self.classe, date=self.date)
        self.nombre_presents = presences.filter(statut='present').count()
        self.nombre_absents = presences.filter(statut__in=['absent', 'absent_justifie']).count()
        self.save()

