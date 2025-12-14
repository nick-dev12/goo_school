"""
Modèle pour archiver les inscriptions d'élèves par année scolaire
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .etablissement_model import Etablissement
from .classe_model import Classe
from .annee_scolaire_model import AnneeScolaire


class InscriptionEleve(models.Model):
    """
    Modèle pour archiver les inscriptions d'élèves par année scolaire
    Représente une inscription d'élève pour une année scolaire spécifique
    """
    
    # Relation avec l'année scolaire (OBLIGATOIRE)
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='inscriptions_eleves',
        verbose_name="Année scolaire",
        help_text="Année scolaire de l'inscription"
    )
    
    # Référence à l'élève (si l'élève existe toujours dans le système)
    eleve = models.ForeignKey(
        'Eleve',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inscriptions',
        verbose_name="Élève",
        help_text="Référence à l'élève dans le système (peut être null si l'élève a été supprimé)"
    )
    
    # Champs personnels (copiés depuis Eleve)
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de famille",
        help_text="Nom de famille de l'élève"
    )
    
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom",
        help_text="Prénom de l'élève"
    )
    
    date_naissance = models.DateField(
        verbose_name="Date de naissance",
        help_text="Date de naissance de l'élève"
    )
    
    lieu_naissance = models.CharField(
        max_length=100,
        verbose_name="Lieu de naissance",
        help_text="Lieu de naissance de l'élève"
    )
    
    SEXE_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Féminin'),
    ]
    sexe = models.CharField(
        max_length=1,
        choices=SEXE_CHOICES,
        verbose_name="Sexe",
        help_text="Sexe de l'élève"
    )
    
    nationalite = models.CharField(
        max_length=100,
        verbose_name="Nationalité",
        help_text="Nationalité de l'élève"
    )
    
    adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse",
        help_text="Adresse de résidence de l'élève (optionnel)"
    )
    
    telephone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone",
        help_text="Numéro de téléphone de l'élève"
    )
    
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
        help_text="Adresse email de l'élève"
    )
    
    # Informations scolaires
    numero_eleve = models.CharField(
        max_length=20,
        verbose_name="Numéro d'élève",
        help_text="Numéro unique d'identification de l'élève"
    )
    
    matricule_eleve = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Matricule élève",
        help_text="Matricule de connexion de l'élève (ex: BP2025001)"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='inscriptions_eleves',
        verbose_name="Établissement",
        help_text="Établissement de scolarisation"
    )
    
    classe = models.ForeignKey(
        Classe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inscriptions_eleves',
        verbose_name="Classe",
        help_text="Classe d'affectation de l'élève"
    )
    
    date_inscription = models.DateField(
        verbose_name="Date d'inscription",
        help_text="Date d'inscription de l'élève"
    )
    
    STATUT_CHOICES = [
        ('nouvelle', 'Nouvelle inscription'),
        ('transfert', 'Transfert d\'établissement'),
        ('reinscription', 'Réinscription'),
    ]
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        verbose_name="Statut d'inscription",
        help_text="Type d'inscription de l'élève"
    )
    
    # Informations du parent/tuteur
    parent_nom = models.CharField(
        max_length=100,
        verbose_name="Nom du parent/tuteur",
        help_text="Nom de famille du parent ou tuteur"
    )
    
    parent_prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom du parent/tuteur",
        help_text="Prénom du parent ou tuteur"
    )
    
    parent_telephone = models.CharField(
        max_length=20,
        verbose_name="Téléphone du parent/tuteur",
        help_text="Numéro de téléphone du parent ou tuteur"
    )
    
    parent_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email du parent/tuteur",
        help_text="Adresse email du parent ou tuteur (optionnel)"
    )
    
    parent_adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse du parent/tuteur",
        help_text="Adresse complète du parent ou tuteur (optionnel)"
    )
    
    parent_profession = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Profession du parent/tuteur",
        help_text="Profession du parent ou tuteur (optionnel)"
    )
    
    LIEN_PARENT_CHOICES = [
        ('pere', 'Père'),
        ('mere', 'Mère'),
        ('grand_parent', 'Grand-parent'),
        ('oncle_tante', 'Oncle/Tante'),
        ('frere_soeur', 'Frère/Sœur'),
        ('autre_famille', 'Autre membre de la famille'),
        ('tuteur_legal', 'Tuteur légal'),
        ('autre', 'Autre'),
    ]
    parent_lien = models.CharField(
        max_length=20,
        choices=LIEN_PARENT_CHOICES,
        verbose_name="Lien avec l'élève",
        help_text="Lien de parenté du parent/tuteur avec l'élève"
    )
    
    # Documents d'identité
    document_acte_naissance = models.BooleanField(
        default=False,
        verbose_name="Acte de naissance",
        help_text="Acte de naissance fourni"
    )
    
    document_cni = models.BooleanField(
        default=False,
        verbose_name="Carte nationale d'identité",
        help_text="Carte nationale d'identité fournie"
    )
    
    document_passeport = models.BooleanField(
        default=False,
        verbose_name="Passeport",
        help_text="Passeport fourni"
    )
    
    # Documents scolaires
    document_bulletin_precedent = models.BooleanField(
        default=False,
        verbose_name="Bulletin de l'année précédente",
        help_text="Bulletin de l'année précédente fourni"
    )
    
    document_certificat_scolarite = models.BooleanField(
        default=False,
        verbose_name="Certificat de scolarité",
        help_text="Certificat de scolarité fourni"
    )
    
    document_livret_scolaire = models.BooleanField(
        default=False,
        verbose_name="Livret scolaire",
        help_text="Livret scolaire fourni"
    )
    
    # Documents médicaux
    document_certificat_medical = models.BooleanField(
        default=False,
        verbose_name="Certificat médical",
        help_text="Certificat médical fourni"
    )
    
    document_carnet_vaccination = models.BooleanField(
        default=False,
        verbose_name="Carnet de vaccination",
        help_text="Carnet de vaccination fourni"
    )
    
    document_assurance_maladie = models.BooleanField(
        default=False,
        verbose_name="Attestation d'assurance maladie",
        help_text="Attestation d'assurance maladie fournie"
    )
    
    # Documents administratifs
    document_justificatif_domicile = models.BooleanField(
        default=False,
        verbose_name="Justificatif de domicile",
        help_text="Justificatif de domicile fourni"
    )
    
    document_photo_identite = models.BooleanField(
        default=False,
        verbose_name="Photo d'identité",
        help_text="Photo d'identité fournie"
    )
    
    document_autorisation_parentale = models.BooleanField(
        default=False,
        verbose_name="Autorisation parentale",
        help_text="Autorisation parentale fournie"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Date de création de l'enregistrement d'inscription"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    class Meta:
        verbose_name = "Inscription d'élève"
        verbose_name_plural = "Inscriptions d'élèves"
        ordering = ['-annee_scolaire', '-date_inscription', 'nom', 'prenom']
        unique_together = ['annee_scolaire', 'matricule_eleve']
        indexes = [
            models.Index(fields=['annee_scolaire', 'etablissement']),
            models.Index(fields=['annee_scolaire', 'classe']),
            models.Index(fields=['matricule_eleve']),
            models.Index(fields=['date_inscription']),
        ]
    
    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.annee_scolaire.libelle} ({self.numero_eleve})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de l'élève"""
        return f"{self.prenom} {self.nom}"
    
    @property
    def age(self):
        """Calcule l'âge de l'élève à la date d'inscription"""
        from datetime import date
        inscription_date = self.date_inscription
        return inscription_date.year - self.date_naissance.year - ((inscription_date.month, inscription_date.day) < (self.date_naissance.month, self.date_naissance.day))
    
    @property
    def responsable_nom_complet(self):
        """Retourne le nom complet du parent/tuteur"""
        if self.parent_prenom and self.parent_nom:
            return f"{self.parent_prenom} {self.parent_nom}"
        elif self.parent_nom:
            return self.parent_nom
        else:
            return "Non renseigné"
    
    @property
    def responsable_contact(self):
        """Retourne le contact du parent/tuteur"""
        return self.parent_telephone or "Non renseigné"
    
    @property
    def responsable_email(self):
        """Retourne l'email du parent/tuteur"""
        return self.parent_email
    
    @property
    def documents_fournis_liste(self):
        """Retourne la liste des documents fournis"""
        documents = []
        if self.document_acte_naissance:
            documents.append("Acte de naissance")
        if self.document_cni:
            documents.append("Carte nationale d'identité")
        if self.document_passeport:
            documents.append("Passeport")
        if self.document_bulletin_precedent:
            documents.append("Bulletin de l'année précédente")
        if self.document_certificat_scolarite:
            documents.append("Certificat de scolarité")
        if self.document_livret_scolaire:
            documents.append("Livret scolaire")
        if self.document_certificat_medical:
            documents.append("Certificat médical")
        if self.document_carnet_vaccination:
            documents.append("Carnet de vaccination")
        if self.document_assurance_maladie:
            documents.append("Attestation d'assurance maladie")
        if self.document_justificatif_domicile:
            documents.append("Justificatif de domicile")
        if self.document_photo_identite:
            documents.append("Photo d'identité")
        if self.document_autorisation_parentale:
            documents.append("Autorisation parentale")
        return documents
    
    @property
    def nombre_documents_fournis(self):
        """Retourne le nombre de documents fournis"""
        return len(self.documents_fournis_liste)
    
    def get_statut_display(self):
        """Retourne l'affichage du statut d'inscription"""
        return dict(self.STATUT_CHOICES).get(self.statut, self.statut)
    
    def get_sexe_display(self):
        """Retourne l'affichage du sexe"""
        return dict(self.SEXE_CHOICES).get(self.sexe, self.sexe)
    
    def get_parent_lien_display(self):
        """Retourne l'affichage du lien du parent/tuteur"""
        return dict(self.LIEN_PARENT_CHOICES).get(self.parent_lien, self.parent_lien)
    
    def clean(self):
        """Validation personnalisée"""
        from django.core.exceptions import ValidationError
        
        # Validation du parent/tuteur
        if not self.parent_nom:
            raise ValidationError("Le nom du parent/tuteur est obligatoire.")
        if not self.parent_prenom:
            raise ValidationError("Le prénom du parent/tuteur est obligatoire.")
        if not self.parent_telephone:
            raise ValidationError("Le téléphone du parent/tuteur est obligatoire.")
        if not self.parent_lien:
            raise ValidationError("Le lien avec l'élève est obligatoire.")
        
        # Vérifier que l'établissement correspond à celui de l'année scolaire
        if self.annee_scolaire and self.etablissement:
            if self.annee_scolaire.etablissement != self.etablissement:
                raise ValidationError("L'établissement doit correspondre à celui de l'année scolaire.")
    
    def save(self, *args, **kwargs):
        """Surcharge du save pour exécuter la validation"""
        self.full_clean()
        super().save(*args, **kwargs)

