from django.db import models
from django.utils import timezone
from .compte_user import CompteUser


class MessageCommercial(models.Model):
    """
    Modèle pour les messages commerciaux
    """
    
    # Types de messages
    TYPE_MESSAGE_CHOICES = [
        ('demande_info', 'Demande d\'information'),
        ('proposition', 'Proposition commerciale'),
        ('suivi', 'Suivi de prospection'),
        ('rendez_vous', 'Rendez-vous'),
        ('devis', 'Devis'),
        ('contrat', 'Contrat'),
        ('support', 'Support technique'),
        ('autre', 'Autre'),
    ]
    
    # Priorités
    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('normale', 'Normale'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]
    
    # Statuts
    STATUT_CHOICES = [
        ('non_lu', 'Non lu'),
        ('lu', 'Lu'),
        ('repondu', 'Répondu'),
        ('archive', 'Archivé'),
    ]
    
    # Types d'expéditeurs
    EXPEDITEUR_CHOICES = [
        ('admin', 'Administrateur'),
        ('etablissement', 'Établissement'),
    ]
    
    # Statuts de ticket
    TICKET_STATUT_CHOICES = [
        ('ouvert', 'Ouvert'),
        ('en_cours', 'En cours'),
        ('ferme', 'Fermé'),
    ]
    
    # Champs principaux
    sujet = models.CharField(max_length=255, verbose_name="Sujet du message")
    contenu = models.TextField(verbose_name="Contenu du message")
    type_message = models.CharField(
        max_length=50, 
        choices=TYPE_MESSAGE_CHOICES, 
        default='demande_info',
        verbose_name="Type de message"
    )
    priorite = models.CharField(
        max_length=20, 
        choices=PRIORITE_CHOICES, 
        default='normale',
        verbose_name="Priorité"
    )
    statut = models.CharField(
        max_length=20, 
        choices=STATUT_CHOICES, 
        default='non_lu',
        verbose_name="Statut"
    )
    
    # Système de tickets
    expediteur_type = models.CharField(
        max_length=20,
        choices=EXPEDITEUR_CHOICES,
        default='admin',
        verbose_name="Type d'expéditeur"
    )
    ticket_statut = models.CharField(
        max_length=20,
        choices=TICKET_STATUT_CHOICES,
        default='ouvert',
        verbose_name="Statut du ticket"
    )
    pris_en_charge_par = models.ForeignKey(
        CompteUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_pris_en_charge',
        verbose_name="Pris en charge par"
    )
    date_prise_en_charge = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de prise en charge"
    )
    
    # Relations
    etablissement = models.ForeignKey(
        'school_admin.Prospection',
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name="Établissement"
    )
    expediteur = models.ForeignKey(
        CompteUser,
        on_delete=models.CASCADE,
        related_name='messages_envoyes',
        verbose_name="Expéditeur"
    )
    destinataire = models.ForeignKey(
        CompteUser,
        on_delete=models.CASCADE,
        related_name='messages_recus',
        verbose_name="Destinataire"
    )
    
    # Champs de dates
    date_envoi = models.DateTimeField(default=timezone.now, verbose_name="Date d'envoi")
    date_lecture = models.DateTimeField(null=True, blank=True, verbose_name="Date de lecture")
    date_reponse = models.DateTimeField(null=True, blank=True, verbose_name="Date de réponse")
    
    # Champs système
    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    
    class Meta:
        verbose_name = "Message commercial"
        verbose_name_plural = "Messages commerciaux"
        ordering = ['-date_envoi']
    
    def __str__(self):
        return f"{self.sujet} - {self.etablissement.nom_etablissement}"
    
    def marquer_comme_lu(self):
        """Marquer le message comme lu"""
        if self.statut == 'non_lu':
            self.statut = 'lu'
            self.date_lecture = timezone.now()
            self.save()
    
    def marquer_comme_repondu(self):
        """Marquer le message comme répondu"""
        self.statut = 'repondu'
        self.date_reponse = timezone.now()
        self.save()
    
    def archiver(self):
        """Archiver le message"""
        self.statut = 'archive'
        self.save()
    
    def prendre_en_charge(self, commercial):
        """Prendre en charge le ticket"""
        if self.ticket_statut == 'ouvert':
            self.ticket_statut = 'en_cours'
            self.pris_en_charge_par = commercial
            self.date_prise_en_charge = timezone.now()
            self.save()
            return True
        return False
    
    def fermer_ticket(self):
        """Fermer le ticket"""
        self.ticket_statut = 'ferme'
        self.save()
    
    def liberer_ticket(self):
        """Libérer le ticket"""
        self.ticket_statut = 'ouvert'
        self.pris_en_charge_par = None
        self.date_prise_en_charge = None
        self.save()


class ReponseMessage(models.Model):
    """
    Modèle pour les réponses aux messages
    """
    
    message_original = models.ForeignKey(
        MessageCommercial,
        on_delete=models.CASCADE,
        related_name='reponses',
        verbose_name="Message original"
    )
    contenu = models.TextField(verbose_name="Contenu de la réponse")
    expediteur = models.ForeignKey(
        CompteUser,
        on_delete=models.CASCADE,
        related_name='reponses_envoyees',
        verbose_name="Expéditeur"
    )
    date_envoi = models.DateTimeField(default=timezone.now, verbose_name="Date d'envoi")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    class Meta:
        verbose_name = "Réponse de message"
        verbose_name_plural = "Réponses de messages"
        ordering = ['-date_envoi']
    
    def __str__(self):
        return f"Réponse à: {self.message_original.sujet}"
