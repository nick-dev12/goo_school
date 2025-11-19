import json
import uuid
from importlib import import_module
from io import BytesIO

from django.contrib.auth.models import AbstractUser
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from .etablissement_model import Etablissement
from .classe_model import Classe

try:
    import qrcode
except ImportError:  # pragma: no cover - gestion au moment de la génération
    qrcode = None


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
    
    photo_profil = models.ImageField(
        upload_to='eleves/photos/',
        blank=True,
        null=True,
        verbose_name="Photo de profil",
        help_text="Photographie récente de l'élève pour son dossier"
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
        help_text="Adresse email de l'élève"
    )

    qr_code_identifier = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Identifiant QR code",
        help_text="Identifiant unique du QR code de l'élève"
    )

    qr_code_data = models.TextField(
        blank=True,
        null=True,
        verbose_name="Données QR code",
        help_text="Charge utile encodée dans le QR code de l'élève"
    )

    qr_code_image = models.ImageField(
        upload_to='eleves/qrcodes/',
        blank=True,
        null=True,
        verbose_name="Image du QR code",
        help_text="Image PNG générée pour le QR code de l'élève"
    )

    qr_code_generated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date de génération du QR code",
        help_text="Dernière date de génération du QR code"
    )
    
    # Informations scolaires
    numero_eleve = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Numéro d'élève",
        help_text="Numéro unique d'identification de l'élève"
    )
    
    matricule_eleve = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Matricule élève",
        help_text="Matricule de connexion de l'élève (ex: BP2025001)"
    )
    
    mot_de_passe_eleve_modifie = models.BooleanField(
        default=False,
        verbose_name="Mot de passe élève modifié",
        help_text="Indique si l'élève a changé son mot de passe initial"
    )
    
    # Réinitialisation de mot de passe
    password_reset_code = models.CharField(max_length=6, null=True, blank=True, verbose_name="Code de réinitialisation")
    password_reset_expires = models.DateTimeField(null=True, blank=True, verbose_name="Expiration du code de réinitialisation")
    
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
    def parents_lies(self):
        """Retourne la liste des parents liés à cet élève via LienFamilial"""
        from .lien_familial_model import LienFamilial
        from .parent_model import Parent
        liens = LienFamilial.objects.filter(eleve=self, actif=True, statut='valide')
        return Parent.objects.filter(id__in=liens.values_list('parent_id', flat=True))
    
    @property
    def pere(self):
        """Retourne le père de l'élève s'il existe"""
        from .lien_familial_model import LienFamilial
        lien = LienFamilial.objects.filter(
            eleve=self, 
            type_lien='pere', 
            actif=True, 
            statut='valide'
        ).first()
        return lien.parent if lien else None
    
    @property
    def mere(self):
        """Retourne la mère de l'élève si elle existe"""
        from .lien_familial_model import LienFamilial
        lien = LienFamilial.objects.filter(
            eleve=self, 
            type_lien='mere', 
            actif=True, 
            statut='valide'
        ).first()
        return lien.parent if lien else None
    
    @property
    def tuteurs(self):
        """Retourne la liste des tuteurs de l'élève"""
        from .lien_familial_model import LienFamilial
        from .parent_model import Parent
        liens = LienFamilial.objects.filter(
            eleve=self, 
            type_lien='tuteur', 
            actif=True, 
            statut='valide'
        )
        return Parent.objects.filter(id__in=liens.values_list('parent_id', flat=True))
    
    @property
    def parent_inscripteur(self):
        """Retourne le parent qui a inscrit l'élève"""
        from .lien_familial_model import LienFamilial
        lien = LienFamilial.objects.filter(
            eleve=self, 
            est_inscripteur=True, 
            actif=True, 
            statut='valide'
        ).first()
        return lien.parent if lien else None
    
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
    
    @staticmethod
    def generer_matricule_eleve(etablissement):
        """
        Génère un matricule unique pour un élève
        Format : [XX][ANNEE]-[NUMERO]
        Exemple : BP2025-001 (Blaise Pascal, année 2025, élève 001)
        """
        from datetime import datetime
        
        # Extraire les initiales de l'établissement (2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Année en cours
        annee = datetime.now().year
        
        # Préfixe de base (sans tiret pour la recherche)
        prefix_search = f"{initiales}{annee}"
        
        # Rechercher le dernier matricule utilisé pour ce préfixe
        derniers_eleves = Eleve.objects.filter(
            etablissement=etablissement,
            matricule_eleve__startswith=prefix_search
        ).exclude(
            matricule_eleve__isnull=True
        ).order_by('-matricule_eleve')[:1]
        
        if derniers_eleves.exists():
            # Extraire le numéro du dernier matricule
            dernier_matricule = derniers_eleves[0].matricule_eleve
            try:
                # Extraire les 3 derniers chiffres (après le tiret si présent)
                if '-' in dernier_matricule:
                    dernier_numero = int(dernier_matricule.split('-')[-1])
                else:
                    dernier_numero = int(dernier_matricule[-3:])
                count = dernier_numero + 1
            except (ValueError, IndexError):
                # Si impossible d'extraire, commencer à 1
                count = 1
        else:
            count = 1
        
        # Générer le matricule avec le tiret : BP2025-001
        matricule = f"{prefix_search}-{count:03d}"
        
        # Boucle de sécurité pour éviter les doublons
        max_tentatives = 1000
        tentatives = 0
        while Eleve.objects.filter(matricule_eleve=matricule).exists() or \
              Eleve.objects.filter(username=matricule).exists():
            count += 1
            matricule = f"{prefix_search}-{count:03d}"
            tentatives += 1
            if tentatives >= max_tentatives:
                # Fallback avec timestamp si trop de tentatives
                import time
                timestamp = int(time.time() * 1000) % 10000
                matricule = f"{prefix_search}-{timestamp:04d}"
                break
        
        return matricule
    
    @staticmethod
    def generer_mot_de_passe():
        """
        Génère un mot de passe provisoire de 6 chiffres séparés par un tiret
        Format : XXX-XXX
        Exemple : 487-293
        """
        import random
        partie1 = ''.join([str(random.randint(0, 9)) for _ in range(3)])
        partie2 = ''.join([str(random.randint(0, 9)) for _ in range(3)])
        return f"{partie1}-{partie2}"
    
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

    # Gestion du QR code ---------------------------------------------------

    QR_CODE_FIELDS_TRIGGER = (
        'nom', 'prenom', 'numero_eleve', 'matricule_eleve', 'classe_id', 'etablissement_id'
    )

    def _build_qr_payload(self):
        """Construit la charge utile sécurisée encodée dans le QR code."""
        payload = {
            'identifier': self.qr_code_identifier,
            'eleve_id': self.pk,
            'numero_eleve': self.numero_eleve,
            'matricule_eleve': self.matricule_eleve,
            'nom': self.nom,
            'prenom': self.prenom,
            'classe': self.classe.nom if self.classe else None,
            'etablissement': self.etablissement.nom if self.etablissement else None,
            'generated_at': timezone.now().isoformat(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _generate_qr_code(self, previous_image_path=None):
        """Génère l'image du QR code et met à jour les champs associés."""
        global qrcode

        if qrcode is None:
            try:
                qrcode = import_module('qrcode')
            except ImportError as import_error:  # pragma: no cover
                raise RuntimeError(
                    "La bibliothèque 'qrcode' est requise pour générer les QR codes. "
                    "Installez-la avec 'pip install qrcode[pil]'."
                ) from import_error

        payload = self._build_qr_payload()
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        image_io = BytesIO()
        img.save(image_io, format='PNG')
        image_io.seek(0)

        file_name = f"eleve_{self.pk}_{self.qr_code_identifier}.png"

        # Supprimer l'ancienne image le cas échéant
        if previous_image_path and default_storage.exists(previous_image_path):
            default_storage.delete(previous_image_path)

        self.qr_code_data = payload
        self.qr_code_generated_at = timezone.now()
        self.qr_code_image.save(file_name, ContentFile(image_io.read()), save=False)

    def _should_regenerate_qr(self, old_instance=None):
        """Détermine si le QR code doit être régénéré."""
        if not self.pk or not self.qr_code_identifier or not self.qr_code_image:
            return True

        if old_instance is None:
            return False

        for field in self.QR_CODE_FIELDS_TRIGGER:
            if getattr(old_instance, field) != getattr(self, field):
                return True

        return False

    def save(self, *args, **kwargs):
        """Surcharge du save pour garantir un QR code cohérent et mettre à jour la facturation de l'établissement."""
        old_instance = None
        previous_image_path = None
        etablissement_changed = False
        actif_changed = False

        old_etablissement = None
        if self.pk:
            try:
                old_instance = Eleve.objects.get(pk=self.pk)
                if old_instance.qr_code_image:
                    previous_image_path = old_instance.qr_code_image.name
                # Vérifier si l'établissement ou le statut actif a changé
                if old_instance.etablissement_id != self.etablissement_id:
                    etablissement_changed = True
                    old_etablissement = old_instance.etablissement
                if old_instance.actif != self.actif:
                    actif_changed = True
            except Eleve.DoesNotExist:
                old_instance = None

        if not self.qr_code_identifier:
            self.qr_code_identifier = uuid.uuid4().hex

        regenerate_qr = self._should_regenerate_qr(old_instance)

        super().save(*args, **kwargs)

        if regenerate_qr:
            self._generate_qr_code(previous_image_path)
            super().save(update_fields=['qr_code_data', 'qr_code_image', 'qr_code_generated_at'])
        
        # Mettre à jour la facturation de l'établissement actuel
        if self.etablissement:
            self.etablissement.recalculer_facturation()
        
        # Si l'établissement a changé, mettre à jour aussi l'ancien établissement
        if etablissement_changed and old_etablissement:
            old_etablissement.recalculer_facturation()
