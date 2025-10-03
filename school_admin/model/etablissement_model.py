# school_admin/model/etablissement_model.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

class Etablissement(AbstractUser):
    """
    Modèle représentant un établissement scolaire
    """
    TYPE_CHOICES = [
        ('primary', 'École Primaire'),
        ('collège', 'Collège'),
        ('lycée', 'Lycée'),
    ]
    
    # Code unique de l'établissement
    code_etablissement = models.CharField(max_length=12, unique=True, verbose_name="Code établissement")
    
    # Informations de l'établissement
    nom = models.CharField(max_length=255, verbose_name="Nom de l'établissement")
    adresse = models.CharField(max_length=255, verbose_name="Adresse")
    pays = models.CharField(max_length=255, verbose_name="Pays")
    ville = models.CharField(max_length=255, verbose_name="Ville")
    email = models.EmailField(unique=True, verbose_name="Email de l'établissement")
    telephone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Téléphone")
    type_etablissement = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type d'établissement")
    
    # Informations du directeur
    directeur_prenom = models.CharField(max_length=100, verbose_name="Prénom du directeur")
    directeur_nom = models.CharField(max_length=100, verbose_name="Nom du directeur")
    directeur_email = models.EmailField(unique=True, verbose_name="Email du directeur")
    directeur_telephone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Téléphone du directeur")
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    actif = models.BooleanField(default=True, verbose_name="Établissement actif")
    
    # Relation avec l'utilisateur qui a créé l'établissement (admin)
    cree_par = models.ForeignKey('school_admin.CompteUser', on_delete=models.SET_NULL, 
                                null=True, related_name='etablissements_crees',
                                verbose_name="Créé par")
    
    # Modules activés pour l'établissement
    module_gestion_eleves = models.BooleanField(default=False, verbose_name="Gestion des élèves")
    module_notes_evaluations = models.BooleanField(default=False, verbose_name="Notes et évaluations")
    module_emploi_temps = models.BooleanField(default=False, verbose_name="Emploi du temps")
    module_transport_scolaire = models.BooleanField(default=False, verbose_name="Transport scolaire")
    module_comptabilite = models.BooleanField(default=False, verbose_name="Comptabilité")
    module_gestion_personnel = models.BooleanField(default=False, verbose_name="Gestion du personnel")
    module_censeurs = models.BooleanField(default=False, verbose_name="Censeurs")
    module_surveillance = models.BooleanField(default=False, verbose_name="Surveillance et sécurité")
    module_cantine = models.BooleanField(default=False, verbose_name="Gestion de la cantine")
    module_bibliotheque = models.BooleanField(default=False, verbose_name="Gestion de la bibliothèque")
    module_communication = models.BooleanField(default=False, verbose_name="Communication parents")
    module_orientation = models.BooleanField(default=False, verbose_name="Orientation scolaire")
    module_sante = models.BooleanField(default=False, verbose_name="Suivi médical")
    module_activites = models.BooleanField(default=False, verbose_name="Activités extra-scolaires")
    module_formation = models.BooleanField(default=False, verbose_name="Formation continue")
    
    
    username = models.CharField(unique=True, max_length=100, verbose_name="Nom d'utilisateur", default="")
    USERNAME_FIELD = 'username'
    
    # Redéfinir les champs groups et user_permissions avec des related_name uniques
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this establishment belongs to.',
        related_name="etablissement_set",
        related_query_name="etablissement",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this establishment.',
        related_name="etablissement_set",
        related_query_name="etablissement",
    )
 
    
    class Meta:
        verbose_name = "Établissement"
        verbose_name_plural = "Établissements"
        ordering = ['-date_creation']
        
    def __str__(self):
        return f"{self.nom} ({self.get_type_etablissement_display()})"
