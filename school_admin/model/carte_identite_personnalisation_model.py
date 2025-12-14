# school_admin/model/carte_identite_personnalisation_model.py

from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement


class CarteIdentitePersonnalisation(models.Model):
    """
    Modèle pour stocker les personnalisations de l'en-tête des cartes d'identité
    """
    etablissement = models.OneToOneField(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='carte_identite_personnalisation',
        verbose_name="Établissement",
        help_text="Établissement concerné par cette personnalisation"
    )
    
    # Personnalisation de l'en-tête
    pays_nom = models.CharField(
        max_length=255,
        default="RÉPUBLIQUE DE [VOTRE PAYS]",
        verbose_name="Nom du pays",
        help_text="Nom du pays à afficher (ex: RÉPUBLIQUE DU SÉNÉGAL, RÉPUBLIQUE FRANÇAISE, etc.)"
    )
    
    devise_pays = models.CharField(
        max_length=255,
        default="[DEVISE NATIONALE]",
        verbose_name="Devise du pays",
        help_text="Devise nationale à afficher (ex: UN PEUPLE - UN BUT - UNE FOI, Liberté - Égalité - Fraternité, etc.)"
    )
    
    titre_carte = models.CharField(
        max_length=255,
        default="CARTE D'IDENTITÉ SCOLAIRE",
        verbose_name="Titre de la carte",
        help_text="Titre à afficher sur la carte (ex: CARTE D'IDENTITÉ SCOLAIRE)"
    )
    
    devise_etablissement = models.CharField(
        max_length=255,
        default="[DEVISE DE VOTRE ÉTABLISSEMENT]",
        verbose_name="Devise de l'établissement",
        help_text="Devise de l'établissement à afficher au verso de la carte (ex: Discipline - Travail - Réussite)"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Date de création de la personnalisation"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    class Meta:
        verbose_name = "Personnalisation de carte d'identité"
        verbose_name_plural = "Personnalisations de cartes d'identité"
        ordering = ['-date_modification']
    
    def __str__(self):
        return f"Personnalisation carte d'identité - {self.etablissement.nom}"
    
    @classmethod
    def get_or_create_for_etablissement(cls, etablissement):
        """
        Récupère ou crée une personnalisation pour un établissement
        """
        personnalisation, created = cls.objects.get_or_create(
            etablissement=etablissement,
            defaults={
                'pays_nom': "RÉPUBLIQUE DE [VOTRE PAYS]",
                'devise_pays': "[DEVISE NATIONALE]",
                'titre_carte': "CARTE D'IDENTITÉ SCOLAIRE",
                'devise_etablissement': "[DEVISE DE VOTRE ÉTABLISSEMENT]",
            }
        )
        return personnalisation
