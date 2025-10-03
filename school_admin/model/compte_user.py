# school_admin/model/admin_model.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import datetime

class CompteUser(AbstractUser):
    # Champs personnalisés
    TYPE_COMPTE_CHOICES = [
        ('administrateur', 'Administrateur'),
        ('membre', 'Membre de l\'équipe'),
    ]

    DEPARTEMENT_CHOICES = [
        ('technique', 'Technique'),
        ('support', 'Support Client'),
        ('commercial', 'Commercial & Ventes'),
        ('marketing', 'Marketing'),
        ('direction', 'Direction'),
        ('comptable', 'Comptable'),
        ('ressources humaines', 'Ressources humaines'),
    ]
    
    FONCTION_CHOICES = [
        ('commercial', 'Commercial'),
        ('support', 'Support Client'),
        ('developpeur', 'Développeur'),
        ('marketing', 'Marketing'),
        ('administrateur', 'Administrateur'),
        ('comptable', 'Comptable'),
        ('ressources humaines', 'Ressources humaines'),
    ]



    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom", default="")
    prenom = models.CharField(max_length=100, verbose_name="Prénom", default="")
    email = models.EmailField(unique=True, verbose_name="Email professionnel")  # Pas de default vide pour unique
    telephone = models.CharField(max_length=20, verbose_name="Téléphone", default="")
    date_naissance = models.DateField(verbose_name="Date de naissance", default=datetime.date(1990, 1, 1))
    photo = models.ImageField(upload_to='admin_photos/', null=True, verbose_name="Photo de profil")

    # Informations professionnelles
    type_compte = models.CharField(max_length=50, choices=TYPE_COMPTE_CHOICES, verbose_name="Type de compte", default="")
    fonction = models.CharField(max_length=200, choices=FONCTION_CHOICES, verbose_name="Fonction dans l'entreprise", default="")
    departement = models.CharField(max_length=50, choices=DEPARTEMENT_CHOICES, verbose_name="Département", default="")
    # Le champ username est hérité de AbstractUser et doit être conservé
    # Nous le rendons non-unique car nous utilisons email comme identifiant principal
    username = models.CharField(unique=True, max_length=100, verbose_name="Nom d'utilisateur", default="")

    # Sécurité
    USERNAME_FIELD = 'username'  # L'email est l'identifiant principal
    REQUIRED_FIELDS = ['nom', 'prenom']  # Champs requis pour createsuperuser (sans email)
    
    # Redéfinir les champs groups et user_permissions avec des related_name uniques
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name="compteuser_set",
        related_query_name="compteuser",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="compteuser_set",
        related_query_name="compteuser",
    )
    
    # Forcer la migration en ajoutant un commentaire
    # Migration forcée pour corriger le schéma de base de données
    
    #nom complet
    

    def __str__(self):
        return f"{self.prenom} {self.nom} {self.username}"
    
    @property
    def initiales(self):
        """Retourne les initiales de l'utilisateur"""
        return f"{self.prenom[0] if self.prenom else ''}{self.nom[0] if self.nom else ''}".upper()
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de l'utilisateur"""
        return f"{self.prenom} {self.nom}"

    class Meta:
        verbose_name = "Compte"
        verbose_name_plural = "Comptes"
        app_label = "school_admin"  # Spécifier explicitement l'app_label