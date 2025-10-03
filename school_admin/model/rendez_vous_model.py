from django.db import models
from django.utils import timezone
from .compte_user import CompteUser


class RendezVous(models.Model):
    """
    Modèle pour les rendez-vous liés à un établissement
    """
    
    # On crée le champ "type_rdv" de type choix
    TYPE_RDV_CHOICES = [
        ('appel_telephonique', 'Appel téléphonique'),
        ('visite_site', 'Visite sur site'),
        ('presentation_online', 'Présentation en ligne'),
        ('dejeuner_affaires', 'Déjeuner d\'affaires'),
        ('salon_rencontre', 'Salon/Rencontre'),
        ('autre', 'Autre'),
    ]

    # On crée le champ "etablissement" de type foreign key et on importe le modèle Prospection
    etablissement = models.ForeignKey(
        'school_admin.Prospection', # On importe le modèle Prospection
        on_delete=models.CASCADE, # On supprime le rendez-vous si l'établissement est supprimé
        related_name='rendez_vous', # On nomme la relation "rendez_vous"
        verbose_name="Établissement"
    )
    # On crée le champ "type_rdv" de type choix
    type_rdv = models.CharField(
        max_length=50, 
        choices=TYPE_RDV_CHOICES, 
        verbose_name="Type de rendez-vous"
    )
    # On crée le champ "date_rdv" de type date
    date_rdv = models.DateField(verbose_name="Date du rendez-vous")
    heure_rdv = models.TimeField(verbose_name="Heure du rendez-vous")
    notes_rdv = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Notes sur le rendez-vous"
    )
    # On crée le champ "date_creation" de type date et heure
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    # On crée le champ "cree_par" de type foreign key et on importe le modèle CompteUser
    cree_par = models.ForeignKey(
        CompteUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name="Créé par"
    )
    # On crée le champ "actif" de type booléen
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Rendez-vous" # On nomme le modèle "Rendez-vous"
        verbose_name_plural = "Rendez-vous" # On nomme le pluriel "Rendez-vous"
        ordering = ['-date_creation'] # On ordonne les rendez-vous par date de création

    def __str__(self):
        # On retourne le type de rendez-vous - {date_rdv} à {heure_rdv} - {nom_etablissement}
        return f"{self.get_type_rdv_display()} - {self.date_rdv} à {self.heure_rdv} - {self.etablissement.nom_etablissement}"
