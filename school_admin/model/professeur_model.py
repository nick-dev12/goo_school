# school_admin/model/professeur_model.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from .etablissement_model import Etablissement


class Professeur(AbstractUser):
    """
    Modèle pour les professeurs de l'établissement
    """
    
    # Types de matières enseignées
    MATIERE_CHOICES = [
        ('mathematiques', 'Mathématiques'),
        ('francais', 'Français'),
        ('anglais', 'Anglais'),
        ('histoire_geo', 'Histoire-Géographie'),
        ('sciences', 'Sciences'),
        ('physique', 'Physique'),
        ('chimie', 'Chimie'),
        ('biologie', 'Biologie'),
        ('sport', 'Éducation Physique et Sportive'),
        ('art', 'Arts Plastiques'),
        ('musique', 'Éducation Musicale'),
        ('technologie', 'Technologie'),
        ('informatique', 'Informatique'),
        ('philosophie', 'Philosophie'),
        ('economie', 'Économie'),
        ('autre', 'Autre'),
    ]
    
    # Niveaux d'enseignement
    NIVEAU_CHOICES = [
        ('maternelle', 'Maternelle'),
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('superieur', 'Supérieur'),
    ]
    
    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom de famille")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField(unique=True, verbose_name="Adresse email")
    telephone = models.CharField(max_length=20, verbose_name="Numéro de téléphone")
    
    # Informations professionnelles
    numero_employe = models.CharField(max_length=20, unique=True, verbose_name="Numéro d'employé")
    matiere_principale = models.ForeignKey(
        'Matiere',
        on_delete=models.CASCADE,
        related_name='professeurs_principaux',
        verbose_name="Matière principale"
    )
    matieres_secondaires = models.ManyToManyField(
        'Matiere',
        related_name='professeurs_secondaires',
        blank=True,
        verbose_name="Matières secondaires"
    )
    classes = models.ManyToManyField(
        'Classe',
        related_name='professeurs',
        blank=True,
        verbose_name="Classes affectées"
    )
    niveau_enseignement = models.CharField(
        max_length=20, 
        choices=NIVEAU_CHOICES, 
        verbose_name="Niveau d'enseignement"
    )
    
    
    # Informations administratives
    etablissement = models.ForeignKey(
        Etablissement, 
        on_delete=models.CASCADE, 
        related_name='professeurs',
        verbose_name="Établissement"
    )
    date_embauche = models.DateField(
        default=timezone.now, 
        verbose_name="Date d'embauche"
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    # Informations de connexion
    mot_de_passe_provisoire = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        verbose_name="Mot de passe provisoire"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom', 'telephone', 'matiere_principale', 'niveau_enseignement']
    
    class Meta:
        verbose_name = "Professeur"
        verbose_name_plural = "Professeurs"
        ordering = ['nom', 'prenom']
    
    def __str__(self):
        return f"{self.prenom} {self.nom}"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet du professeur"""
        return f"{self.prenom} {self.nom}"
    
    @property
    def matiere_display(self):
        """Retourne l'affichage de la matière principale"""
        return self.matiere_principale.nom if self.matiere_principale else "Non définie"
    
    @property
    def niveau_display(self):
        """Retourne l'affichage du niveau d'enseignement"""
        return dict(self.NIVEAU_CHOICES).get(self.niveau_enseignement, self.niveau_enseignement)
    
    def get_matieres_secondaires_display(self):
        """Retourne l'affichage des matières secondaires"""
        if not self.matieres_secondaires.exists():
            return "Aucune"
        matieres = [matiere.nom for matiere in self.matieres_secondaires.all()]
        return ", ".join(matieres)
    
    def save(self, *args, **kwargs):
        # Générer le username si pas défini
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)
