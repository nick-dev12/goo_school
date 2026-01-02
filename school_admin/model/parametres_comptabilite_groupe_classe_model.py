# school_admin/model/parametres_comptabilite_groupe_classe_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from decimal import Decimal
import re
from .etablissement_model import Etablissement


class ParametresComptabiliteGroupeClasse(models.Model):
    """
    Modèle pour gérer les paramètres de comptabilité spécifiques à des groupes de classes
    Permet d'avoir des paramètres différents selon les groupes de classes (ex: CE1, CE2, 6eme, etc.)
    """
    
    TYPE_FACTURATION_CHOICES = [
        ('mensuel', 'Facturation mensuelle'),
        ('annuel', 'Facturation annuelle'),
    ]
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='parametres_comptabilite_groupes',
        verbose_name="Établissement"
    )
    
    # Nom du paramètre (pour identifier facilement)
    nom = models.CharField(
        max_length=200,
        verbose_name="Nom du paramètre",
        help_text="Ex: 'Paramètres pour classes primaires', 'Paramètres pour classes secondaires'"
    )
    
    # Groupes de classes concernés (stockés sous forme de JSON)
    # Format: ["CE1", "CE2", "6eme", "5eme", etc.]
    groupes_classes = models.JSONField(
        default=list,
        verbose_name="Groupes de classes",
        help_text="Liste des noms de groupes de classes concernés par ces paramètres"
    )
    
    # Montants (mêmes champs que ParametresComptabilite)
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
        related_name='parametres_comptabilite_groupes_modifies',
        verbose_name="Modifié par"
    )
    
    class Meta:
        verbose_name = "Paramètres de comptabilité par groupe de classes"
        verbose_name_plural = "Paramètres de comptabilité par groupe de classes"
        ordering = ['-date_modification']
        indexes = [
            models.Index(fields=['etablissement']),
        ]
    
    def __str__(self):
        groupes_str = ', '.join(self.groupes_classes) if self.groupes_classes else 'Aucun groupe'
        return f"{self.nom} - {groupes_str}"
    
    def clean(self):
        """
        Validation pour vérifier qu'un groupe de classes n'est pas déjà inclus dans un autre paramètre
        """
        super().clean()
        
        if not self.groupes_classes:
            raise ValidationError({
                'groupes_classes': "Vous devez sélectionner au moins un groupe de classes."
            })
        
        # Vérifier les doublons pour les groupes déjà assignés à d'autres paramètres
        if self.pk:  # Si c'est une modification
            autres_parametres = ParametresComptabiliteGroupeClasse.objects.filter(
                etablissement=self.etablissement
            ).exclude(pk=self.pk)
        else:  # Si c'est une création
            autres_parametres = ParametresComptabiliteGroupeClasse.objects.filter(
                etablissement=self.etablissement
            )
        
        groupes_deja_utilises = []
        for autre_parametre in autres_parametres:
            groupes_communs = set(self.groupes_classes) & set(autre_parametre.groupes_classes)
            if groupes_communs:
                groupes_deja_utilises.extend(list(groupes_communs))
        
        if groupes_deja_utilises:
            groupes_uniques = list(set(groupes_deja_utilises))
            raise ValidationError({
                'groupes_classes': f"Les groupes suivants sont déjà assignés à un autre paramètre : {', '.join(groupes_uniques)}"
            })
    
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
    
    @classmethod
    def get_parametres_for_classe(cls, etablissement, nom_groupe_classe):
        """
        Retourne les paramètres spécifiques pour un groupe de classes donné
        Retourne None si aucun paramètre spécifique n'existe
        """
        try:
            return cls.objects.get(
                etablissement=etablissement,
                groupes_classes__contains=[nom_groupe_classe]
            )
        except (cls.DoesNotExist, cls.MultipleObjectsReturned):
            return None
    
    @classmethod
    def get_groupes_disponibles(cls, etablissement):
        """
        Récupère la liste des groupes de classes disponibles dans l'établissement
        en analysant les noms des classes actives
        """
        from .classe_model import Classe
        import re
        
        classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('niveau', 'nom')
        groupes = set()
        
        for classe in classes:
            nom = classe.nom
            # Pattern pour extraire le groupe (ex: "CE1" de "CE1 A")
            match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
            if match:
                groupe = match.group(1).strip()
            else:
                groupe = nom.strip()
            
            if groupe:
                groupes.add(groupe)
        
        return sorted(list(groupes))
    
    @classmethod
    def get_groupes_deja_assignes(cls, etablissement, exclude_pk=None):
        """
        Récupère la liste des groupes de classes déjà assignés à un paramètre spécifique
        """
        queryset = cls.objects.filter(etablissement=etablissement)
        if exclude_pk:
            queryset = queryset.exclude(pk=exclude_pk)
        
        groupes_assignes = set()
        for parametre in queryset:
            groupes_assignes.update(parametre.groupes_classes)
        
        return sorted(list(groupes_assignes))
    
    def mettre_a_jour_systeme_comptabilite(self):
        """
        Met à jour automatiquement tout le système de comptabilité après modification des paramètres spécifiques.
        Cette méthode est appelée après la sauvegarde des paramètres pour aligner toutes les données.
        
        Actions effectuées :
        1. Récupère toutes les classes qui appartiennent aux groupes configurés
        2. Pour chaque classe, récupère tous les élèves inscrits dans l'année scolaire active
        3. Initialise la comptabilité si elle n'existe pas
        4. Met à jour les frais d'inscription non payés avec les nouveaux montants
        5. Met à jour les mensualités non payées avec les nouveaux montants
        6. Crée les frais/mensualités manquants selon la nouvelle configuration
        7. Recalcule les statuts avec les nouveaux paramètres
        8. Met à jour les statuts des comptabilités élèves
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
                
                # Récupérer toutes les classes qui appartiennent aux groupes configurés
                from .classe_model import Classe
                classes_concernées = []
                
                # Récupérer toutes les classes actives de l'établissement
                toutes_classes = Classe.objects.filter(etablissement=self.etablissement, actif=True)
                
                for classe in toutes_classes:
                    # Extraire le nom du groupe de cette classe
                    nom = classe.nom
                    match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', nom)
                    if match:
                        nom_groupe = match.group(1).strip()
                    else:
                        nom_groupe = nom.strip()
                    
                    # Vérifier si ce groupe fait partie des groupes configurés
                    if nom_groupe in self.groupes_classes:
                        classes_concernées.append(classe)
                
                if not classes_concernées:
                    return True  # Aucune classe concernée
                
                eleves_initialises = 0
                frais_crees = 0
                mensualites_creees = 0
                
                # Pour chaque classe concernée
                for classe in classes_concernées:
                    # Récupérer tous les élèves inscrits dans cette classe pour l'année scolaire active
                    inscriptions = InscriptionEleve.objects.filter(
                        classe=classe,
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active,
                        eleve__isnull=False
                    ).select_related('eleve')
                    
                    for inscription in inscriptions:
                        eleve = inscription.eleve
                        if not eleve or not eleve.actif:
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
                        
                        # 1. Créer ou mettre à jour les frais d'inscription/réinscription
                        frais_existant = FraisInscription.objects.filter(
                            eleve=eleve,
                            etablissement=self.etablissement,
                            annee_scolaire=annee_scolaire_active
                        ).first()
                        
                        if not frais_existant:
                            # Créer les frais d'inscription
                            type_frais = 'inscription'
                            if inscription.statut == 'reinscription':
                                type_frais = 'reinscription'
                            
                            montant = Decimal('0.00')
                            if self.etablissement.type_etablissement_comptabilite == 'prive':
                                if type_frais == 'reinscription' and self.montant_frais_reinscription:
                                    montant = self.montant_frais_reinscription
                                else:
                                    montant = self.montant_frais_inscription or Decimal('0.00')
                            else:  # public
                                montant = self.montant_facturation_annuelle or Decimal('0.00')
                            
                            if montant > Decimal('0.00'):
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
                        else:
                            # Mettre à jour les frais existants non payés (uniquement si montant_paye == 0)
                            if frais_existant.montant_paye == Decimal('0.00'):
                                nouveau_montant = Decimal('0.00')
                                if self.etablissement.type_etablissement_comptabilite == 'prive':
                                    if frais_existant.type_frais == 'reinscription' and self.montant_frais_reinscription:
                                        nouveau_montant = self.montant_frais_reinscription
                                    else:
                                        nouveau_montant = self.montant_frais_inscription or Decimal('0.00')
                                else:  # public
                                    nouveau_montant = self.montant_facturation_annuelle or Decimal('0.00')
                                
                                if nouveau_montant > Decimal('0.00') and frais_existant.montant != nouveau_montant:
                                    frais_existant.montant = nouveau_montant
                                    frais_existant.reste_a_payer = nouveau_montant
                                    frais_existant.save(update_fields=['montant', 'reste_a_payer'])
                            else:
                                # Si déjà payé, on met à jour seulement le reste à payer si nécessaire
                                nouveau_montant = Decimal('0.00')
                                if self.etablissement.type_etablissement_comptabilite == 'prive':
                                    if frais_existant.type_frais == 'reinscription' and self.montant_frais_reinscription:
                                        nouveau_montant = self.montant_frais_reinscription
                                    else:
                                        nouveau_montant = self.montant_frais_inscription or Decimal('0.00')
                                else:  # public
                                    nouveau_montant = self.montant_facturation_annuelle or Decimal('0.00')
                                
                                if nouveau_montant > Decimal('0.00') and frais_existant.montant != nouveau_montant:
                                    # Conserver le montant payé, mais mettre à jour le montant total
                                    frais_existant.montant = nouveau_montant
                                    reste = nouveau_montant - frais_existant.montant_paye
                                    
                                    # Si le nouveau montant est inférieur ou égal au montant déjà payé, tout est payé
                                    if reste <= Decimal('0.00'):
                                        frais_existant.montant_paye = nouveau_montant
                                        frais_existant.reste_a_payer = Decimal('0.00')
                                        frais_existant.statut = 'paye'
                                        if not frais_existant.date_paiement:
                                            frais_existant.date_paiement = timezone.now()
                                    else:
                                        frais_existant.reste_a_payer = reste
                                        # Si le statut était 'paye' mais qu'il reste à payer, changer le statut
                                        if frais_existant.statut == 'paye':
                                            frais_existant.statut = 'en_attente'
                                    
                                    frais_existant.save(update_fields=['montant', 'montant_paye', 'reste_a_payer', 'statut', 'date_paiement'])
                        
                        # 2. Créer ou mettre à jour les mensualités pour les établissements privés
                        if self.etablissement.type_etablissement_comptabilite == 'prive' and self.montant_mensualite and self.montant_mensualite > Decimal('0.00'):
                            # Générer les mensualités selon la période de facturation
                            mois_debut = self.mois_debut_facturation
                            mois_fin = self.mois_fin_facturation
                            annee_debut = annee_scolaire_active.annee_debut
                            annee_fin = annee_scolaire_active.annee_fin
                            
                            noms_mois = [
                                '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                                'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
                            ]
                            
                            mois_courant = mois_debut
                            annee_courante = annee_debut
                            periode_sur_deux_annees = mois_fin < mois_debut
                            
                            while True:
                                date_debut_mois = date(annee_courante, mois_courant, 1)
                                if date_debut_mois < annee_scolaire_active.date_debut or date_debut_mois > annee_scolaire_active.date_fin:
                                    mois_courant += 1
                                    if mois_courant > 12:
                                        mois_courant = 1
                                        annee_courante += 1
                                    
                                    if periode_sur_deux_annees:
                                        if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                            break
                                    else:
                                        if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                            break
                                    continue
                                
                                mensualite_existante = Mensualite.objects.filter(
                                    eleve=eleve,
                                    etablissement=self.etablissement,
                                    annee_scolaire=annee_scolaire_active,
                                    mois=mois_courant,
                                    annee=annee_courante
                                ).first()
                                
                                if not mensualite_existante:
                                    # Créer la mensualité
                                    dernier_jour_mois = monthrange(annee_courante, mois_courant)[1]
                                    date_echeance = date(annee_courante, mois_courant, dernier_jour_mois)
                                    periode = f"{noms_mois[mois_courant]} {annee_courante}"
                                    
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
                                else:
                                    # Mettre à jour la mensualité non payée (uniquement si montant_paye == 0)
                                    if mensualite_existante.montant_paye == Decimal('0.00'):
                                        if mensualite_existante.montant != self.montant_mensualite:
                                            mensualite_existante.montant = self.montant_mensualite
                                            mensualite_existante.save(update_fields=['montant'])
                                    else:
                                        # Si déjà payé partiellement ou totalement, mettre à jour le montant total et recalculer le reste
                                        if mensualite_existante.montant != self.montant_mensualite:
                                            ancien_montant = mensualite_existante.montant
                                            mensualite_existante.montant = self.montant_mensualite
                                            reste = self.montant_mensualite - mensualite_existante.montant_paye
                                            
                                            # Si le nouveau montant est inférieur ou égal au montant déjà payé, tout est payé
                                            if reste <= Decimal('0.00'):
                                                mensualite_existante.montant_paye = self.montant_mensualite
                                                mensualite_existante.reste_a_payer = Decimal('0.00')
                                                mensualite_existante.statut = 'paye'
                                                if not mensualite_existante.date_paiement:
                                                    mensualite_existante.date_paiement = timezone.now()
                                                mensualite_existante.date_dernier_paiement_partiel = None
                                            else:
                                                # Recalculer le reste à payer
                                                mensualite_existante.reste_a_payer = reste
                                                # Si le statut était 'paye' mais qu'il reste à payer, changer le statut
                                                if mensualite_existante.statut == 'paye':
                                                    mensualite_existante.statut = 'en_attente'
                                            
                                            # Recalculer le statut avec les nouveaux paramètres
                                            mensualite_existante.mettre_a_jour_statut(self)
                                            mensualite_existante.save(update_fields=['montant', 'montant_paye', 'reste_a_payer', 'statut', 'date_paiement', 'date_dernier_paiement_partiel'])
                                
                                mois_courant += 1
                                if mois_courant > 12:
                                    mois_courant = 1
                                    annee_courante += 1
                                
                                if periode_sur_deux_annees:
                                    if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                        break
                                else:
                                    if annee_courante > annee_fin or (annee_courante == annee_fin and mois_courant > mois_fin):
                                        break
                        
                        # 3. Recalculer les statuts de TOUTES les mensualités avec les nouveaux paramètres
                        # (même celles qui ont déjà été payées partiellement ou totalement)
                        if self.etablissement.type_etablissement_comptabilite == 'prive':
                            mensualites_eleve = Mensualite.objects.filter(
                                comptabilite_eleve=comptabilite,
                                etablissement=self.etablissement,
                                annee_scolaire=annee_scolaire_active
                            )
                            for mensualite in mensualites_eleve:
                                # Recalculer le statut avec les nouveaux paramètres spécifiques
                                mensualite.mettre_a_jour_statut(self)
                        
                        # 4. Mettre à jour le statut de la comptabilité
                        comptabilite.verifier_statut_paiement()
                
                return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la mise à jour du système de comptabilité pour les paramètres spécifiques : {str(e)}")
            return False

