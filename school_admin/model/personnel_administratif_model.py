# school_admin/model/personnel_administratif_model.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PersonnelAdministratif(AbstractUser):
    """
    Modèle représentant le personnel administratif d'un établissement
    """
    # Fonctions adaptées aux établissements sénégalais
    TYPE_FONCTION_CHOICES = [
        # Direction - École Primaire
        ('directeur_adjoint_primaire', 'Directeur Adjoint (École Primaire)'),
        
        # Direction - Collège
        ('principal_adjoint', 'Principal Adjoint (Collège)'),
        
        # Direction - Lycée
        ('proviseur_adjoint', 'Proviseur Adjoint (Lycée)'),
        
        # Direction - Mixte
        ('directeur_principal', 'Directeur Principal (Établissement Mixte)'),
        ('directeur_section_primaire', 'Directeur de Section Primaire'),
        ('principal_section_college', 'Principal de Section Collège'),
        ('proviseur_section_lycee', 'Proviseur de Section Lycée'),
        
        # Administration
        ('secretaire_principal', 'Secrétaire Principal'),
        ('gestionnaire', 'Gestionnaire'),
        
        # Pédagogie - Censeurs
        ('censeur', 'Censeur'),
        ('censeur_etudes', 'Censeur des Études (Collèges & Lycées)'),
        ('censeur_adjoint', 'Censeur Adjoint (Lycées)'),
        ('censeur_premier_cycle', 'Censeur du Premier Cycle (6e à 3e)'),
        ('censeur_second_cycle', 'Censeur du Second Cycle (2nde à Tle)'),
        ('censeur_pedagogie', 'Censeur chargé de la Pédagogie'),
        ('censeur_vie_scolaire', 'Censeur chargé de la Vie Scolaire'),
        
        # Vie Scolaire
        ('surveillant_general', 'Surveillant Général'),
        ('secretaire_vie_scolaire', 'Secrétaire de Vie Scolaire'),
        
        # Autres
        ('administrateur', 'Administrateur Système'),
    ]
    
    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField(unique=True, blank=True, null=True, verbose_name="Email professionnel")
    telephone = models.CharField(max_length=20, verbose_name="Téléphone")

    # Informations professionnelles
    fonction = models.CharField(max_length=50, choices=TYPE_FONCTION_CHOICES, verbose_name="Fonction")
    
    # Permissions (pour usage futur)
    permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Permissions"
    )
    
    # Mot de passe provisoire (en clair, pour usage administratif uniquement)
    mot_de_passe_provisoire = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name="Mot de passe provisoire (en clair)"
    )
    
    # Relation avec l'établissement
    etablissement = models.ForeignKey(
        'school_admin.Etablissement', 
        on_delete=models.CASCADE,
        related_name='personnel_administratif',
        verbose_name="Établissement"
    )
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    numero_employe = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Numéro d'employé")
    
    # Configuration d'authentification
    username = models.CharField(unique=True, max_length=100, verbose_name="Nom d'utilisateur")
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nom', 'prenom']
    
    # Ajouter les champs password et is_active pour l'authentification
    password = models.CharField(max_length=128, verbose_name="Mot de passe")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    is_staff = models.BooleanField(default=False, verbose_name="Staff")
    is_superuser = models.BooleanField(default=False, verbose_name="Super utilisateur")
    last_login = models.DateTimeField(blank=True, null=True, verbose_name="Dernière connexion")
    date_joined = models.DateTimeField(default=timezone.now, verbose_name="Date d'inscription")
    
    # Relations ManyToMany avec related_name uniques
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name="personnel_administratif_set",
        related_query_name="personnel_administratif",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name="personnel_administratif_set",
        related_query_name="personnel_administratif",
    )
    
    
    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.get_fonction_display()}"
    
    @property
    def initiales(self):
        """Retourne les initiales de l'utilisateur"""
        return f"{self.prenom[0] if self.prenom else ''}{self.nom[0] if self.nom else ''}".upper()
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de l'utilisateur"""
        return f"{self.prenom} {self.nom}"

    class Meta:
        verbose_name = "Personnel Administratif"
        verbose_name_plural = "Personnel Administratif"
        ordering = ['-date_creation']
        
   