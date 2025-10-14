from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement
from .classe_model import Classe


class Matiere(models.Model):
    """
    Modèle pour les matières enseignées dans l'établissement
    """
    
    # Types de matières
    TYPE_MATIERE_CHOICES = [
        ('obligatoire', 'Matière obligatoire'),
        ('optionnelle', 'Matière optionnelle'),
        ('facultative', 'Matière facultative'),
        ('sport', 'Éducation physique et sportive'),
        ('art', 'Arts et culture'),
        ('technique', 'Matière technique'),
    ]
    
    # Niveaux d'enseignement
    NIVEAU_CHOICES = [
        ('maternelle', 'Maternelle'),
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('superieur', 'Supérieur'),
        ('tous', 'Tous niveaux'),
    ]
    
    # Informations de base
    nom = models.CharField(max_length=100, verbose_name="Nom de la matière")
    code = models.CharField(max_length=10, unique=True, verbose_name="Code de la matière")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    
    # Classification
    type_matiere = models.CharField(
        max_length=20, 
        choices=TYPE_MATIERE_CHOICES, 
        default='obligatoire',
        verbose_name="Type de matière"
    )
    niveau = models.CharField(
        max_length=20, 
        choices=NIVEAU_CHOICES, 
        default='tous',
        verbose_name="Niveau d'enseignement"
    )
    
    # Relations
    etablissement = models.ForeignKey(
        Etablissement, 
        on_delete=models.CASCADE, 
        related_name='matieres',
        verbose_name="Établissement"
    )
    classes = models.ManyToManyField(
        Classe,
        blank=True,
        related_name='matieres',
        verbose_name="Classes concernées"
    )
    
    # Informations administratives
    coefficient = models.DecimalField(
        max_digits=3, 
        decimal_places=1, 
        default=1.0,
        verbose_name="Coefficient"
    )
  
    
    # Statut
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Matière"
        verbose_name_plural = "Matières"
        ordering = ['nom']
        unique_together = ['nom', 'etablissement']
    
    def __str__(self):
        return f"{self.nom} ({self.code})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de la matière"""
        return f"{self.nom} ({self.code})"
    
    @property
    def type_display(self):
        """Retourne l'affichage du type de matière"""
        return dict(self.TYPE_MATIERE_CHOICES).get(self.type_matiere, self.type_matiere)
    
    @property
    def niveau_display(self):
        """Retourne l'affichage du niveau d'enseignement"""
        return dict(self.NIVEAU_CHOICES).get(self.niveau, self.niveau)
    
    def get_classes_display(self):
        """Retourne l'affichage des classes concernées"""
        if not self.classes.exists():
            return "Aucune classe assignée"
        classes = [classe.nom for classe in self.classes.all()]
        return ", ".join(classes)
    
    def get_classes_count(self):
        """Retourne le nombre de classes assignées"""
        return self.classes.count()
    
    def save(self, *args, **kwargs):
        # Générer le code si pas défini
        if not self.code:
            self.code = self.nom[:3].upper()
        super().save(*args, **kwargs)
