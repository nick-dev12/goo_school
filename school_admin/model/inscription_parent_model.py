"""
Modèle pour archiver les inscriptions de parents par année scolaire
"""
from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement
from .annee_scolaire_model import AnneeScolaire


class InscriptionParent(models.Model):
    """
    Modèle pour archiver les inscriptions de parents par année scolaire
    Représente une inscription de parent pour une année scolaire spécifique
    """
    
    # Relation avec l'année scolaire (OBLIGATOIRE)
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='inscriptions_parents',
        verbose_name="Année scolaire",
        help_text="Année scolaire de l'inscription"
    )
    
    # Référence au parent (si le parent existe toujours dans le système)
    parent = models.ForeignKey(
        'Parent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inscriptions',
        verbose_name="Parent",
        help_text="Référence au parent dans le système (peut être null si le parent a été supprimé)"
    )
    
    # Informations personnelles (copiées depuis Parent)
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de famille"
    )
    
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom"
    )
    
    telephone = models.CharField(
        max_length=20,
        verbose_name="Téléphone"
    )
    
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
        help_text="Adresse email du parent"
    )
    
    matricule_parental = models.CharField(
        max_length=20,
        verbose_name="Matricule parental",
        help_text="Identifiant unique du parent (ex: BPP2025001)"
    )
    
    TYPE_PARENT_CHOICES = [
        ('mere', 'Mère'),
        ('pere', 'Père'),
        ('tuteur', 'Tuteur/Tutrice'),
    ]
    type_parent = models.CharField(
        max_length=10,
        choices=TYPE_PARENT_CHOICES,
        verbose_name="Type de parent"
    )
    
    adresse = models.TextField(
        verbose_name="Adresse",
        blank=True,
        null=True
    )
    
    profession = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Profession"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='inscriptions_parents',
        verbose_name="Établissement"
    )
    
    # Métadonnées
    date_inscription = models.DateField(
        verbose_name="Date d'inscription",
        help_text="Date d'inscription du parent"
    )
    
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création",
        help_text="Date de création de l'enregistrement d'inscription"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    class Meta:
        verbose_name = "Inscription de parent"
        verbose_name_plural = "Inscriptions de parents"
        ordering = ['-annee_scolaire', '-date_inscription', 'nom', 'prenom']
        unique_together = ['annee_scolaire', 'matricule_parental']
        indexes = [
            models.Index(fields=['annee_scolaire', 'etablissement']),
            models.Index(fields=['matricule_parental']),
            models.Index(fields=['date_inscription']),
        ]
    
    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.annee_scolaire.libelle} ({self.matricule_parental})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet du parent"""
        return f"{self.prenom} {self.nom}"
    
    def get_type_parent_display(self):
        """Retourne l'affichage du type de parent"""
        return dict(self.TYPE_PARENT_CHOICES).get(self.type_parent, self.type_parent)
    
    def clean(self):
        """Validation personnalisée"""
        from django.core.exceptions import ValidationError
        
        # Vérifier que l'établissement correspond à celui de l'année scolaire
        if self.annee_scolaire and self.etablissement:
            if self.annee_scolaire.etablissement != self.etablissement:
                raise ValidationError("L'établissement doit correspondre à celui de l'année scolaire.")
    
    def save(self, *args, **kwargs):
        """Surcharge du save pour exécuter la validation"""
        self.full_clean()
        super().save(*args, **kwargs)

