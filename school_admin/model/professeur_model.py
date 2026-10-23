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
    sexe = models.CharField(
        max_length=1,
        choices=[('M', 'Masculin'), ('F', 'Féminin')],
        blank=True,
        default='',
        verbose_name="Sexe",
    )
    email = models.EmailField(unique=True, blank=True, null=True, verbose_name="Adresse email", help_text="Ce champ est facultatif")
    telephone = models.CharField(max_length=20, verbose_name="Numéro de téléphone")
    prix_volume_horaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix du volume horaire (FCFA/heure)",
    )
    
    # Contrat : un vacataire est payé à l'heure validée ; un permanent touche un salaire
    # fixe, moins les cours non faits non justifiés, plus les heures au-delà de son contrat.
    TYPE_CONTRAT_CHOICES = [
        ('vacataire', 'Vacataire (payé à l’heure)'),
        ('permanent', 'Permanent (salaire mensuel)'),
    ]
    type_contrat = models.CharField(
        max_length=12, choices=TYPE_CONTRAT_CHOICES, default='vacataire', verbose_name="Type de contrat",
    )
    salaire_mensuel = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Salaire mensuel brut",
    )
    heures_contrat_semaine = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Heures prévues au contrat (par semaine)",
    )

    # Informations professionnelles
    # Supérieur : grade universitaire (référentiel CAMES) et service statutaire en heures équivalent TD
    GRADE_CHOICES = [
        ('professeur_titulaire', 'Professeur titulaire'),
        ('maitre_conferences', 'Maître de conférences'),
        ('maitre_assistant', 'Maître-assistant'),
        ('assistant', 'Assistant'),
        ('charge_cours', 'Chargé de cours / enseignant associé'),
        ('vacataire', 'Vacataire'),
    ]
    grade_universitaire = models.CharField(max_length=24, choices=GRADE_CHOICES, blank=True, default='',
                                           verbose_name="Grade universitaire")
    service_statutaire = models.PositiveSmallIntegerField(
        default=0, verbose_name="Service statutaire (heures éq. TD / an)",
        help_text="0 = valeur par défaut du grade (règles de service de l'établissement).",
    )
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
        null=True,
        blank=True,
        verbose_name="Date d'embauche",
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    # Informations de connexion
    mot_de_passe_provisoire = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        verbose_name="Mot de passe provisoire"
    )
    # Réinitialisation de mot de passe
    password_reset_code = models.CharField(max_length=6, null=True, blank=True, verbose_name="Code de réinitialisation")
    password_reset_expires = models.DateTimeField(null=True, blank=True, verbose_name="Expiration du code de réinitialisation")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    # Acceptation des conditions d'utilisation
    conditions_acceptees = models.BooleanField(
        default=False,
        verbose_name="Conditions acceptées",
        help_text="Indique si le professeur a accepté les conditions d'utilisation et la politique de confidentialité"
    )
    
    USERNAME_FIELD = 'numero_employe'
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
        # Ne plus générer automatiquement le username à partir de l'email
        # Le username doit être généré explicitement lors de la création
        # via ProfesseurController.generate_matricule_professeur()
        if self.etablissement_id:
            from school_admin.services.assistant_prof_persona import (
                niveau_enseignement_for_type_etablissement,
            )

            etab = self.etablissement
            if etab is None:
                from school_admin.model.etablissement_model import Etablissement

                etab = Etablissement.objects.filter(pk=self.etablissement_id).first()
            if etab is not None:
                expected = niveau_enseignement_for_type_etablissement(
                    etab.type_etablissement
                )
                if self.niveau_enseignement != expected:
                    self.niveau_enseignement = expected
        super().save(*args, **kwargs)
