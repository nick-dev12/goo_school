# school_admin/model/personnel_administratif_model.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PersonnelAdministratif(AbstractUser):
    """
    Modèle représentant le personnel administratif d'un établissement
    """
    TYPE_FONCTION_CHOICES = [
        ('secretaire', 'Secrétaire / Service de scolarité'),
        ('surveillant_general', 'Surveillant Général (SG)'),
        ('censeur', 'Censeur'),
        ('administrateur', 'Administrateur'),
    ]
    
    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField(unique=True, verbose_name="Email professionnel")
    telephone = models.CharField(max_length=20, verbose_name="Téléphone")

    # Informations professionnelles
    fonction = models.CharField(max_length=50, choices=TYPE_FONCTION_CHOICES, verbose_name="Fonction")
    
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
    REQUIRED_FIELDS = ['nom', 'prenom', 'email']
    
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
        
   