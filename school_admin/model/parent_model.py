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
        """Retourne le nom complet du parent"""
        return f"{self.prenom} {self.nom}"
    
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
        Format : [XX]P[4 NUMERO_ALEATOIRE]-[3 NUMERO_ALEATOIRE]
        Exemple : BPP1254-857 (initiales établissement + P + 4 chiffres aléatoires + tiret + 3 chiffres aléatoires)
        Tous les chiffres sont aléatoires
        """
        import random
        
        # Extraire les initiales de l'établissement (2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Générer un numéro aléatoire de 4 chiffres (1000-9999)
        numero_aleatoire_4 = random.randint(1000, 9999)
        
        # Générer un numéro aléatoire de 3 chiffres (100-999)
        numero_aleatoire_3 = random.randint(100, 999)
        
        # Générer le matricule avec le tiret : BPP1254-857
        matricule = f"{initiales}P{numero_aleatoire_4}-{numero_aleatoire_3:03d}"
        
        # Boucle de sécurité pour éviter les doublons
        max_tentatives = 1000
        tentatives = 0
        while Parent.objects.filter(matricule_parental=matricule).exists() or \
              Parent.objects.filter(username=matricule).exists():
            # Générer de nouveaux numéros aléatoires
            numero_aleatoire_4 = random.randint(1000, 9999)
            numero_aleatoire_3 = random.randint(100, 999)
            matricule = f"{initiales}P{numero_aleatoire_4}-{numero_aleatoire_3:03d}"
            tentatives += 1
            if tentatives >= max_tentatives:
                # Fallback avec timestamp si trop de tentatives
                import time
                timestamp = int(time.time() * 1000) % 1000000
                numero_4 = timestamp % 10000
                numero_3 = (timestamp // 10000) % 1000
                matricule = f"{initiales}P{numero_4:04d}-{numero_3:03d}"
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

