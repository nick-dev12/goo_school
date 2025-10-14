# school_admin/model/depense_model.py

from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement


class Depense(models.Model):
    """
    Modèle pour gérer les dépenses de l'organisation
    """
    
    CATEGORIE_CHOICES = [
        ('personnel', 'Personnel'),
        ('equipement', 'Équipement'),
        ('maintenance', 'Maintenance'),
        ('formation', 'Formation'),
        ('marketing', 'Marketing'),
        ('bureau', 'Bureau'),
        ('transport', 'Transport'),
        ('loyer', 'Loyer'),
        ('autre', 'Autre'),
    ]
    
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('approuve', 'Approuvé'),
        ('rejete', 'Rejeté'),
        ('paye', 'Payé'),
    ]
    
    
    # Informations de base
    description = models.CharField(
        max_length=200,
        verbose_name="Description",
        help_text="Description de la dépense"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant",
        help_text="Montant de la dépense en FCFA"
    )
    
    categorie = models.CharField(
        max_length=20,
        choices=CATEGORIE_CHOICES,
        verbose_name="Catégorie",
        help_text="Catégorie de la dépense"
    )
    
    # Dates
    date_depense = models.DateField(
        verbose_name="Date de la dépense",
        help_text="Date à laquelle la dépense a été effectuée"
    )
    
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création",
        help_text="Date de création de l'enregistrement"
    )
    
    # Statut et approbation
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut",
        help_text="Statut de la dépense"
    )
    
    # Fournisseur et paiement
    fournisseur = models.CharField(
        max_length=100,
        verbose_name="Fournisseur",
        help_text="Nom du fournisseur ou bénéficiaire"
    )
    
    
    
    # Documents et notes
    piece_jointe = models.FileField(
        upload_to='depenses/',
        blank=True,
        null=True,
        verbose_name="Pièce jointe",
        help_text="Facture, reçu ou autre document justificatif"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Notes additionnelles sur la dépense"
    )
    
    # Établissement concerné (optionnel)
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='depenses',
        verbose_name="Établissement",
        help_text="Établissement concerné par cette dépense (optionnel)"
    )
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    
    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.description} - {self.montant} FCFA"
    
    def get_categorie_display_color(self):
        """Retourne la couleur CSS pour l'affichage de la catégorie"""
        colors = {
            'personnel': '#e74c3c',
            'equipement': '#3498db',
            'maintenance': '#f39c12',
            'formation': '#9b59b6',
            'marketing': '#e67e22',
            'bureau': '#95a5a6',
            'transport': '#34495e',
            'loyer': '#2ecc71',
            'autre': '#7f8c8d',
        }
        return colors.get(self.categorie, '#95a5a6')
    
    def get_statut_display_color(self):
        """Retourne la couleur CSS pour l'affichage du statut"""
        colors = {
            'en_attente': '#f39c12',
            'approuve': '#27ae60',
            'rejete': '#e74c3c',
            'paye': '#2ecc71',
        }
        return colors.get(self.statut, '#95a5a6')
    
    def get_montant_formatted(self):
        """Retourne le montant formaté avec séparateurs de milliers"""
        return f"{self.montant:,.0f} FCFA"
    
    def is_urgent(self):
        """Détermine si la dépense est urgente (plus de 500,000 FCFA)"""
        return self.montant >= 500000
    
    def get_priority_level(self):
        """Retourne le niveau de priorité basé sur le montant"""
        if self.montant >= 1000000:
            return 'Haute'
        elif self.montant >= 500000:
            return 'Moyenne'
        else:
            return 'Basse'
    
    def can_be_approved(self):
        """Vérifie si la dépense peut être approuvée"""
        return self.statut == 'en_attente'
    
    def can_be_paid(self):
        """Vérifie si la dépense peut être payée"""
        return self.statut == 'approuve'
    
    def can_be_rejected(self):
        """Vérifie si la dépense peut être rejetée"""
        return self.statut in ['en_attente', 'approuve']
    
    @classmethod
    def get_total_by_category(cls, categorie=None):
        """Retourne le total des dépenses par catégorie"""
        queryset = cls.objects.all()
        if categorie:
            queryset = queryset.filter(categorie=categorie)
        return queryset.aggregate(total=models.Sum('montant'))['total'] or 0
    
    @classmethod
    def get_stats_by_status(cls):
        """Retourne les statistiques par statut"""
        from django.db.models import Count, Sum
        
        stats = {}
        for statut, _ in cls.STATUT_CHOICES:
            count = cls.objects.filter(statut=statut).count()
            total = cls.objects.filter(statut=statut).aggregate(total=Sum('montant'))['total'] or 0
            stats[statut] = {
                'count': count,
                'total': total
            }
        return stats
