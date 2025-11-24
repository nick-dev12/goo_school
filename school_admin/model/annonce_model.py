# school_admin/model/annonce_model.py

from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement
from .personnel_administratif_model import PersonnelAdministratif


class Annonce(models.Model):
    """
    Modèle représentant les annonces publiées par le directeur ou le personnel administratif
    """
    
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('publiee', 'Publiée'),
        ('archivee', 'Archivée'),
    ]
    
    DESTINATAIRES_CHOICES = [
        ('tous', 'Tous'),
        ('enseignants', 'Enseignants'),
        ('parents', 'Parents'),
        ('eleves', 'Élèves'),
        ('personnel_administratif', 'Personnel Administratif'),
    ]
    
    # Informations de base
    titre = models.CharField(max_length=255, verbose_name="Titre de l'annonce")
    contenu = models.TextField(verbose_name="Contenu de l'annonce")
    
    # Auteur (peut être un directeur ou un membre du personnel administratif)
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='annonces',
        verbose_name="Établissement"
    )
    auteur_directeur = models.ForeignKey(
        Etablissement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='annonces_creees',
        verbose_name="Auteur (Directeur)"
    )
    auteur_personnel = models.ForeignKey(
        PersonnelAdministratif,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='annonces_creees',
        verbose_name="Auteur (Personnel)"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='annonces_annee_scolaire',
        verbose_name="Année scolaire"
    )
    
    # Gestion de la publication
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_publication = models.DateTimeField(null=True, blank=True, verbose_name="Date de publication")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    
    # Destinataires (JSONField pour permettre la sélection multiple)
    destinataires = models.JSONField(
        default=list,
        verbose_name="Destinataires"
    )
    
    # Fichier joint optionnel
    fichier_joint = models.FileField(
        upload_to='annonces/fichiers/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Fichier joint"
    )
    
    # Statut
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='brouillon',
        verbose_name="Statut"
    )
    
    # Gestion
    actif = models.BooleanField(default=True, verbose_name="Active")
    
    class Meta:
        verbose_name = "Annonce"
        verbose_name_plural = "Annonces"
        ordering = ['-date_publication', '-date_creation']
        indexes = [
            models.Index(fields=['-date_publication']),
            models.Index(fields=['etablissement', 'statut']),
        ]
    
    def __str__(self):
        return f"{self.titre} - {self.get_statut_display()}"
    
    def get_nom_auteur(self):
        """Retourne le nom complet de l'auteur"""
        if self.auteur_directeur:
            return f"{self.auteur_directeur.directeur_prenom} {self.auteur_directeur.directeur_nom}"
        elif self.auteur_personnel:
            return f"{self.auteur_personnel.prenom} {self.auteur_personnel.nom}"
        return "Auteur inconnu"
    
    def get_destinataires_display(self):
        """Retourne les destinataires de manière lisible"""
        import json
        
        # Gérer le cas où destinataires est une chaîne JSON
        destinataires_list = self.destinataires
        if isinstance(self.destinataires, str):
            try:
                destinataires_list = json.loads(self.destinataires)
            except (json.JSONDecodeError, TypeError):
                # Si c'est une simple chaîne (ancien format)
                destinataires_list = [self.destinataires]
        
        if not destinataires_list or not isinstance(destinataires_list, list):
            return "Aucun destinataire"
        
        # Dictionnaire pour mapper les codes aux labels
        choices_dict = dict(self.DESTINATAIRES_CHOICES)
        
        # Si "tous" est sélectionné, retourner uniquement "Tous"
        if 'tous' in destinataires_list:
            return "Tous"
        
        # Convertir les codes en labels
        labels = [choices_dict.get(dest, dest) for dest in destinataires_list if dest in choices_dict]
        
        if not labels:
            return "Aucun destinataire"
        
        # Joindre avec des virgules
        return ", ".join(labels)
    
    def publier(self):
        """Publie l'annonce"""
        if self.statut == 'brouillon':
            self.statut = 'publiee'
            self.date_publication = timezone.now()
            self.save()
            self.notifier_destinataires()

    def notifier_destinataires(self):
        """
        Planifie l'envoi des notifications push en arrière-plan.
        """
        from school_admin.services.notification_tasks import schedule_annonce_notification
        schedule_annonce_notification(self.id)
    
    def archiver(self):
        """Archive l'annonce"""
        if self.statut == 'publiee':
            self.statut = 'archivee'
            self.save()

