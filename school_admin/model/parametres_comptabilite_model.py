# school_admin/model/parametres_comptabilite_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .etablissement_model import Etablissement


class ParametresComptabilite(models.Model):
    """
    Modèle pour gérer les paramètres de comptabilité d'un établissement
    """
    
    TYPE_FACTURATION_CHOICES = [
        ('mensuel', 'Facturation mensuelle'),
        ('annuel', 'Facturation annuelle'),
    ]
    
    etablissement = models.OneToOneField(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='parametres_comptabilite',
        verbose_name="Établissement"
    )
    
    # Montants
    montant_frais_inscription = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name="Montant des frais d'inscription",
        help_text="Montant des frais d'inscription (établissements privés)"
    )
    
    montant_frais_reinscription = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name="Montant des frais de réinscription",
        help_text="Montant des frais de réinscription (peut être différent de l'inscription)"
    )
    
    montant_mensualite = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name="Montant de la mensualité",
        help_text="Montant de la mensualité mensuelle (établissements privés)"
    )
    
    montant_facturation_annuelle = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name="Montant de facturation annuelle",
        help_text="Montant annuel unique à payer (établissements publics)"
    )
    
    # Type de facturation
    type_facturation = models.CharField(
        max_length=20,
        choices=TYPE_FACTURATION_CHOICES,
        default='mensuel',
        verbose_name="Type de facturation",
        help_text="Détermine si la facturation est mensuelle ou annuelle"
    )
    
    # Autorisations et règles
    autoriser_retards = models.BooleanField(
        default=True,
        verbose_name="Autoriser les retards de paiement",
        help_text="Si activé, les élèves peuvent avoir des paiements en retard"
    )
    
    autoriser_paiements_partiels = models.BooleanField(
        default=True,
        verbose_name="Autoriser les paiements partiels",
        help_text="Si activé, les élèves peuvent payer partiellement leurs frais"
    )
    
    delai_tolerance_retard = models.PositiveIntegerField(
        default=15,
        verbose_name="Délai de tolérance pour retard (jours)",
        help_text="Nombre de jours après l'échéance avant de considérer un paiement en retard"
    )
    
    # Notifications et rappels
    envoyer_rappels_automatiques = models.BooleanField(
        default=True,
        verbose_name="Envoyer des rappels automatiques",
        help_text="Si activé, des rappels seront envoyés pour les paiements en retard"
    )
    
    jours_avant_rappel = models.PositiveIntegerField(
        default=7,
        verbose_name="Jours avant échéance pour rappel",
        help_text="Nombre de jours avant l'échéance pour envoyer un rappel"
    )
    
    jours_apres_retard_rappel = models.PositiveIntegerField(
        default=3,
        verbose_name="Jours après retard pour rappel",
        help_text="Nombre de jours après le retard pour envoyer un rappel"
    )
    
    # Période de facturation
    mois_debut_facturation = models.IntegerField(
        default=9,
        verbose_name="Mois de début de facturation",
        help_text="Mois de début de la période de facturation (1-12, ex: 9 pour septembre)",
        choices=[(i, f"{i:02d}") for i in range(1, 13)]
    )
    
    mois_fin_facturation = models.IntegerField(
        default=6,
        verbose_name="Mois de fin de facturation",
        help_text="Mois de fin de la période de facturation (1-12, ex: 6 pour juin)",
        choices=[(i, f"{i:02d}") for i in range(1, 13)]
    )
    
    # Remises et réductions
    appliquer_remise_famille_nombreuse = models.BooleanField(
        default=False,
        verbose_name="Appliquer remise famille nombreuse",
        help_text="Si activé, une remise sera appliquée pour les familles nombreuses"
    )
    
    pourcentage_remise_famille_nombreuse = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Pourcentage de remise famille nombreuse",
        help_text="Pourcentage de remise à appliquer (ex: 10.00 pour 10%)"
    )
    
    nombre_enfants_minimum_remise = models.PositiveIntegerField(
        default=3,
        verbose_name="Nombre minimum d'enfants pour remise",
        help_text="Nombre minimum d'enfants dans l'établissement pour bénéficier de la remise"
    )
    
    # Paiements multiples
    nombre_max_paiements_partiels = models.PositiveIntegerField(
        default=3,
        verbose_name="Nombre maximum de paiements partiels",
        help_text="Nombre maximum de paiements partiels autorisés pour une facture"
    )
    
    # Date de versement mensuel
    jour_versement = models.PositiveIntegerField(
        default=5,
        verbose_name="Jour de versement mensuel",
        help_text="Jour du mois où les paiements mensuels doivent être effectués (1-31, ex: 5 pour le 5 de chaque mois)",
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    
    # Type de paiement mensuel
    paiement_en_avance = models.BooleanField(
        default=False,
        verbose_name="Paiement en avance",
        help_text="Si activé, le paiement effectué le jour de versement est pour le mois en cours. Sinon, c'est pour le mois précédent."
    )
    
    # Dates
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de dernière modification"
    )
    
    modifie_par = models.ForeignKey(
        'CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parametres_comptabilite_modifies',
        verbose_name="Modifié par"
    )
    
    class Meta:
        verbose_name = "Paramètres de comptabilité"
        verbose_name_plural = "Paramètres de comptabilité"
        ordering = ['-date_modification']
    
    def __str__(self):
        return f"Paramètres comptabilité - {self.etablissement.nom}"
    
    def get_montant_inscription(self):
        """
        Retourne le montant d'inscription approprié selon le type d'établissement
        """
        if self.etablissement.type_etablissement_comptabilite == 'prive':
            return self.montant_frais_inscription or Decimal('0.00')
        else:
            return self.montant_facturation_annuelle or Decimal('0.00')
    
    def get_montant_reinscription(self):
        """
        Retourne le montant de réinscription approprié selon le type d'établissement
        """
        if self.etablissement.type_etablissement_comptabilite == 'prive':
            return self.montant_frais_reinscription or self.montant_frais_inscription or Decimal('0.00')
        else:
            return self.montant_facturation_annuelle or Decimal('0.00')
    
    def est_facturation_mensuelle(self):
        """
        Retourne True si la facturation est mensuelle
        """
        return self.type_facturation == 'mensuel' and self.etablissement.type_etablissement_comptabilite == 'prive'
    
    def est_facturation_annuelle(self):
        """
        Retourne True si la facturation est annuelle
        """
        return self.type_facturation == 'annuel' or self.etablissement.type_etablissement_comptabilite == 'public'
    
    def mettre_a_jour_systeme_comptabilite(self):
        """
        Met à jour automatiquement tout le système de comptabilité après modification des paramètres.
        Cette méthode est appelée après la sauvegarde des paramètres pour aligner toutes les données.
        
        Actions effectuées :
        1. Initialise automatiquement tous les élèves inscrits dans l'année scolaire active :
           - Crée la comptabilité élève si elle n'existe pas
           - Crée les frais d'inscription/réinscription selon le type d'inscription
           - Crée les mensualités pour les établissements privés selon la période de facturation
        2. Met à jour les frais d'inscription non payés (uniquement ceux avec montant_paye = 0) avec les nouveaux montants
        3. Met à jour les mensualités non payées (uniquement celles avec montant_paye = 0) avec les nouveaux montants
        4. Recalcule les statuts des mensualités avec les nouveaux paramètres (jour_versement, paiement_en_avance, delai_tolerance)
        5. Met à jour les statuts des comptabilités élèves
        
        Note : On ne met à jour que les montants des frais/mensualités qui n'ont pas encore été payés
        pour éviter les incohérences avec les paiements partiels déjà enregistrés.
        """
        from django.db import transaction
        from .comptabilite_eleve_model import FraisInscription, Mensualite, ComptabiliteEleve
        from .annee_scolaire_model import AnneeScolaire
        from .inscription_eleve_model import InscriptionEleve
        from datetime import date
        from calendar import monthrange
        
        try:
            with transaction.atomic():
                # Récupérer l'année scolaire active
                annee_scolaire_active = AnneeScolaire.get_session_active(self.etablissement)
                if not annee_scolaire_active:
                    return True  # Pas d'année scolaire active, on ne fait rien
                
                # ========== ÉTAPE 1 : INITIALISER TOUS LES ÉLÈVES INSCRITS ==========
                # Récupérer tous les élèves inscrits dans l'année scolaire active via InscriptionEleve
                inscriptions = InscriptionEleve.objects.filter(
                    etablissement=self.etablissement,
                    annee_scolaire=annee_scolaire_active,
                    eleve__isnull=False  # Uniquement les élèves qui existent encore
                ).select_related('eleve', 'classe')
                
                # Récupérer les groupes de classes qui ont des paramètres spécifiques
                from .parametres_comptabilite_groupe_classe_model import ParametresComptabiliteGroupeClasse
                import re
                groupes_avec_parametres_specifiques = set()
                parametres_specifiques = ParametresComptabiliteGroupeClasse.objects.filter(etablissement=self.etablissement)
                for param_spec in parametres_specifiques:
                    groupes_avec_parametres_specifiques.update(param_spec.groupes_classes)
                
                eleves_initialises = 0
                frais_crees = 0
                mensualites_creees = 0
                
                for inscription in inscriptions:
                    eleve = inscription.eleve
                    if not eleve or not eleve.actif:
                        continue
                    
                    # Vérifier si cette classe a des paramètres spécifiques
                    # Si oui, on ne met pas à jour avec les paramètres généraux
                    if inscription.classe:
                        nom = inscription.classe.nom
                        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
                        if match:
                            nom_groupe = match.group(1).strip()
                        else:
                            nom_groupe = nom.strip()
                        
                        # Si ce groupe a des paramètres spécifiques, on saute cet élève
                        if nom_groupe in groupes_avec_parametres_specifiques:
                            continue
                    
                    # Créer ou récupérer la comptabilité de l'élève
                    comptabilite, created_comptabilite = ComptabiliteEleve.objects.get_or_create(
                        eleve=eleve,
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active,
                        defaults={'statut_paiement': 'a_jour'}
                    )
                    
                    if created_comptabilite:
                        eleves_initialises += 1
                    
                    # 1.1. Créer les frais d'inscription/réinscription si ils n'existent pas
                    frais_existant = FraisInscription.objects.filter(
                        eleve=eleve,
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active
                    ).first()
                    
                    if not frais_existant:
                        # Déterminer le type de frais selon le statut d'inscription
                        type_frais = 'inscription'
                        if inscription.statut == 'reinscription':
                            type_frais = 'reinscription'
                        
                        # Déterminer le montant selon le type d'établissement et le type de frais
                        montant = Decimal('0.00')
                        
                        if self.etablissement.type_etablissement_comptabilite == 'prive':
                            if type_frais == 'reinscription' and self.montant_frais_reinscription:
                                montant = self.montant_frais_reinscription
                            else:
                                montant = self.montant_frais_inscription or Decimal('0.00')
                        else:  # public
                            montant = self.montant_facturation_annuelle or Decimal('0.00')
                        
                        # Créer les frais d'inscription si le montant est valide
                        if montant > Decimal('0.00'):
                            # Date d'échéance : 30 jours après la date d'inscription ou aujourd'hui
                            if inscription.date_inscription:
                                date_echeance = inscription.date_inscription + timedelta(days=30)
                            else:
                                date_echeance = timezone.now().date() + timedelta(days=30)
                            
                            FraisInscription.objects.create(
                                eleve=eleve,
                                etablissement=self.etablissement,
                                annee_scolaire=annee_scolaire_active,
                                comptabilite_eleve=comptabilite,
                                montant=montant,
                                date_echeance=date_echeance,
                                type_frais=type_frais,
                                statut='en_attente',
                                montant_paye=Decimal('0.00'),
                                reste_a_payer=montant
                            )
                            frais_crees += 1
                    
                    # 1.2. Créer les mensualités pour les établissements privés
                    if self.etablissement.type_etablissement_comptabilite == 'prive' and self.montant_mensualite and self.montant_mensualite > Decimal('0.00'):
                        # Générer les mensualités selon la période de facturation
                        mois_debut = self.mois_debut_facturation
                        mois_fin = self.mois_fin_facturation
                        annee_debut = annee_scolaire_active.annee_debut
                        annee_fin = annee_scolaire_active.annee_fin
                        
                        # Noms des mois en français
                        noms_mois = [
                            '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
                        ]
                        
                        # Parcourir les mois de la période de facturation
                        # La période peut s'étendre sur deux années (ex: septembre à juin)
                        mois_courant = mois_debut
                        annee_courante = annee_debut
                        
                        # Déterminer si la période s'étend sur deux années
                        periode_sur_deux_annees = mois_fin < mois_debut
                        
                        while True:
                            # Vérifier si on est dans la période de l'année scolaire
                            date_debut_mois = date(annee_courante, mois_courant, 1)
                            if date_debut_mois < annee_scolaire_active.date_debut or date_debut_mois > annee_scolaire_active.date_fin:
                                # Passer au mois suivant
                                mois_courant += 1
                                if mois_courant > 12:
                                    mois_courant = 1
                                    annee_courante += 1
                                
                                # Vérifier si on a dépassé la période
                                if periode_sur_deux_annees:
                                    # Si la période s'étend sur deux années (ex: sept à juin)
                                    # On s'arrête quand on dépasse le mois_fin de l'année suivante
                                    if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                        break
                                else:
                                    # Si la période est dans la même année (ex: jan à déc)
                                    if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                        break
                                continue
                            
                            # Vérifier si une mensualité existe déjà pour ce mois
                            mensualite_existante = Mensualite.objects.filter(
                                eleve=eleve,
                                etablissement=self.etablissement,
                                annee_scolaire=annee_scolaire_active,
                                mois=mois_courant,
                                annee=annee_courante
                            ).first()
                            
                            if not mensualite_existante:
                                # Calculer la date d'échéance (fin du mois)
                                dernier_jour_mois = monthrange(annee_courante, mois_courant)[1]
                                date_echeance = date(annee_courante, mois_courant, dernier_jour_mois)
                                
                                periode = f"{noms_mois[mois_courant]} {annee_courante}"
                                
                                # Créer la mensualité
                                Mensualite.objects.create(
                                    eleve=eleve,
                                    etablissement=self.etablissement,
                                    annee_scolaire=annee_scolaire_active,
                                    comptabilite_eleve=comptabilite,
                                    mois=mois_courant,
                                    annee=annee_courante,
                                    montant=self.montant_mensualite,
                                    date_echeance=date_echeance,
                                    periode=periode,
                                    statut='en_attente',
                                    montant_paye=Decimal('0.00')
                                )
                                mensualites_creees += 1
                            
                            # Passer au mois suivant
                            mois_courant += 1
                            if mois_courant > 12:
                                mois_courant = 1
                                annee_courante += 1
                            
                            # Vérifier si on a dépassé la période
                            if periode_sur_deux_annees:
                                # Si la période s'étend sur deux années (ex: sept à juin)
                                # On s'arrête quand on dépasse le mois_fin de l'année suivante
                                if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                    break
                            else:
                                # Si la période est dans la même année (ex: jan à déc)
                                if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                    break
                
                # ========== ÉTAPE 2 : METTRE À JOUR LES FRAIS D'INSCRIPTION EXISTANTS ==========
                # Uniquement pour les élèves qui n'ont PAS de paramètres spécifiques
                frais_inscription_non_payes = FraisInscription.objects.filter(
                    etablissement=self.etablissement,
                    annee_scolaire=annee_scolaire_active,
                    statut__in=['en_attente', 'en_retard'],
                    montant_paye=Decimal('0.00')  # Uniquement ceux qui n'ont jamais été payés
                ).select_related('eleve')
                
                for frais in frais_inscription_non_payes:
                    # Vérifier si l'élève a des paramètres spécifiques pour sa classe
                    inscription_eleve = InscriptionEleve.objects.filter(
                        eleve=frais.eleve,
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active
                    ).select_related('classe').first()
                    
                    if inscription_eleve and inscription_eleve.classe:
                        nom = inscription_eleve.classe.nom
                        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
                        if match:
                            nom_groupe = match.group(1).strip()
                        else:
                            nom_groupe = nom.strip()
                        
                        # Si ce groupe a des paramètres spécifiques, on saute ce frais
                        if nom_groupe in groupes_avec_parametres_specifiques:
                            continue
                    # Déterminer le nouveau montant selon le type d'établissement et le type de frais
                    nouveau_montant = Decimal('0.00')
                    
                    if self.etablissement.type_etablissement_comptabilite == 'prive':
                        if frais.type_frais == 'reinscription' and self.montant_frais_reinscription:
                            nouveau_montant = self.montant_frais_reinscription
                        else:
                            nouveau_montant = self.montant_frais_inscription or Decimal('0.00')
                    else:  # public
                        nouveau_montant = self.montant_facturation_annuelle or Decimal('0.00')
                    
                    # Si le montant a changé et qu'il est valide
                    if nouveau_montant > Decimal('0.00') and frais.montant != nouveau_montant:
                        # Mettre à jour le montant et le reste à payer
                        frais.montant = nouveau_montant
                        frais.reste_a_payer = nouveau_montant
                        frais.save(update_fields=['montant', 'reste_a_payer'])
                
                # ========== ÉTAPE 3 : METTRE À JOUR LES MENSUALITÉS EXISTANTES ==========
                # Uniquement pour les élèves qui n'ont PAS de paramètres spécifiques
                if self.etablissement.type_etablissement_comptabilite == 'prive' and self.montant_mensualite:
                    mensualites_non_payees = Mensualite.objects.filter(
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active,
                        statut__in=['en_attente', 'en_retard', 'impaye'],
                        montant_paye=Decimal('0.00')  # Uniquement celles qui n'ont jamais été payées
                    ).select_related('eleve')
                    
                    for mensualite in mensualites_non_payees:
                        # Vérifier si l'élève a des paramètres spécifiques pour sa classe
                        inscription_eleve = InscriptionEleve.objects.filter(
                            eleve=mensualite.eleve,
                            etablissement=self.etablissement,
                            annee_scolaire=annee_scolaire_active
                        ).select_related('classe').first()
                        
                        if inscription_eleve and inscription_eleve.classe:
                            nom = inscription_eleve.classe.nom
                            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
                            if match:
                                nom_groupe = match.group(1).strip()
                            else:
                                nom_groupe = nom.strip()
                            
                            # Si ce groupe a des paramètres spécifiques, on saute cette mensualité
                            if nom_groupe in groupes_avec_parametres_specifiques:
                                continue
                        # Si le montant a changé
                        if mensualite.montant != self.montant_mensualite:
                            # Mettre à jour le montant
                            mensualite.montant = self.montant_mensualite
                            mensualite.save(update_fields=['montant'])
                
                # ========== ÉTAPE 4 : RECALCULER LES STATUTS DES MENSUALITÉS ==========
                # Uniquement pour les élèves qui n'ont PAS de paramètres spécifiques
                if self.etablissement.type_etablissement_comptabilite == 'prive':
                    mensualites = Mensualite.objects.filter(
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active
                    ).select_related('eleve')
                    
                    for mensualite in mensualites:
                        # Vérifier si l'élève a des paramètres spécifiques pour sa classe
                        inscription_eleve = InscriptionEleve.objects.filter(
                            eleve=mensualite.eleve,
                            etablissement=self.etablissement,
                            annee_scolaire=annee_scolaire_active
                        ).select_related('classe').first()
                        
                        if inscription_eleve and inscription_eleve.classe:
                            nom = inscription_eleve.classe.nom
                            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
                            if match:
                                nom_groupe = match.group(1).strip()
                            else:
                                nom_groupe = nom.strip()
                            
                            # Si ce groupe a des paramètres spécifiques, on saute cette mensualité
                            if nom_groupe in groupes_avec_parametres_specifiques:
                                continue
                        
                        # Recalculer le statut avec les nouveaux paramètres généraux
                        mensualite.mettre_a_jour_statut(self)
                
                # ========== ÉTAPE 5 : METTRE À JOUR LES STATUTS DES COMPTABILITÉS ÉLÈVES ==========
                comptabilites = ComptabiliteEleve.objects.filter(
                    etablissement=self.etablissement,
                    annee_scolaire=annee_scolaire_active
                )
                
                for comptabilite in comptabilites:
                    comptabilite.verifier_statut_paiement()
                
                return True
        except Exception as e:
            # En cas d'erreur, on log l'erreur mais on ne bloque pas la sauvegarde des paramètres
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la mise à jour du système de comptabilité : {str(e)}")
            return False

