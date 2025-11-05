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
        Format : [XX]P[ANNEE]-[NUMERO]
        Exemple : BPP2025-001
        """
        from datetime import datetime
        
        # Extraire les initiales de l'établissement (2 premiers mots)
        mots = etablissement.nom.split()[:2]
        initiales = ''.join([mot[0].upper() for mot in mots if mot])
        
        # Année en cours
        annee = datetime.now().year
        
        # Préfixe de base (sans tiret pour la recherche)
        prefix_search = f"{initiales}P{annee}"
        
        # Rechercher le dernier matricule utilisé pour ce préfixe
        derniers_parents = Parent.objects.filter(
            etablissement=etablissement,
            matricule_parental__startswith=prefix_search
        ).exclude(
            matricule_parental__isnull=True
        ).order_by('-matricule_parental')[:1]
        
        if derniers_parents.exists():
            # Extraire le numéro du dernier matricule
            dernier_matricule = derniers_parents[0].matricule_parental
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
        
        # Générer le matricule avec le tiret : BPP2025-001
        matricule = f"{prefix_search}-{count:03d}"
        
        # Boucle de sécurité pour éviter les doublons
        max_tentatives = 1000
        tentatives = 0
        while Parent.objects.filter(matricule_parental=matricule).exists() or \
              Parent.objects.filter(username=matricule).exists():
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

