from django.db import models
from django.utils import timezone
from .compte_user import CompteUser


class Prospection(models.Model):
    
    # On crée le champ "type_etablissement" de type choix
    TYPE_CHOICES = [
        ('primaire', 'École primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('universite', 'Université'),
        ('autre', 'Autre'),
    ]
    
    # On crée le champ "genre_etablissement" de type choix
    GENRE_CHOICES = [
        ('public', 'Public'),
        ('prive', 'Privé'),
        ('confessionnel', 'Confessionnel'),
    ]
    
    # On crée le champ "statut_etablissement" de type choix
    STATUT_CHOICES = [
        ('prospect', 'Prospect'),
        ('contacte', 'Contacté'),
        ('rendez_vous', 'Rendez-vous'),
        ('contrat_signe', 'Contrat signé'),
        ('non_interesse', 'Non intéressé'),
        ('interesse', 'Intéressé'),
        ('negociation', 'En négociation'),
        ('devis_envoye', 'Devis envoyé'),
        ('contrat_signe', 'Contrat signé'),
    ]
       
    
    # On crée le champ "potentiel_etablissement" de type choix
    POTENTIEL_CHOICES = [
        ('faible', 'Faible'),
        ('moyen', 'Moyen'),
        ('eleve', 'Élevé'),
        ('tres_eleve', 'Très élevé'),
    ]
    
    # On crée le champ "priorite_etablissement" de type choix
    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('normale', 'Normale'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]
    
    # On crée le champ "pays_etablissement" de type choix
    PAYS_CHOICES = [
        ('senegal', 'Sénégal'),
        ('cote_ivoire', 'Côte d\'Ivoire'),
        ('mali', 'Mali'),
        ('burkina_faso', 'Burkina Faso'),
        ('niger', 'Niger'),
        ('guinee', 'Guinée'),
        ('autre', 'Autre'),
    ]
    
    # On crée le champ "source_etablissement" de type choix
    SOURCE_CHOICES = [
        ('recommandation', 'Recommandation'),
        ('site_web', 'Site web'),
        ('reseau_social', 'Réseau social'),
        ('salon', 'Salon/Événement'),
        ('appel_froid', 'Appel froid'),
        ('autre', 'Autre'),
    ]
    
    # On crée le champ "prochaine_action_etablissement" de type choix
    ACTION_CHOICES = [
        ('recherche_contact', 'Rechercher les contacts'),
        ('appel_telephonique', 'Appel téléphonique'),
        ('email', 'Envoi d\'email'),
        ('visite', 'Visite sur site'),
        ('presentation', 'Présentation'),
    ]

    # On crée le champ "nom_etablissement" de type texte
    nom_etablissement = models.CharField(max_length=255, verbose_name="Nom de l'établissement")
    # On crée le champ "type_etablissement" de type choix
    type_etablissement = models.CharField(max_length=255, choices=TYPE_CHOICES, verbose_name="Type d'établissement")
    genre_etablissement = models.CharField(max_length=255, choices=GENRE_CHOICES, verbose_name="Genre d'établissement")
    statut_etablissement = models.CharField(max_length=255, choices=STATUT_CHOICES, verbose_name="Statut d'établissement")
    ville_etablissement = models.CharField(max_length=255, verbose_name="Ville")
    pays_etablissement = models.CharField(max_length=255, choices=PAYS_CHOICES, verbose_name="Pays")
    adresse_etablissement = models.TextField(verbose_name="Adresse complète")
    potentiel_etablissement = models.CharField(max_length=255, choices=POTENTIEL_CHOICES, verbose_name="Potentiel commercial")
    priorite_etablissement = models.CharField(max_length=255, choices=PRIORITE_CHOICES, verbose_name="Priorité")
    source_etablissement = models.CharField(max_length=255, choices=SOURCE_CHOICES, verbose_name="Source de prospection", blank=True, null=True)
    prochaine_action_etablissement = models.CharField(max_length=255, choices=ACTION_CHOICES, verbose_name="Prochaine action", blank=True, null=True)
    notes_commercial = models.TextField(verbose_name="Notes commerciales", blank=True, null=True)
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    cree_par = models.ForeignKey(CompteUser, on_delete=models.SET_NULL, null=True, verbose_name="Créé par")
    notes_rendezvous = models.TextField(verbose_name="Notes de rendez-vous", blank=True, null=True)
    
    class Meta:
        verbose_name = "Prospection"
        verbose_name_plural = "Prospections"
        ordering = ['-date_creation']
        
    def __str__(self):
        return f"{self.nom_etablissement}"