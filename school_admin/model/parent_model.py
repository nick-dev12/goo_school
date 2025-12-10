"""
Modèle Parent pour la gestion des parents d'élèves
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from .etablissement_model import Etablissement


class Parent(AbstractUser):
    """
    Modèle pour les parents d'élèves
    Hérite de CompteUser pour l'authentification
    """
    TYPE_PARENT_CHOICES = [
        ('mere', 'Mère'),
        ('pere', 'Père'),
        ('tuteur', 'Tuteur/Tutrice'),
    ]
    
    # Informations personnelles
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de famille"
    )
    
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom"
    )
    
    telephone = models.CharField(
        max_length=20,
        verbose_name="Téléphone"
    )
    
    matricule_parental = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Matricule parental",
        help_text="Identifiant unique du parent (ex: BPP2025001)"
    )
    
    type_parent = models.CharField(
        max_length=10,
        choices=TYPE_PARENT_CHOICES,
        verbose_name="Type de parent"
    )
    
    adresse = models.TextField(
        verbose_name="Adresse",
        blank=True
    )
    
    profession = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Profession"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='parents',
        verbose_name="Établissement"
    )
    
    mot_de_passe_provisoire = models.CharField(
        max_length=10,
        verbose_name="Mot de passe provisoire",
        help_text="Mot de passe initial à changer lors de la première connexion"
    )
    
    mot_de_passe_modifie = models.BooleanField(
        default=False,
        verbose_name="Mot de passe modifié",
        help_text="Indique si le parent a changé son mot de passe initial"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    # Réinitialisation de mot de passe
    password_reset_code = models.CharField(max_length=6, null=True, blank=True, verbose_name="Code de réinitialisation")
    password_reset_expires = models.DateTimeField(null=True, blank=True, verbose_name="Expiration du code de réinitialisation")
    
    # Authentification par QR Code
    qr_auth_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Token d'authentification QR",
        help_text="Token unique pour l'authentification par QR Code"
    )
    
    qr_auth_token_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de génération du token QR",
        help_text="Date de génération du token d'authentification QR"
    )
    
    # Acceptation des conditions d'utilisation
    conditions_acceptees = models.BooleanField(
        default=False,
        verbose_name="Conditions acceptées",
        help_text="Indique si le parent a accepté les conditions d'utilisation et la politique de confidentialité"
    )
    
    # Configuration de l'authentification
    USERNAME_FIELD = 'matricule_parental'
    REQUIRED_FIELDS = ['nom', 'prenom', 'email']
    
    # Redéfinir groups et user_permissions pour éviter les conflits
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name="parent_set",
        related_query_name="parent",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="parent_set",
        related_query_name="parent",
    )
    
    class Meta:
        verbose_name = "Parent d'élève"
        verbose_name_plural = "Parents d'élèves"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.matricule_parental}) - {self.get_type_parent_display()}"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet du parent au format 'NOM Prénom'"""
        nom = self.nom.upper() if self.nom else ''
        prenom = self.prenom[0].upper() + self.prenom[1:].lower() if self.prenom and len(self.prenom) > 1 else (self.prenom.upper() if self.prenom else '')
        if nom and prenom:
            return f"{nom} {prenom}"
        elif nom:
            return nom
        elif prenom:
            return prenom
        else:
            return ''
    
    @property
    def nombre_enfants(self):
        """Retourne le nombre d'enfants liés à ce parent"""
        return self.liens_enfants.filter(actif=True, statut='valide').count()
    
    @property
    def enfants(self):
        """Retourne la liste des élèves liés à ce parent"""
        from .eleve_model import Eleve
        liens = self.liens_enfants.filter(actif=True, statut='valide')
        return Eleve.objects.filter(id__in=liens.values_list('eleve_id', flat=True))
    
    @staticmethod
    def generer_matricule_parent(etablissement):
        """
        Génère un matricule parental unique
        Format : [XX]P[6 NUMEROS_ALEATOIRES]
        Exemple : BDP345843 (première lettre des 2 premiers mots de l'établissement + P + 6 chiffres aléatoires)
        """
        import random
        
        # Extraire les initiales de l'établissement (première lettre des 2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Générer un numéro aléatoire de 6 chiffres (100000-999999)
        numero_aleatoire_6 = random.randint(100000, 999999)
        
        # Générer le matricule : BDP345843
        matricule = f"{initiales}P{numero_aleatoire_6}"
        
        # Boucle de sécurité pour éviter les doublons
        max_tentatives = 1000
        tentatives = 0
        while Parent.objects.filter(matricule_parental=matricule).exists() or \
              Parent.objects.filter(username=matricule).exists():
            # Générer un nouveau numéro aléatoire
            numero_aleatoire_6 = random.randint(100000, 999999)
            matricule = f"{initiales}P{numero_aleatoire_6}"
            tentatives += 1
            if tentatives >= max_tentatives:
                # Fallback avec timestamp si trop de tentatives
                import time
                timestamp = int(time.time() * 1000) % 1000000
                matricule = f"{initiales}P{timestamp:06d}"
                break
        
        return matricule
    
    @staticmethod
    def generer_mot_de_passe():
        """
        Génère un mot de passe provisoire de 6 chiffres sans tiret
        Format : XXXXXX
        Exemple : 654565
        """
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    @staticmethod
    def generer_token_qr_auth():
        """
        Génère un token unique et sécurisé pour l'authentification par QR Code
        """
        import secrets
        return secrets.token_urlsafe(32)
    
    def generer_et_sauvegarder_token_qr(self):
        """
        Génère et sauvegarde un nouveau token QR d'authentification
        """
        self.qr_auth_token = self.generer_token_qr_auth()
        self.qr_auth_token_generated_at = timezone.now()
        self.save(update_fields=['qr_auth_token', 'qr_auth_token_generated_at'])
    
    def get_qr_auth_url(self, request=None):
        """
        Retourne l'URL d'authentification par QR Code
        """
        from django.urls import reverse
        if request:
            return request.build_absolute_uri(
                reverse('school_admin:auth_qr_login', kwargs={'token': self.qr_auth_token})
            )
        return f"/auth/qr/{self.qr_auth_token}/"
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour générer automatiquement le token QR d'authentification
        et formater les noms et prénoms
        """
        # Formater automatiquement les noms et prénoms
        if self.nom:
            self.nom = self.nom.strip().upper()
        if self.prenom:
            prenom_stripped = self.prenom.strip()
            if len(prenom_stripped) > 1:
                self.prenom = prenom_stripped[0].upper() + prenom_stripped[1:].lower()
            else:
                self.prenom = prenom_stripped.upper()
        
        # Générer le token QR d'authentification si nécessaire
        if not self.qr_auth_token:
            self.qr_auth_token = self.generer_token_qr_auth()
            self.qr_auth_token_generated_at = timezone.now()
        
        super().save(*args, **kwargs)

