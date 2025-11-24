# school_admin/model/etablissement_model.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

class Etablissement(AbstractUser):
    """
    Modèle représentant un établissement scolaire
    """
    TYPE_CHOICES = [
        ('primary', 'École Primaire'),
        ('collège', 'Collège'),
        ('lycée', 'Lycée'),
        ('collège_lycée', 'Collège + Lycée'),
        ('mixte', 'Établissement Mixte'),
    ]
    
    # Code unique de l'établissement
    code_etablissement = models.CharField(max_length=12, unique=True, verbose_name="Code établissement")
    
    # Informations de l'établissement
    nom = models.CharField(max_length=255, verbose_name="Nom de l'établissement")
    adresse = models.CharField(max_length=255, verbose_name="Adresse")
    pays = models.CharField(max_length=255, verbose_name="Pays")
    ville = models.CharField(max_length=255, verbose_name="Ville")
    email = models.EmailField(unique=True, verbose_name="Email de l'établissement")
    telephone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Téléphone")
    type_etablissement = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type d'établissement")
    
    # Informations du directeur
    directeur_prenom = models.CharField(max_length=100, verbose_name="Prénom du directeur")
    directeur_nom = models.CharField(max_length=100, verbose_name="Nom du directeur")
    directeur_email = models.EmailField(unique=True, verbose_name="Email du directeur")
    directeur_telephone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Téléphone du directeur")
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    actif = models.BooleanField(default=True, verbose_name="Établissement actif")
    
    # Relation avec l'utilisateur qui a créé l'établissement (admin)
    cree_par = models.ForeignKey('school_admin.CompteUser', on_delete=models.SET_NULL, 
                                null=True, related_name='etablissements_crees',
                                verbose_name="Créé par")
    
    # Modules activés pour l'établissement
    module_gestion_eleves = models.BooleanField(default=False, verbose_name="Gestion des élèves")
    module_notes_evaluations = models.BooleanField(default=False, verbose_name="Notes et évaluations")
    module_emploi_temps = models.BooleanField(default=False, verbose_name="Emploi du temps")
    module_transport_scolaire = models.BooleanField(default=False, verbose_name="Transport scolaire")
    module_comptabilite = models.BooleanField(default=False, verbose_name="Comptabilité")
    module_gestion_personnel = models.BooleanField(default=False, verbose_name="Gestion du personnel")
    module_censeurs = models.BooleanField(default=False, verbose_name="Censeurs")
    module_surveillance = models.BooleanField(default=False, verbose_name="Surveillance et sécurité")
    module_cantine = models.BooleanField(default=False, verbose_name="Gestion de la cantine")
    module_bibliotheque = models.BooleanField(default=False, verbose_name="Gestion de la bibliothèque")
    module_communication = models.BooleanField(default=False, verbose_name="Communication parents")
    module_orientation = models.BooleanField(default=False, verbose_name="Orientation scolaire")
    module_sante = models.BooleanField(default=False, verbose_name="Suivi médical")
    module_activites = models.BooleanField(default=False, verbose_name="Activités extra-scolaires")
    module_formation = models.BooleanField(default=False, verbose_name="Formation continue")
    
    logo = models.ImageField(
        upload_to='etablissements/logos/',
        blank=True,
        null=True,
        verbose_name="Logo de l'établissement",
        help_text="Image utilisée comme logo officiel de l'établissement"
    )
    
    # Facturation
    type_facturation = models.CharField(
        max_length=20,
        choices=[
            ('mensuel', 'Facturation mensuelle'),
            ('annuel', 'Facturation annuelle'),
        ],
        default='mensuel',
        verbose_name="Type de facturation"
    )
    montant_par_eleve = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=3000.00, 
        verbose_name="Montant par élève (FCFA)"
    )
    montant_total_facturation = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="Montant total de facturation"
    )
    statut_paiement = models.CharField(
        max_length=20,
        choices=[
            ('en_attente', 'En attente de paiement'),
            ('paye', 'Payé'),
            ('en_retard', 'En retard'),
            ('annule', 'Annulé'),
        ],
        default='en_attente',
        verbose_name="Statut du paiement"
    )
    statut_reglementation = models.CharField(
        max_length=20,
        choices=[
            ('hors_service', 'Hors service'),
            ('en_regle', 'En règle'),
            ('en_retard', 'En retard'),
            ('non_en_regle', 'Non en règle'),
            ('contentieux', 'Contentieux'),
        ],
        default='hors_service',
        verbose_name="Statut de réglementation"
    )
    date_derniere_facturation = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Date de dernière facturation"
    )
    nombre_eleves_factures = models.PositiveIntegerField(
        default=0, 
        verbose_name="Nombre d'élèves facturés"
    )
    
    
    username = models.CharField(unique=True, max_length=100, verbose_name="Nom d'utilisateur", default="")
    USERNAME_FIELD = 'username'
    
    # Réinitialisation de mot de passe
    password_reset_code = models.CharField(max_length=6, null=True, blank=True, verbose_name="Code de réinitialisation")
    password_reset_expires = models.DateTimeField(null=True, blank=True, verbose_name="Expiration du code de réinitialisation")
    
    # Redéfinir les champs groups et user_permissions avec des related_name uniques
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this establishment belongs to.',
        related_name="etablissement_set",
        related_query_name="etablissement",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this establishment.',
        related_name="etablissement_set",
        related_query_name="etablissement",
    )
 
    
    class Meta:
        verbose_name = "Établissement"
        verbose_name_plural = "Établissements"
        ordering = ['-date_creation']
        # Configuration de l'encodage UTF-8
        db_table = 'school_admin_etablissement'
        managed = True
        
    def __str__(self):
        return f"{self.nom} ({self.get_type_etablissement_display()})"
    
    def recalculer_facturation(self):
        """
        Recalcule automatiquement le montant total de facturation et le nombre d'élèves facturés
        basé sur le nombre d'élèves actifs dans l'établissement.
        """
        from django.db.models import Count
        from decimal import Decimal
        
        # Compter les élèves actifs
        nombre_eleves_actifs = self.eleves.filter(actif=True).count()
        
        # Calculer le montant total : nombre d'élèves × montant par élève
        montant_total = Decimal(str(nombre_eleves_actifs)) * self.montant_par_eleve
        
        # Mettre à jour les champs
        self.montant_total_facturation = montant_total
        self.nombre_eleves_factures = nombre_eleves_actifs
        
        # Sauvegarder sans déclencher les signaux pour éviter les boucles infinies
        self.save(update_fields=['montant_total_facturation', 'nombre_eleves_factures'])
    
    def mettre_a_jour_statut_reglementation(self):
        """
        Met à jour automatiquement le statut de réglementation de l'établissement
        basé sur les factures et les dates d'échéance.
        
        Logique :
        - Facturation mensuelle : vérifie chaque mois depuis la date de création
        - Facturation annuelle : vérifie chaque année depuis la date de création
        - Si échéance passée sans paiement → 'en_retard'
        - Si dépassé de plus de 10 jours → 'non_en_regle'
        - Si dépassé de plus d'un mois → 'contentieux'
        - Si tout est payé → 'en_regle'
        """
        from datetime import timedelta
        from decimal import Decimal
        
        maintenant = timezone.now()
        date_creation = self.date_creation
        
        # Récupérer toutes les factures non payées ou partiellement payées
        factures_en_attente = self.facturations.filter(
            statut__in=['en_attente', 'en_retard', 'impaye']
        )
        
        factures_avec_reste = self.facturations.filter(
            paiement_partiel=True,
            reste_a_payer__gt=Decimal('0.00')
        )
        
        # Vérifier s'il y a des factures en retard
        factures_en_retard = []
        factures_non_en_regle = []
        factures_contentieux = []
        
        for facture in factures_en_attente:
            jours_retard = 0
            date_echeance = facture.date_echeance
            
            if date_echeance < maintenant:
                jours_retard = (maintenant - date_echeance).days
                
                if jours_retard > 30:  # Plus d'un mois
                    factures_contentieux.append(facture)
                elif jours_retard > 10:  # Plus de 10 jours
                    factures_non_en_regle.append(facture)
                else:  # Moins de 10 jours
                    factures_en_retard.append(facture)
        
        # Vérifier aussi les factures avec reste à payer
        # IMPORTANT : On vérifie uniquement si la date d'échéance du reste est passée
        # et qu'il y a effectivement un reste à payer
        for facture in factures_avec_reste:
            # Utiliser la date d'échéance du reste si elle existe, sinon la date d'échéance principale
            if facture.date_echeance_reste:
                date_echeance = facture.date_echeance_reste
            else:
                # Si pas de date d'échéance spécifique pour le reste, utiliser la date principale
                date_echeance = facture.date_echeance
            
            # Vérifier uniquement si la date d'échéance est passée ET qu'il y a un reste à payer
            if date_echeance < maintenant and facture.reste_a_payer > Decimal('0.00'):
                jours_retard = (maintenant - date_echeance).days
                
                if jours_retard > 30:  # Plus d'un mois
                    factures_contentieux.append(facture)
                elif jours_retard > 10:  # Plus de 10 jours
                    factures_non_en_regle.append(facture)
                else:  # Moins de 10 jours
                    factures_en_retard.append(facture)
        
        # Déterminer le statut selon la priorité
        if factures_contentieux:
            nouveau_statut = 'contentieux'
        elif factures_non_en_regle:
            nouveau_statut = 'non_en_regle'
        elif factures_en_retard:
            nouveau_statut = 'en_retard'
        else:
            # Vérifier si l'établissement a des factures en attente
            factures_en_attente_count = self.facturations.filter(
                statut='en_attente'
            ).count()
            
            if factures_en_attente_count > 0:
                # Vérifier si les factures en attente sont dans les délais
                factures_dans_delais = True
                for facture in self.facturations.filter(statut='en_attente'):
                    if facture.date_echeance < maintenant:
                        factures_dans_delais = False
                        break
                
                if factures_dans_delais:
                    nouveau_statut = 'en_regle'
                else:
                    nouveau_statut = 'en_retard'
            else:
                # Aucune facture en attente, tout est payé
                nouveau_statut = 'en_regle'
        
        # Mettre à jour le statut si différent
        if self.statut_reglementation != nouveau_statut:
            self.statut_reglementation = nouveau_statut
            self.save(update_fields=['statut_reglementation'])
        
        return nouveau_statut
    
    @classmethod
    def mettre_a_jour_tous_les_statuts(cls):
        """
        Met à jour le statut de réglementation pour tous les établissements actifs.
        """
        etablissements = cls.objects.filter(actif=True)
        compteur = 0
        
        for etablissement in etablissements:
            ancien_statut = etablissement.statut_reglementation
            nouveau_statut = etablissement.mettre_a_jour_statut_reglementation()
            
            if ancien_statut != nouveau_statut:
                compteur += 1
        
        return compteur