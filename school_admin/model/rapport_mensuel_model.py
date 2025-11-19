# school_admin/model/rapport_mensuel_model.py

from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator


class RapportMensuel(models.Model):
    """
    Modèle pour gérer les rapports mensuels générés
    """
    
    TYPE_RAPPORT_CHOICES = [
        ('complet', 'Rapport complet'),
        ('resume', 'Résumé exécutif'),
        ('financier', 'Rapport financier uniquement'),
        ('operational', 'Rapport opérationnel'),
    ]
    
    STATUT_CHOICES = [
        ('en_cours', 'En cours de génération'),
        ('genere', 'Généré'),
        ('erreur', 'Erreur'),
    ]
    
    FREQUENCE_CHOICES = [
        ('manuel', 'Manuel'),
        ('mensuel', 'Mensuel'),
        ('trimestriel', 'Trimestriel'),
        ('annuel', 'Annuel'),
    ]
    
    # Informations de base
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom du rapport"
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description"
    )
    
    type_rapport = models.CharField(
        max_length=20,
        choices=TYPE_RAPPORT_CHOICES,
        default='complet',
        verbose_name="Type de rapport"
    )
    
    # Période du rapport
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Mois du rapport (1-12)"
    )
    
    annee = models.IntegerField(
        verbose_name="Année",
        help_text="Année du rapport"
    )
    
    date_debut = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de début"
    )
    
    date_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin"
    )
    
    # Statut et génération
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_cours',
        verbose_name="Statut"
    )
    
    frequence = models.CharField(
        max_length=20,
        choices=FREQUENCE_CHOICES,
        default='manuel',
        verbose_name="Fréquence de génération"
    )
    
    # Fichier généré
    fichier_pdf = models.FileField(
        upload_to='rapports_mensuels/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        verbose_name="Fichier PDF"
    )
    
    taille_fichier = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Taille du fichier (octets)"
    )
    
    # Sections incluses
    inclure_resume_executif = models.BooleanField(
        default=True,
        verbose_name="Inclure résumé exécutif"
    )
    
    inclure_donnees_financieres = models.BooleanField(
        default=True,
        verbose_name="Inclure données financières"
    )
    
    inclure_analyse_etablissements = models.BooleanField(
        default=True,
        verbose_name="Inclure analyse des établissements"
    )
    
    inclure_graphiques = models.BooleanField(
        default=True,
        verbose_name="Inclure graphiques et tableaux"
    )
    
    inclure_recommandations = models.BooleanField(
        default=True,
        verbose_name="Inclure recommandations"
    )
    
    # Données du rapport (JSON)
    donnees_rapport = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Données du rapport"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    date_generation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de génération"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    temps_generation = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Temps de génération (secondes)"
    )
    
    class Meta:
        db_table = "rapports_mensuels"
        verbose_name = "Rapport mensuel"
        verbose_name_plural = "Rapports mensuels"
        ordering = ['-annee', '-mois', '-date_creation']
        indexes = [
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['statut']),
            models.Index(fields=['type_rapport']),
            models.Index(fields=['date_creation']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['mois', 'annee', 'type_rapport'], name='unique_rapport_periode_type')
        ]
    
    def __str__(self):
        return f"{self.nom} - {self.get_mois_display()} {self.annee}"
    
    def get_mois_display(self):
        """Retourne le nom du mois"""
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        return mois_noms.get(self.mois, f'Mois {self.mois}')
    
    def get_periode_display(self):
        """Retourne la période formatée"""
        return f"{self.get_mois_display()} {self.annee}"
    
    def get_taille_fichier_display(self):
        """Retourne la taille du fichier formatée"""
        if not self.taille_fichier:
            return "-"
        
        taille = self.taille_fichier
        for unit in ['B', 'KB', 'MB', 'GB']:
            if taille < 1024.0:
                return f"{taille:.1f} {unit}"
            taille /= 1024.0
        return f"{taille:.1f} TB"
    
    def marquer_comme_genere(self, fichier_pdf=None, temps_generation=None):
        """Marque le rapport comme généré"""
        self.statut = 'genere'
        self.date_generation = timezone.now()
        if fichier_pdf:
            self.fichier_pdf = fichier_pdf
            if hasattr(fichier_pdf, 'size'):
                self.taille_fichier = fichier_pdf.size
        if temps_generation:
            self.temps_generation = temps_generation
        self.save()

