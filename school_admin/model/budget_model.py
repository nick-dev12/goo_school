# school_admin/model/budget_model.py

from django.db import models
from django.utils import timezone
from decimal import Decimal


class Budget(models.Model):
    """
    Modèle pour gérer les budgets par catégorie
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
    
    PERIODE_CHOICES = [
        ('mensuel', 'Mensuel'),
        ('trimestriel', 'Trimestriel'),
        ('annuel', 'Annuel'),
    ]
    
    # Informations de base
    nom = models.CharField(
        max_length=200,
        verbose_name="Nom du budget",
        help_text="Nom ou description du budget"
    )
    
    categorie = models.CharField(
        max_length=20,
        choices=CATEGORIE_CHOICES,
        verbose_name="Catégorie",
        help_text="Catégorie de dépense concernée"
    )
    
    montant_alloue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant alloué",
        help_text="Montant alloué pour cette catégorie en FCFA"
    )
    
    periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        default='mensuel',
        verbose_name="Période",
        help_text="Période de validité du budget"
    )
    
    # Dates
    date_debut = models.DateField(
        verbose_name="Date de début",
        help_text="Date de début de la période budgétaire"
    )
    
    date_fin = models.DateField(
        verbose_name="Date de fin",
        help_text="Date de fin de la période budgétaire"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    date_mise_a_jour = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de dernière modification"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Indique si le budget est actif"
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Notes additionnelles sur le budget"
    )
    
    class Meta:
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"
        ordering = ['-date_creation']
        unique_together = ['categorie', 'date_debut', 'date_fin']
    
    def __str__(self):
        return f"{self.nom} - {self.get_categorie_display()} ({self.montant_alloue:,.0f} FCFA)"
    
    def get_montant_alloue_formatted(self):
        """Retourne le montant alloué formaté"""
        return f"{self.montant_alloue:,.0f} FCFA"
    
    def get_periode_display_color(self):
        """Retourne la couleur CSS pour l'affichage de la période"""
        colors = {
            'mensuel': '#3498db',
            'trimestriel': '#e67e22',
            'annuel': '#9b59b6',
        }
        return colors.get(self.periode, '#95a5a6')
    
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
    
    def get_montant_depense(self):
        """Retourne le montant dépensé pour cette catégorie dans la période"""
        from .depense_model import Depense
        
        depenses = Depense.objects.filter(
            categorie=self.categorie,
            date_depense__gte=self.date_debut,
            date_depense__lte=self.date_fin,
            statut__in=['approuve', 'paye']
        )
        
        return depenses.aggregate(total=models.Sum('montant'))['total'] or Decimal('0')
    
    def get_montant_restant(self):
        """Retourne le montant restant du budget"""
        montant_depense = self.get_montant_depense()
        return self.montant_alloue - montant_depense
    
    def get_pourcentage_utilise(self):
        """Retourne le pourcentage du budget utilisé"""
        if self.montant_alloue > 0:
            montant_depense = self.get_montant_depense()
            return round((montant_depense / self.montant_alloue) * 100, 1)
        return 0
    
    def is_depasse(self):
        """Vérifie si le budget est dépassé"""
        return self.get_montant_depense() > self.montant_alloue
    
    def get_statut_budget(self):
        """Retourne le statut du budget"""
        pourcentage = self.get_pourcentage_utilise()
        
        if pourcentage >= 100:
            return 'depasse'
        elif pourcentage >= 80:
            return 'critique'
        elif pourcentage >= 60:
            return 'attention'
        else:
            return 'normal'
    
    def get_statut_display_color(self):
        """Retourne la couleur CSS pour l'affichage du statut"""
        statut = self.get_statut_budget()
        colors = {
            'normal': '#2ecc71',
            'attention': '#f39c12',
            'critique': '#e67e22',
            'depasse': '#e74c3c',
        }
        return colors.get(statut, '#95a5a6')
    
    @classmethod
    def get_budget_total_actuel(cls):
        """Retourne le budget total actuel (toutes catégories confondues)"""
        from django.utils import timezone
        
        maintenant = timezone.now().date()
        budgets_actifs = cls.objects.filter(
            actif=True,
            date_debut__lte=maintenant,
            date_fin__gte=maintenant
        )
        
        return budgets_actifs.aggregate(total=models.Sum('montant_alloue'))['total'] or Decimal('0')
    
    @classmethod
    def get_depenses_total_actuel(cls):
        """Retourne le total des dépenses actuelles"""
        from .depense_model import Depense
        from django.utils import timezone
        
        maintenant = timezone.now().date()
        budgets_actifs = cls.objects.filter(
            actif=True,
            date_debut__lte=maintenant,
            date_fin__gte=maintenant
        )
        
        categories = [budget.categorie for budget in budgets_actifs]
        
        depenses = Depense.objects.filter(
            categorie__in=categories,
            statut__in=['approuve', 'paye']
        )
        
        return depenses.aggregate(total=models.Sum('montant'))['total'] or Decimal('0')
    
    @classmethod
    def get_budget_restant_total(cls):
        """Retourne le budget restant total"""
        budget_total = cls.get_budget_total_actuel()
        depenses_total = cls.get_depenses_total_actuel()
        return budget_total - depenses_total
