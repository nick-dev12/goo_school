from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinLengthValidator
from .etablissement_model import Etablissement
from .classe_model import Classe


class Eleve(AbstractUser):
    """
    Modèle pour les élèves de l'établissement
    Hérite d'AbstractUser pour permettre la connexion
    """
    
    # Champs personnels
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
        verbose_name="Adresse",
        help_text="Adresse de résidence de l'élève"
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
        unique=True,
        verbose_name="Numéro d'élève",
        help_text="Numéro unique d'identification de l'élève"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='eleves',
        verbose_name="Établissement",
        help_text="Établissement de scolarisation"
    )
    
    classe = models.ForeignKey(
        Classe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eleves',
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
    
    # Informations des parents/tuteurs
    TYPE_RESPONSABLE_CHOICES = [
        ('parents', 'Parents'),
        ('tuteur', 'Tuteur légal'),
    ]
    type_responsable = models.CharField(
        max_length=20,
        choices=TYPE_RESPONSABLE_CHOICES,
        verbose_name="Type de responsable",
        help_text="Type de responsable de l'élève"
    )
    
    # Champs parents
    nom_pere = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Nom du père",
        help_text="Nom de famille du père"
    )
    
    nom_mere = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Nom de la mère",
        help_text="Nom de famille de la mère"
    )
    
    telephone_pere = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone du père",
        help_text="Numéro de téléphone du père"
    )
    
    telephone_mere = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone de la mère",
        help_text="Numéro de téléphone de la mère"
    )
    
    email_pere = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email du père",
        help_text="Adresse email du père"
    )
    
    email_mere = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email de la mère",
        help_text="Adresse email de la mère"
    )
    
    # Champs tuteur
    tuteur_nom = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Nom du tuteur",
        help_text="Nom de famille du tuteur légal"
    )
    
    tuteur_prenom = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Prénom du tuteur",
        help_text="Prénom du tuteur légal"
    )
    
    tuteur_telephone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Téléphone du tuteur",
        help_text="Numéro de téléphone du tuteur"
    )
    
    tuteur_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email du tuteur",
        help_text="Adresse email du tuteur"
    )
    
    tuteur_adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse du tuteur",
        help_text="Adresse complète du tuteur"
    )
    
    tuteur_profession = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Profession du tuteur",
        help_text="Profession du tuteur légal"
    )
    
    LIEN_TUTEUR_CHOICES = [
        ('grand_parent', 'Grand-parent'),
        ('oncle_tante', 'Oncle/Tante'),
        ('frere_soeur', 'Frère/Sœur'),
        ('autre_famille', 'Autre membre de la famille'),
        ('autre', 'Autre'),
    ]
    tuteur_lien = models.CharField(
        max_length=20,
        choices=LIEN_TUTEUR_CHOICES,
        blank=True,
        null=True,
        verbose_name="Lien avec l'élève",
        help_text="Lien de parenté du tuteur avec l'élève"
    )
    
    # Mot de passe provisoire pour les parents/tuteurs
    mot_de_passe_provisoire = models.CharField(
        max_length=128,
        verbose_name="Mot de passe provisoire",
        help_text="Mot de passe provisoire pour l'accès parent/tuteur"
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
    
    # Statut de l'élève
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si l'élève est actuellement actif"
    )
    
    # Dates de gestion
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Date de création du compte élève"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Date de dernière modification"
    )
    
    # Configuration des champs AbstractUser
    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nom d'utilisateur",
        help_text="Nom d'utilisateur unique pour la connexion"
    )
    USERNAME_FIELD = 'username'
    
    first_name = None  # On utilise 'prenom' à la place
    last_name = None   # On utilise 'nom' à la place
    
    # Champs obligatoires pour AbstractUser
    is_staff = models.BooleanField(
        default=False,
        verbose_name="Membre du personnel",
        help_text="Indique si l'utilisateur peut accéder à l'interface d'administration"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si ce compte utilisateur doit être considéré comme actif"
    )
    
    is_superuser = models.BooleanField(
        default=False,
        verbose_name="Superutilisateur",
        help_text="Indique que cet utilisateur a toutes les permissions sans les assigner explicitement"
    )
    
    # Related names pour éviter les conflits
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groupes',
        blank=True,
        help_text='Les groupes auxquels appartient cet utilisateur',
        related_name='eleve_groups',
        related_query_name='eleve_group'
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='permissions utilisateur',
        blank=True,
        help_text='Permissions spécifiques pour cet utilisateur',
        related_name='eleve_user_permissions',
        related_query_name='eleve_user_permission'
    )
    
    class Meta:
        verbose_name = "Élève"
        verbose_name_plural = "Élèves"
        ordering = ['username', 'prenom']
        db_table = 'eleve'
    
    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.numero_eleve})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de l'élève"""
        return f"{self.prenom} {self.nom}"
    
    @property
    def age(self):
        """Calcule l'âge de l'élève"""
        from datetime import date
        today = date.today()
        return today.year - self.date_naissance.year - ((today.month, today.day) < (self.date_naissance.month, self.date_naissance.day))
    
    @property
    def responsable_nom_complet(self):
        """Retourne le nom complet du responsable selon le type"""
        if self.type_responsable == 'parents':
            if self.nom_pere and self.nom_mere:
                return f"{self.nom_pere} et {self.nom_mere}"
            elif self.nom_pere:
                return self.nom_pere
            elif self.nom_mere:
                return self.nom_mere
            else:
                return "Non renseigné"
        elif self.type_responsable == 'tuteur':
            if self.tuteur_prenom and self.tuteur_nom:
                return f"{self.tuteur_prenom} {self.tuteur_nom}"
            elif self.tuteur_nom:
                return self.tuteur_nom
            else:
                return "Non renseigné"
        return "Non renseigné"
    
    @property
    def responsable_contact(self):
        """Retourne le contact principal du responsable"""
        if self.type_responsable == 'parents':
            if self.telephone_pere:
                return self.telephone_pere
            elif self.telephone_mere:
                return self.telephone_mere
            else:
                return "Non renseigné"
        elif self.type_responsable == 'tuteur':
            return self.tuteur_telephone or "Non renseigné"
        return "Non renseigné"
    
    @property
    def responsable_email(self):
        """Retourne l'email principal du responsable"""
        if self.type_responsable == 'parents':
            if self.email_pere:
                return self.email_pere
            elif self.email_mere:
                return self.email_mere
            else:
                return None
        elif self.type_responsable == 'tuteur':
            return self.tuteur_email
        return None
    
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
    
    def get_type_responsable_display(self):
        """Retourne l'affichage du type de responsable"""
        return dict(self.TYPE_RESPONSABLE_CHOICES).get(self.type_responsable, self.type_responsable)
    
    def get_tuteur_lien_display(self):
        """Retourne l'affichage du lien du tuteur"""
        return dict(self.LIEN_TUTEUR_CHOICES).get(self.tuteur_lien, self.tuteur_lien)
    
    def clean(self):
        """Validation personnalisée"""
        from django.core.exceptions import ValidationError
        
        # Validation selon le type de responsable
        if self.type_responsable == 'parents':
            pere_renseigne = self.nom_pere and self.telephone_pere
            mere_renseignee = self.nom_mere and self.telephone_mere
            
            if not pere_renseigne and not mere_renseignee:
                raise ValidationError("Au moins un parent doit être renseigné (nom et téléphone).")
        elif self.type_responsable == 'tuteur':
            if not self.tuteur_nom:
                raise ValidationError("Le nom du tuteur est obligatoire.")
            if not self.tuteur_telephone:
                raise ValidationError("Le téléphone du tuteur est obligatoire.")
            if not self.tuteur_adresse:
                raise ValidationError("L'adresse du tuteur est obligatoire.")
            if not self.tuteur_lien:
                raise ValidationError("Le lien avec l'élève est obligatoire.")
            # L'email du tuteur est optionnel
        
        # Validation de l'âge
        if self.date_naissance:
            from datetime import date
            today = date.today()
            age = today.year - self.date_naissance.year - ((today.month, today.day) < (self.date_naissance.month, self.date_naissance.day))
            if age < 3 or age > 25:
                raise ValidationError("L'âge de l'élève doit être entre 3 et 25 ans.")
    
    def get_absolute_url(self):
        """Retourne l'URL de détail de l'élève"""
        from django.urls import reverse
        return reverse('secretaire:detail_eleve', kwargs={'pk': self.pk})
