# school_admin/model/facturation_model.py

from django.db import models
from django.utils import timezone
from .etablissement_model import Etablissement
from .eleve_model import Eleve


class Facturation(models.Model):
    """
    Modèle pour gérer la facturation des services de gestion scolaire
    """
    
    STATUT_CHOICES = [
        ('en_attente', 'En attente de paiement'),
        ('paye', 'Payé'),
        ('en_retard', 'En retard'),
        ('impaye', 'Impayé'),
        ('contentieux', 'Contentieux'),
        ('annule', 'Annulé'),
    ]
    
    TYPE_FACTURE_CHOICES = [
        ('frais_service_mensuel', 'Frais de service mensuel'),
        ('frais_service_annuel', 'Frais de service annuel'),
        ('module_supplementaire', 'Module supplémentaire'),
    ]
    
    # Informations de base
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='facturations',
        verbose_name="Établissement"
    )
    
    numero_facture = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Numéro de facture"
    )
    
    type_facture = models.CharField(
        max_length=30,
        choices=TYPE_FACTURE_CHOICES,
        verbose_name="Type de facture"
    )
    
    # Montants
    montant_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant unitaire"
    )
    
    quantite = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantité"
    )
    
    montant_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant total"
    )
    
    # Statut et dates
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )
    
    date_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de création"
    )
    
    date_echeance = models.DateTimeField(
        verbose_name="Date d'échéance"
    )
    
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de paiement"
    )
    
    # Détails
    description = models.TextField(
        verbose_name="Description",
        help_text="Description détaillée de la facture"
    )
    
    # Élèves concernés (pour les factures d'inscription)
    eleves_concernes = models.ManyToManyField(
        Eleve,
        blank=True,
        related_name='facturations',
        verbose_name="Élèves concernés"
    )
    
    # Modules supplémentaires (champs booléens pour chaque module)
    module_surveillance = models.BooleanField(default=False, verbose_name="Surveillance et sécurité")
    module_communication = models.BooleanField(default=False, verbose_name="Communication parents")
    module_orientation = models.BooleanField(default=False, verbose_name="Orientation scolaire")
    module_formation = models.BooleanField(default=False, verbose_name="Formation continue")
    module_transport_scolaire = models.BooleanField(default=False, verbose_name="Transport scolaire")
    module_cantine = models.BooleanField(default=False, verbose_name="Gestion de la cantine")
    module_bibliotheque = models.BooleanField(default=False, verbose_name="Gestion de la bibliothèque")
    module_sante = models.BooleanField(default=False, verbose_name="Suivi médical")
    module_activites = models.BooleanField(default=False, verbose_name="Activités extra-scolaires")
    module_comptabilite = models.BooleanField(default=False, verbose_name="Comptabilité")
    module_censeurs = models.BooleanField(default=False, verbose_name="Censeurs")
    
    # Informations de paiement
    mode_paiement = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Mode de paiement"
    )
    
    reference_paiement = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Référence de paiement"
    )
    
    montant_verse = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Montant versé"
    )
    
    # Champs pour le paiement partiel
    reste_a_payer = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="Reste à payer"
    )
    
    date_echeance_reste = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'échéance du reste à payer"
    )
    
    paiement_partiel = models.BooleanField(
        default=False,
        verbose_name="Paiement partiel"
    )
    
    statut_envoi = models.BooleanField(
        default=False,
        verbose_name="Statut d'envoi"
    )
    
    class Meta:
        verbose_name = "Facturation"
        verbose_name_plural = "Facturations"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"Facture {self.numero_facture} - {self.etablissement.nom} - {self.montant_total}€"
    
    def save(self, *args, **kwargs):
        # Calculer automatiquement le montant total
        self.montant_total = self.montant_unitaire * self.quantite
        
        # Générer le numéro de facture s'il n'existe pas
        if not self.numero_facture:
            self.numero_facture = self.generer_numero_facture()
        
        super().save(*args, **kwargs)
    
    def generer_numero_facture(self):
        """Génère un numéro de facture unique"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"FAC-{timestamp}-{self.etablissement.code_etablissement}"
    
    def marquer_comme_paye(self, mode_paiement=None, reference_paiement=None):
        """Marque la facture comme payée"""
        self.statut = 'paye'
        self.date_paiement = timezone.now()
        if mode_paiement:
            self.mode_paiement = mode_paiement
        if reference_paiement:
            self.reference_paiement = reference_paiement
        self.save()
    
    def est_en_retard(self):
        """Vérifie si la facture est en retard"""
        return self.date_echeance < timezone.now() and self.statut not in ['paye', 'annule']
    
    def get_statut_display_color(self):
        """Retourne la couleur CSS pour l'affichage du statut"""
        colors = {
            'en_attente': 'warning',
            'paye': 'success',
            'en_retard': 'danger',
            'impaye': 'danger',
            'contentieux': 'danger',
            'annule': 'secondary',
        }
        return colors.get(self.statut, 'secondary')
    
    @property
    def jours_restants(self):
        """Calcule le nombre de jours restants avant échéance"""
        if self.statut in ['paye', 'annule']:
            return 0
        
        delta = self.date_echeance - timezone.now()
        return max(0, delta.days)
    
    @property
    def est_urgente(self):
        """Détermine si la facture est urgente (moins de 7 jours)"""
        return self.jours_restants <= 7 and self.jours_restants > 0
    
    def get_modules_supplementaires_display(self):
        """Retourne la liste des modules supplémentaires formatée"""
        modules_actifs = []
        
        if self.module_surveillance:
            modules_actifs.append('Surveillance et sécurité')
        if self.module_communication:
            modules_actifs.append('Communication parents')
        if self.module_orientation:
            modules_actifs.append('Orientation scolaire')
        if self.module_formation:
            modules_actifs.append('Formation continue')
        if self.module_transport_scolaire:
            modules_actifs.append('Transport scolaire')
        if self.module_cantine:
            modules_actifs.append('Gestion de la cantine')
        if self.module_bibliotheque:
            modules_actifs.append('Gestion de la bibliothèque')
        if self.module_sante:
            modules_actifs.append('Suivi médical')
        if self.module_activites:
            modules_actifs.append('Activités extra-scolaires')
        if self.module_comptabilite:
            modules_actifs.append('Comptabilité')
        if self.module_censeurs:
            modules_actifs.append('Censeurs')
        
        if not modules_actifs:
            return "Aucun module supplémentaire"
        
        return ", ".join(modules_actifs)
    
    def get_type_facture_display_detailed(self):
        """Retourne le type de facture avec plus de détails"""
        if self.type_facture == 'frais_service_mensuel':
            return f"Frais de service mensuel ({self.etablissement.get_type_facturation_display()})"
        elif self.type_facture == 'frais_service_annuel':
            return f"Frais de service annuel ({self.etablissement.get_type_facturation_display()})"
        elif self.type_facture == 'module_supplementaire':
            modules = self.get_modules_supplementaires_display()
            return f"Module supplémentaire: {modules}"
        return self.get_type_facture_display()
    
    def get_montant_par_eleve(self):
        """Retourne le montant par élève pour cette facture"""
        if self.quantite > 0:
            return self.montant_total / self.quantite
        return 0
    
    def get_nombre_eleves_concernes(self):
        """Retourne le nombre d'élèves concernés par cette facture"""
        return self.eleves_concernes.count()
    
    def est_facture_service(self):
        """Détermine si c'est une facture de service (mensuel/annuel)"""
        return self.type_facture in ['frais_service_mensuel', 'frais_service_annuel']
    
    def est_facture_module(self):
        """Détermine si c'est une facture de module supplémentaire"""
        return self.type_facture == 'module_supplementaire'
    
    def get_modules_selectionnes(self):
        """Retourne la liste des noms des modules sélectionnés"""
        modules_selectionnes = []
        
        if self.module_surveillance:
            modules_selectionnes.append('module_surveillance')
        if self.module_communication:
            modules_selectionnes.append('module_communication')
        if self.module_orientation:
            modules_selectionnes.append('module_orientation')
        if self.module_formation:
            modules_selectionnes.append('module_formation')
        if self.module_transport_scolaire:
            modules_selectionnes.append('module_transport_scolaire')
        if self.module_cantine:
            modules_selectionnes.append('module_cantine')
        if self.module_bibliotheque:
            modules_selectionnes.append('module_bibliotheque')
        if self.module_sante:
            modules_selectionnes.append('module_sante')
        if self.module_activites:
            modules_selectionnes.append('module_activites')
        if self.module_comptabilite:
            modules_selectionnes.append('module_comptabilite')
        if self.module_censeurs:
            modules_selectionnes.append('module_censeurs')
        
        return modules_selectionnes
    
    def has_any_module_selected(self):
        """Vérifie si au moins un module est sélectionné"""
        return any([
            self.module_surveillance,
            self.module_communication,
            self.module_orientation,
            self.module_formation,
            self.module_transport_scolaire,
            self.module_cantine,
            self.module_bibliotheque,
            self.module_sante,
            self.module_activites,
            self.module_comptabilite,
            self.module_censeurs,
        ])
    
    def calculer_reste_a_payer(self, montant_verse):
        """Calcule le reste à payer après un versement"""
        from decimal import Decimal
        # S'assurer que montant_verse est un Decimal
        if isinstance(montant_verse, (int, float)):
            montant_verse = Decimal(str(montant_verse))
        
        if montant_verse >= self.montant_total:
            return Decimal('0.00')
        return self.montant_total - montant_verse
    
    def traiter_paiement_partiel(self, montant_verse, date_echeance_reste=None):
        """Traite un paiement partiel"""
        from decimal import Decimal
        
        # S'assurer que montant_verse est un Decimal
        if isinstance(montant_verse, (int, float)):
            montant_verse = Decimal(str(montant_verse))
        
        # Sauvegarder le montant versé
        self.montant_verse = montant_verse
        self.reste_a_payer = self.calculer_reste_a_payer(montant_verse)
        if date_echeance_reste:
            self.date_echeance_reste = date_echeance_reste
        
        # Mettre à jour le statut - toujours "payé" quand il y a un paiement
        self.statut = 'paye'
        self.date_paiement = timezone.now()
        
        # Déterminer si c'est un paiement partiel
        if self.reste_a_payer == Decimal('0.00'):
            self.paiement_partiel = False
        else:
            self.paiement_partiel = True
        
        self.save()
    
    def est_paiement_complet(self):
        """Vérifie si le paiement est complet"""
        from decimal import Decimal
        return self.reste_a_payer == Decimal('0.00')
    
    def est_paiement_partiel(self):
        """Vérifie si c'est un paiement partiel"""
        from decimal import Decimal
        return self.paiement_partiel and self.reste_a_payer > Decimal('0.00')
    
    def marquer_comme_envoyee(self):
        """Marque la facture comme envoyée"""
        self.statut_envoi = True
        self.save()
    
    def mettre_a_jour_statut_automatique(self):
        """Met à jour automatiquement le statut basé sur les dates d'échéance"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # Si la facture est déjà payée complètement, pas de mise à jour
        if self.statut == 'paye' and self.reste_a_payer == 0:
            return
        
        # Vérifier l'échéance principale
        if self.date_echeance and self.date_echeance < now:
            jours_retard = (now - self.date_echeance).days
            
            if jours_retard >= 60:  # 2 mois
                self.statut = 'contentieux'
            elif jours_retard >= 30:  # 1 mois
                self.statut = 'impaye'
            else:
                self.statut = 'en_retard'
        
        # Vérifier l'échéance du reste à payer
        elif self.date_echeance_reste and self.date_echeance_reste < now:
            jours_retard = (now - self.date_echeance_reste).days
            
            if jours_retard >= 60:  # 2 mois
                self.statut = 'contentieux'
            elif jours_retard >= 30:  # 1 mois
                self.statut = 'impaye'
            else:
                self.statut = 'en_retard'
        
        self.save()
    
    @classmethod
    def mettre_a_jour_tous_les_statuts(cls):
        """Met à jour automatiquement tous les statuts des factures"""
        factures_a_mettre_a_jour = cls.objects.filter(
            statut__in=['en_attente', 'en_retard', 'impaye', 'contentieux']
        )
        
        for facture in factures_a_mettre_a_jour:
            facture.mettre_a_jour_statut_automatique()
        
        return factures_a_mettre_a_jour.count()
