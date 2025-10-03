from django.db import models
from django.utils import timezone
from .compte_user import CompteUser


class CompteRendu(models.Model):
    """
    Modèle pour les comptes rendus de visite liés à un établissement
    """
    
    # On crée le champ "etablissement" de type foreign key et on importe le modèle Prospection
    etablissement = models.ForeignKey(
        'school_admin.Prospection', # On importe le modèle Prospection
        on_delete=models.CASCADE, # On supprime le compte rendu si l'établissement est supprimé
        related_name='comptes_rendus', # On nomme la relation "comptes_rendus"
        verbose_name="Établissement" # On nomme le champ "Établissement"
    )
    
    # On crée le champ "rendez_vous" de type foreign key et on importe le modèle RendezVous
    rendez_vous = models.ForeignKey(
        'school_admin.RendezVous', # On importe le modèle RendezVous
        on_delete=models.SET_NULL, # On garde le compte rendu même si le RDV est supprimé
        null=True, # Le RDV peut être null (compte rendu sans RDV programmé)
        blank=True, # Le champ peut être vide
        related_name='compte_rendu', # On nomme la relation "compte_rendu"
        verbose_name="Rendez-vous associé" # On nomme le champ "Rendez-vous associé"
    )
    
    # On crée le champ "titre" de type texte court
    titre = models.CharField(
        max_length=255, 
        verbose_name="Titre du compte rendu"
    )
    
    # On crée le champ "contenu" de type texte long
    contenu = models.TextField(
        verbose_name="Contenu du compte rendu"
    )
    
    # On crée le champ "date_visite" de type date
    date_visite = models.DateField(
        verbose_name="Date de la visite"
    )
    
    
    # On crée le champ "satisfaction_client" de type choix
    SATISFACTION_CHOICES = [
        ('tres_satisfait', 'Très satisfait'),
        ('satisfait', 'Satisfait'),
        ('neutre', 'Neutre'),
        ('peu_satisfait', 'Peu satisfait'),
        ('pas_satisfait', 'Pas satisfait'),
    ]
    
    satisfaction_client = models.CharField(
        max_length=20,
        choices=SATISFACTION_CHOICES,
        verbose_name="Satisfaction du client"
    )
    
    # On crée le champ "date_creation" de type date et heure
    date_creation = models.DateTimeField(
        default=timezone.now, 
        verbose_name="Date de création"
    )
    
    # On crée le champ "cree_par" de type foreign key et on importe le modèle CompteUser
    cree_par = models.ForeignKey(
        CompteUser, # On importe le modèle CompteUser
        on_delete=models.SET_NULL, # On garde le compte rendu même si l'utilisateur est supprimé
        null=True, # L'utilisateur peut être null
        verbose_name="Créé par"
    )
    
    # On crée le champ "actif" de type booléen
    actif = models.BooleanField(
        default=True, 
        verbose_name="Actif"
    )

    class Meta:
        verbose_name = "Compte rendu" # On nomme le modèle "Compte rendu"
        verbose_name_plural = "Comptes rendus" # On nomme le pluriel "Comptes rendus"
        ordering = ['-date_creation'] # On ordonne les comptes rendus par date de création

    def __str__(self):
        # On retourne le titre du compte rendu - {date_visite} - {nom_etablissement}
        return f"{self.titre} - {self.date_visite} - {self.etablissement.nom_etablissement}"
