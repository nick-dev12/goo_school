"""
Modèle pour gérer les demandes de liaison entre parents et élèves
"""
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class DemandeLiaisonParent(models.Model):
    """
    Modèle pour les demandes de liaison entre parents et élèves
    Permet à un parent de demander l'accès au dossier d'un élève
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente de validation'),
        ('approuvee', 'Approuvée'),
        ('refusee', 'Refusée'),
        ('reussie', 'Réussie (liaison automatique)'),
        ('echec', 'Échec (vérification échouée)'),
        ('bloquee', 'Bloquée (trop de tentatives)'),
    ]
    
    TYPE_LIEN_CHOICES = [
        ('mere', 'Mère'),
        ('pere', 'Père'),
        ('tuteur', 'Tuteur/Tutrice'),
    ]
    
    parent_demandeur = models.ForeignKey(
        'Parent',
        on_delete=models.CASCADE,
        related_name='demandes_liaison',
        verbose_name="Parent demandeur"
    )
    
    # Informations pour identifier l'élève
    matricule_eleve = models.CharField(
        max_length=20,
        verbose_name="Matricule de l'élève",
        help_text="Matricule unique de l'élève (ex: BP2025001)"
    )
    
    nom_eleve = models.CharField(
        max_length=100,
        verbose_name="Nom de l'élève"
    )
    
    prenom_eleve = models.CharField(
        max_length=100,
        verbose_name="Prénom de l'élève"
    )
    
    date_naissance_eleve = models.DateField(
        verbose_name="Date de naissance de l'élève",
        help_text="Pour vérification de l'identité"
    )
    
    classe_eleve = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Classe de l'élève",
        help_text="Classe fournie par le parent pour vérification"
    )
    
    nom_parent_inscripteur = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Nom du parent inscripteur",
        help_text="Nom ou prénom du parent qui a inscrit l'enfant"
    )
    
    type_lien = models.CharField(
        max_length=10,
        choices=TYPE_LIEN_CHOICES,
        verbose_name="Type de lien familial"
    )
    
    nombre_tentatives = models.PositiveIntegerField(
        default=1,
        verbose_name="Nombre de tentatives",
        help_text="Compteur de tentatives de liaison pour ce parent/élève"
    )
    
    raison_echec = models.TextField(
        blank=True,
        null=True,
        verbose_name="Raison de l'échec",
        help_text="Détails sur pourquoi la liaison a échoué"
    )
    
    statut = models.CharField(
        max_length=15,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut de la demande"
    )
    
    justificatif = models.FileField(
        upload_to='justificatifs_liaison/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Justificatif",
        help_text="Document prouvant le lien familial (acte de naissance, livret de famille, etc.)"
    )
    
    message = models.TextField(
        blank=True,
        verbose_name="Message",
        help_text="Message explicatif du parent"
    )
    
    date_demande = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de la demande"
    )
    
    date_traitement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de traitement"
    )
    
    traite_par = models.ForeignKey(
        'PersonnelAdministratif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_traitees',
        verbose_name="Traité par"
    )
    
    motif_refus = models.TextField(
        blank=True,
        verbose_name="Motif du refus",
        help_text="Raison du refus de la demande"
    )
    
    # Stockage de l'élève trouvé (après validation)
    eleve_valide = models.ForeignKey(
        'Eleve',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_liaison_recues',
        verbose_name="Élève validé"
    )
    
    class Meta:
        ordering = ['-date_demande']
        verbose_name = "Demande de liaison parent"
        verbose_name_plural = "Demandes de liaison parent"
        indexes = [
            models.Index(fields=['statut', '-date_demande']),
            models.Index(fields=['matricule_eleve']),
        ]
    
    def __str__(self):
        return f"{self.parent_demandeur.nom_complet} → {self.nom_eleve} {self.prenom_eleve} ({self.get_statut_display()})"
    
    def clean(self):
        """Validation de la demande"""
        from .eleve_model import Eleve
        # Vérifier que le matricule existe
        try:
            eleve = Eleve.objects.get(
                matricule_eleve=self.matricule_eleve,
                actif=True
            )
            
            # Vérifier la correspondance nom/prénom/date de naissance
            if eleve.nom.upper() != self.nom_eleve.upper():
                raise ValidationError({
                    'nom_eleve': "Le nom ne correspond pas au matricule fourni."
                })
            
            if eleve.prenom.upper() != self.prenom_eleve.upper():
                raise ValidationError({
                    'prenom_eleve': "Le prénom ne correspond pas au matricule fourni."
                })
            
            if eleve.date_naissance != self.date_naissance_eleve:
                raise ValidationError({
                    'date_naissance_eleve': "La date de naissance ne correspond pas au matricule fourni."
                })
            
            # Vérifier qu'il n'existe pas déjà un lien
            from .lien_familial_model import LienFamilial
            lien_existant = LienFamilial.objects.filter(
                parent=self.parent_demandeur,
                eleve=eleve,
                actif=True
            ).exists()
            
            if lien_existant:
                raise ValidationError(
                    "Un lien familial existe déjà entre ce parent et cet élève."
                )
            
            # Stocker l'élève validé
            self.eleve_valide = eleve
            
        except Eleve.DoesNotExist:
            raise ValidationError({
                'matricule_eleve': "Aucun élève actif ne correspond à ce matricule."
            })
    
    def approuver(self, traite_par=None):
        """Approuve la demande et crée le lien familial"""
        from .lien_familial_model import LienFamilial
        
        if self.statut != 'en_attente':
            raise ValueError("Cette demande a déjà été traitée.")
        
        if not self.eleve_valide:
            raise ValueError("L'élève n'a pas été validé.")
        
        # Créer le lien familial
        lien = LienFamilial.objects.create(
            parent=self.parent_demandeur,
            eleve=self.eleve_valide,
            type_lien=self.type_lien,
            statut='valide',
            est_inscripteur=False
        )
        lien.valider()
        
        # Mettre à jour la demande
        self.statut = 'approuvee'
        self.date_traitement = timezone.now()
        self.traite_par = traite_par
        self.save()
        
        return lien
    
    def refuser(self, motif, traite_par=None):
        """Refuse la demande"""
        if self.statut != 'en_attente':
            raise ValueError("Cette demande a déjà été traitée.")
        
        self.statut = 'refusee'
        self.motif_refus = motif
        self.date_traitement = timezone.now()
        self.traite_par = traite_par
        self.save()

