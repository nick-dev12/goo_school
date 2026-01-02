# school_admin/model/comptabilite_eleve_model.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from .etablissement_model import Etablissement
from .eleve_model import Eleve
from .annee_scolaire_model import AnneeScolaire


class ComptabiliteEleve(models.Model):
    """
    Modèle pour suivre la comptabilité globale d'un élève pour une année scolaire
    """
    
    STATUT_CHOICES = [
        ('a_jour', 'À jour'),
        ('en_retard', 'En retard'),
        ('impaye', 'Impayé'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='comptabilites',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='comptabilites_eleves',
        verbose_name="Établissement"
    )
    
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='comptabilites_eleves',
        verbose_name="Année scolaire"
    )
    
    statut_paiement = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='a_jour',
        verbose_name="Statut de paiement"
    )
    
    date_derniere_verification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de dernière vérification"
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    class Meta:
        verbose_name = "Comptabilité élève"
        verbose_name_plural = "Comptabilités élèves"
        unique_together = ['eleve', 'annee_scolaire']
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['eleve', 'annee_scolaire']),
            models.Index(fields=['etablissement', 'statut_paiement']),
        ]
    
    def __str__(self):
        return f"Comptabilité {self.eleve.nom_complet} - {self.annee_scolaire.libelle}"
    
    def calculer_total_du(self):
        """
        Calcule le total dû par l'élève (frais d'inscription + mensualités)
        """
        total = Decimal('0.00')
        
        # Frais d'inscription
        for frais in self.frais_inscriptions.all():
            total += frais.montant
        
        # Mensualités
        for mensualite in self.mensualites.all():
            total += mensualite.montant
        
        return total
    
    def calculer_total_paye(self):
        """
        Calcule le total payé par l'élève en utilisant les champs montant_paye
        """
        total = Decimal('0.00')
        
        # Total payé pour les frais d'inscription
        for frais in self.frais_inscriptions.all():
            total += frais.montant_paye
        
        # Total payé pour les mensualités
        for mensualite in self.mensualites.all():
            total += mensualite.montant_paye
        
        return total
    
    def verifier_statut_paiement(self):
        """
        Vérifie automatiquement si l'élève est à jour et met à jour le statut
        """
        maintenant = timezone.now().date()
        
        # Vérifier les frais d'inscription en retard
        frais_en_retard = self.frais_inscriptions.filter(
            statut__in=['en_attente', 'en_retard'],
            date_echeance__lt=maintenant
        ).exists()
        
        # Vérifier les mensualités en retard
        mensualites_en_retard = self.mensualites.filter(
            statut__in=['en_attente', 'en_retard', 'impaye'],
            date_echeance__lt=maintenant
        ).exists()
        
        # Vérifier s'il y a des impayés
        mensualites_impayees = self.mensualites.filter(statut='impaye').exists()
        
        if mensualites_impayees:
            nouveau_statut = 'impaye'
        elif frais_en_retard or mensualites_en_retard:
            nouveau_statut = 'en_retard'
        else:
            nouveau_statut = 'a_jour'
        
        if self.statut_paiement != nouveau_statut:
            self.statut_paiement = nouveau_statut
            self.save(update_fields=['statut_paiement', 'date_derniere_verification'])
        
        return nouveau_statut
    
    def est_non_en_regle(self, parametres=None):
        """
        Vérifie si l'élève est "non en règle" selon les critères :
        - Des factures mensuelles passées impayées ou en retard
        - Des factures avec reste à payer qui ont dépassé la date de 15 jours supplémentaires
        """
        from datetime import timedelta
        maintenant = timezone.now().date()
        
        # Récupérer les paramètres si non fournis
        if parametres is None:
            try:
                from ..model.parametres_comptabilite_model import ParametresComptabilite
                parametres = ParametresComptabilite.objects.get(etablissement=self.etablissement)
            except:
                parametres = None
        
        delai_tolerance = 15
        if parametres:
            delai_tolerance = parametres.delai_tolerance_retard or 15
        
        # 1. Vérifier les mensualités passées impayées ou en retard
        mensualites_passees = self.mensualites.filter(
            date_echeance__lt=maintenant
        )
        
        for mensualite in mensualites_passees:
            # Si la mensualité n'est pas totalement payée
            if not mensualite.est_totalement_paye():
                # Vérifier si c'est impayé ou en retard
                if mensualite.statut in ['impaye', 'en_retard']:
                    return True
                # Si c'est en attente mais que la date d'échéance est passée
                if mensualite.statut == 'en_attente':
                    return True
        
        # 2. Vérifier les frais d'inscription avec reste à payer qui ont dépassé 15 jours
        frais_inscription = self.frais_inscriptions.all()
        for frais in frais_inscription:
            # Utiliser le champ reste_a_payer s'il existe, sinon calculer
            if hasattr(frais, 'reste_a_payer'):
                reste_a_payer = frais.reste_a_payer
            else:
                reste_a_payer = frais.montant - frais.montant_paye
            if reste_a_payer > Decimal('0.00'):
                # Vérifier si la date d'échéance + 15 jours est passée
                date_limite = frais.date_echeance + timedelta(days=delai_tolerance)
                if maintenant > date_limite:
                    return True
        
        # 3. Vérifier les mensualités avec reste à payer qui ont dépassé 15 jours depuis le dernier paiement partiel
        for mensualite in mensualites_passees:
            reste_a_payer = mensualite.get_reste_a_payer()
            if reste_a_payer > Decimal('0.00'):
                # Si il y a une date de dernier paiement partiel
                if mensualite.date_dernier_paiement_partiel:
                    date_limite = mensualite.date_dernier_paiement_partiel.date() + timedelta(days=delai_tolerance)
                    if maintenant > date_limite:
                        return True
                # Sinon, vérifier par rapport à la date d'échéance
                else:
                    date_limite = mensualite.date_echeance + timedelta(days=delai_tolerance)
                    if maintenant > date_limite:
                        return True
        
        return False


class FraisInscription(models.Model):
    """
    Modèle pour gérer les frais d'inscription/réinscription
    """
    
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('paye', 'Payé'),
        ('en_retard', 'En retard'),
    ]
    
    TYPE_FRAIS_CHOICES = [
        ('inscription', 'Inscription'),
        ('reinscription', 'Réinscription'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='frais_inscriptions',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='frais_inscriptions',
        verbose_name="Établissement"
    )
    
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='frais_inscriptions',
        verbose_name="Année scolaire"
    )
    
    comptabilite_eleve = models.ForeignKey(
        ComptabiliteEleve,
        on_delete=models.CASCADE,
        related_name='frais_inscriptions',
        verbose_name="Comptabilité élève"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant"
    )
    
    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant payé",
        help_text="Montant déjà payé pour ces frais d'inscription"
    )
    
    reste_a_payer = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Reste à payer",
        help_text="Montant restant à payer pour ces frais d'inscription"
    )
    
    date_echeance = models.DateField(
        verbose_name="Date d'échéance"
    )
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )
    
    type_frais = models.CharField(
        max_length=20,
        choices=TYPE_FRAIS_CHOICES,
        verbose_name="Type de frais"
    )
    
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de paiement"
    )
    
    def get_reste_a_payer(self):
        """
        Calcule le reste à payer et synchronise le champ reste_a_payer
        """
        reste = self.montant - self.montant_paye
        reste_calcule = reste if reste > Decimal('0.00') else Decimal('0.00')
        
        # Synchroniser le champ reste_a_payer avec le calcul
        # (sans sauvegarder pour éviter les boucles infinies)
        self.reste_a_payer = reste_calcule
        
        return reste_calcule
    
    def est_totalement_paye(self):
        """
        Vérifie si les frais sont totalement payés
        """
        return self.montant_paye >= self.montant
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    class Meta:
        verbose_name = "Frais d'inscription"
        verbose_name_plural = "Frais d'inscription"
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['eleve', 'annee_scolaire']),
            models.Index(fields=['etablissement', 'statut']),
        ]
    
    def __str__(self):
        return f"Frais {self.get_type_frais_display()} - {self.eleve.nom_complet} - {self.montant}"
    
    def marquer_comme_paye(self):
        """
        Marque les frais d'inscription comme payés
        """
        self.montant_paye = self.montant
        self.reste_a_payer = Decimal('0.00')
        self.statut = 'paye'
        self.date_paiement = timezone.now()
        self.save(update_fields=['montant_paye', 'reste_a_payer', 'statut', 'date_paiement'])
    
    def ajouter_paiement(self, montant):
        """
        Ajoute un paiement partiel ou total et met à jour le reste à payer
        """
        from decimal import Decimal
        # S'assurer que montant_paye est bien un Decimal
        montant_paye_actuel = Decimal(str(self.montant_paye)) if self.montant_paye else Decimal('0.00')
        montant_a_ajouter = Decimal(str(montant))
        
        # Ajouter le montant au montant déjà payé
        nouveau_montant_paye = montant_paye_actuel + montant_a_ajouter
        
        # S'assurer qu'on ne dépasse pas le montant total
        if nouveau_montant_paye > self.montant:
            nouveau_montant_paye = self.montant
        
        self.montant_paye = nouveau_montant_paye
        
        # Calculer et mettre à jour le reste à payer
        reste = self.montant - nouveau_montant_paye
        self.reste_a_payer = reste if reste > Decimal('0.00') else Decimal('0.00')
        
        # Mettre à jour le statut
        if self.est_totalement_paye():
            self.statut = 'paye'
            if not self.date_paiement:
                self.date_paiement = timezone.now()
        else:
            self.statut = 'en_attente'
        
        self.save(update_fields=['montant_paye', 'reste_a_payer', 'statut', 'date_paiement'])


class Mensualite(models.Model):
    """
    Modèle pour gérer les mensualités mensuelles
    """
    
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('paye', 'Payé'),
        ('en_retard', 'En retard'),
        ('impaye', 'Impayé'),
        ('mp', 'Mois Précédents'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='mensualites',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='mensualites',
        verbose_name="Établissement"
    )
    
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='mensualites',
        verbose_name="Année scolaire"
    )
    
    comptabilite_eleve = models.ForeignKey(
        ComptabiliteEleve,
        on_delete=models.CASCADE,
        related_name='mensualites',
        verbose_name="Comptabilité élève"
    )
    
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Numéro du mois (1-12)"
    )
    
    annee = models.IntegerField(
        verbose_name="Année"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant"
    )
    
    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Montant payé",
        help_text="Montant déjà payé pour cette mensualité"
    )
    
    date_echeance = models.DateField(
        verbose_name="Date d'échéance"
    )
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )
    
    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de paiement"
    )
    
    date_dernier_paiement_partiel = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date du dernier paiement partiel",
        help_text="Date du dernier paiement partiel effectué pour cette mensualité"
    )
    
    periode = models.CharField(
        max_length=50,
        verbose_name="Période",
        help_text="Ex: Janvier 2025"
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    def get_reste_a_payer(self):
        """
        Calcule le reste à payer
        """
        reste = self.montant - self.montant_paye
        return reste if reste > Decimal('0.00') else Decimal('0.00')
    
    def est_totalement_paye(self):
        """
        Vérifie si la mensualité est totalement payée
        """
        return self.montant_paye >= self.montant
    
    class Meta:
        verbose_name = "Mensualité"
        verbose_name_plural = "Mensualités"
        unique_together = ['eleve', 'annee_scolaire', 'mois', 'annee']
        ordering = ['annee', 'mois']
        indexes = [
            models.Index(fields=['eleve', 'annee_scolaire', 'mois', 'annee']),
            models.Index(fields=['etablissement', 'statut']),
            models.Index(fields=['date_echeance']),
        ]
    
    def __str__(self):
        return f"Mensualité {self.periode} - {self.eleve.nom_complet} - {self.montant}"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        if self.mois < 1 or self.mois > 12:
            raise ValidationError({
                'mois': "Le mois doit être entre 1 et 12."
            })
    
    def marquer_comme_paye(self):
        """
        Marque la mensualité comme payée
        """
        self.montant_paye = self.montant
        self.statut = 'paye'
        self.date_paiement = timezone.now()
        self.save(update_fields=['montant_paye', 'statut', 'date_paiement'])
    
    def calculer_statut_automatique(self, parametres=None):
        """
        Calcule automatiquement le statut de la mensualité basé sur :
        - Si un mois est passé avec retard ou impayé → "impaye" (rouge) ou "en_retard" (orange)
        - Si un paiement partiel a été fait, compter 15 jours à partir de la date du dernier paiement partiel
        - Si après 15 jours le reste n'est pas payé → "impaye"
        """
        from datetime import date, timedelta
        from calendar import monthrange
        
        # Si totalement payé, statut = paye
        if self.est_totalement_paye():
            return 'paye'
        
        # Récupérer les paramètres si non fournis
        if parametres is None:
            try:
                from ..model.parametres_comptabilite_model import ParametresComptabilite
                parametres = ParametresComptabilite.objects.get(etablissement=self.etablissement)
            except:
                # Si pas de paramètres, utiliser la logique par défaut
                maintenant = timezone.now().date()
                if self.date_echeance < maintenant:
                    return 'en_retard'
                return 'en_attente'
        
        maintenant = timezone.now().date()
        jour_versement = parametres.jour_versement or 5
        paiement_en_avance = parametres.paiement_en_avance
        delai_tolerance = parametres.delai_tolerance_retard or 15
        
        # Construire la date de versement pour ce mois
        mois_mensualite = self.mois
        annee_mensualite = self.annee
        
        if paiement_en_avance:
            date_versement_attendu = date(annee_mensualite, mois_mensualite, min(jour_versement, monthrange(annee_mensualite, mois_mensualite)[1]))
        else:
            mois_suivant = mois_mensualite + 1
            annee_suivante = annee_mensualite
            if mois_suivant > 12:
                mois_suivant = 1
                annee_suivante += 1
            date_versement_attendu = date(annee_suivante, mois_suivant, min(jour_versement, monthrange(annee_suivante, mois_suivant)[1]))
        
        # Vérifier si c'est un mois précédent
        mois_actuel = maintenant.month
        annee_actuelle = maintenant.year
        
        est_mois_precedent = False
        if annee_mensualite < annee_actuelle:
            est_mois_precedent = True
        elif annee_mensualite == annee_actuelle and mois_mensualite < mois_actuel:
            est_mois_precedent = True
        
        reste_a_payer = self.get_reste_a_payer()
        
        # Si c'est un mois précédent avec reste à payer
        if est_mois_precedent and reste_a_payer > Decimal('0.00'):
            # Si non payé du tout → "impaye"
            if self.montant_paye == Decimal('0.00'):
                return 'impaye'
            
            # Si paiement partiel → vérifier les 15 jours depuis le dernier paiement partiel
            if self.date_dernier_paiement_partiel:
                date_dernier_paiement = self.date_dernier_paiement_partiel.date()
                jours_depuis_dernier_paiement = (maintenant - date_dernier_paiement).days
                # Si plus de 15 jours depuis le dernier paiement partiel et qu'il reste à payer → "impaye"
                if jours_depuis_dernier_paiement > 15 and reste_a_payer > Decimal('0.00'):
                    return 'impaye'
                # Si moins de 15 jours → "en_retard"
                return 'en_retard'
            
            # Si pas de date de dernier paiement partiel mais qu'il y a un paiement partiel
            # Vérifier la date de versement attendue
            if maintenant > date_versement_attendu:
                jours_retard = (maintenant - date_versement_attendu).days
                if jours_retard > delai_tolerance:
                    return 'en_retard'
                # Si dans le délai de tolérance → "impaye" pour un mois précédent
                return 'impaye'
            
            # Par défaut pour un mois précédent avec paiement partiel → "en_retard"
            return 'en_retard'
        
        # Si la date de versement attendue est passée
        if maintenant > date_versement_attendu:
            jours_retard = (maintenant - date_versement_attendu).days
            
            # Si non payé du tout → "impaye"
            if self.montant_paye == Decimal('0.00'):
                return 'impaye'
            
            # Si paiement partiel, vérifier les 15 jours depuis le dernier paiement partiel
            if self.date_dernier_paiement_partiel:
                date_dernier_paiement = self.date_dernier_paiement_partiel.date()
                jours_depuis_dernier_paiement = (maintenant - date_dernier_paiement).days
                # Si plus de 15 jours depuis le dernier paiement partiel et qu'il reste à payer → "impaye"
                if jours_depuis_dernier_paiement > 15 and reste_a_payer > Decimal('0.00'):
                    return 'impaye'
            
            # Si le délai de tolérance est dépassé → "en_retard"
            if jours_retard > delai_tolerance:
                return 'en_retard'
            # Si dans le délai de tolérance mais paiement partiel → "en_retard"
            if reste_a_payer > Decimal('0.00'):
                return 'en_retard'
        
        # Si la date de versement n'est pas encore arrivée
        if maintenant < date_versement_attendu:
            # Si paiement partiel, vérifier les 15 jours depuis le dernier paiement partiel
            if self.date_dernier_paiement_partiel:
                date_dernier_paiement = self.date_dernier_paiement_partiel.date()
                jours_depuis_dernier_paiement = (maintenant - date_dernier_paiement).days
                # Si plus de 15 jours depuis le dernier paiement partiel et qu'il reste à payer → "impaye"
                if jours_depuis_dernier_paiement > 15 and reste_a_payer > Decimal('0.00'):
                    return 'impaye'
            # Si non payé → "en_attente"
            if self.montant_paye == Decimal('0.00'):
                return 'en_attente'
            # Si partiellement payé → "en_attente"
            return 'en_attente'
        
        # Si on est exactement à la date de versement
        if maintenant == date_versement_attendu:
            if self.montant_paye == Decimal('0.00'):
                return 'impaye'
            elif not self.est_totalement_paye():
                return 'en_attente'
        
        return 'en_attente'
    
    def mettre_a_jour_statut(self, parametres=None):
        """
        Met à jour le statut de la mensualité en utilisant le calcul automatique
        """
        nouveau_statut = self.calculer_statut_automatique(parametres)
        if self.statut != nouveau_statut:
            self.statut = nouveau_statut
            self.save(update_fields=['statut'])
        return nouveau_statut
    
    def ajouter_paiement(self, montant):
        """
        Ajoute un paiement partiel ou total et met à jour le statut automatiquement
        """
        from decimal import Decimal
        # S'assurer que montant_paye est bien un Decimal
        montant_paye_actuel = Decimal(str(self.montant_paye)) if self.montant_paye else Decimal('0.00')
        montant_a_ajouter = Decimal(str(montant))
        
        # Ajouter le montant au montant déjà payé
        nouveau_montant_paye = montant_paye_actuel + montant_a_ajouter
        
        # S'assurer qu'on ne dépasse pas le montant total
        if nouveau_montant_paye > self.montant:
            nouveau_montant_paye = self.montant
        
        self.montant_paye = nouveau_montant_paye
        
        # Mettre à jour le statut automatiquement
        if self.est_totalement_paye():
            self.statut = 'paye'
            if not self.date_paiement:
                self.date_paiement = timezone.now()
            # Si totalement payé, réinitialiser la date du dernier paiement partiel
            self.date_dernier_paiement_partiel = None
        else:
            # Si paiement partiel, mettre à jour la date du dernier paiement partiel
            self.date_dernier_paiement_partiel = timezone.now()
            # Utiliser le calcul automatique pour déterminer le nouveau statut
            # Utiliser les paramètres spécifiques de la classe de l'élève si disponibles
            try:
                from ..controllers.comptabilite_controller import ComptabiliteController
                from ..model.inscription_eleve_model import InscriptionEleve
                from ..model.annee_scolaire_model import AnneeScolaire
                
                # Récupérer l'année scolaire active
                annee_scolaire_active = AnneeScolaire.get_session_active(self.etablissement)
                if annee_scolaire_active:
                    # Récupérer l'inscription de l'élève pour obtenir sa classe
                    inscription = InscriptionEleve.objects.filter(
                        eleve=self.eleve,
                        etablissement=self.etablissement,
                        annee_scolaire=annee_scolaire_active
                    ).first()
                    
                    if inscription and inscription.classe:
                        # Utiliser les paramètres spécifiques de la classe
                        parametres = ComptabiliteController._get_parametres_for_classe(self.etablissement, inscription.classe)
                        if parametres:
                            self.mettre_a_jour_statut(parametres)
                        else:
                            # Fallback sur les paramètres généraux
                            from ..model.parametres_comptabilite_model import ParametresComptabilite
                            try:
                                parametres = ParametresComptabilite.objects.get(etablissement=self.etablissement)
                                self.mettre_a_jour_statut(parametres)
                            except:
                                self.statut = 'en_attente'
                    else:
                        # Pas de classe trouvée, utiliser les paramètres généraux
                        from ..model.parametres_comptabilite_model import ParametresComptabilite
                        try:
                            parametres = ParametresComptabilite.objects.get(etablissement=self.etablissement)
                            self.mettre_a_jour_statut(parametres)
                        except:
                            self.statut = 'en_attente'
                else:
                    # Pas d'année scolaire active, utiliser la logique simple
                    self.statut = 'en_attente'
            except Exception as e:
                # En cas d'erreur, utiliser la logique simple
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Erreur lors de la récupération des paramètres pour la mensualité : {str(e)}")
                self.statut = 'en_attente'
        
        self.save(update_fields=['montant_paye', 'statut', 'date_paiement', 'date_dernier_paiement_partiel'])


class PaiementEleve(models.Model):
    """
    Modèle pour enregistrer les paiements effectués par les élèves
    """
    
    TYPE_PAIEMENT_CHOICES = [
        ('frais_inscription', 'Frais d\'inscription'),
        ('mensualite', 'Mensualité'),
        ('autre', 'Autre'),
    ]
    
    MODE_PAIEMENT_CHOICES = [
        ('especes', 'Espèces'),
        ('cheque', 'Chèque'),
        ('virement', 'Virement bancaire'),
        ('mobile_money', 'Mobile Money'),
        ('carte', 'Carte bancaire'),
        ('autre', 'Autre'),
    ]
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='paiements',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='paiements_eleves',
        verbose_name="Établissement"
    )
    
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='paiements_eleves',
        verbose_name="Année scolaire"
    )
    
    type_paiement = models.CharField(
        max_length=30,
        choices=TYPE_PAIEMENT_CHOICES,
        verbose_name="Type de paiement"
    )
    
    frais_inscription = models.ForeignKey(
        FraisInscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements',
        verbose_name="Frais d'inscription"
    )
    
    mensualite = models.ForeignKey(
        Mensualite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements',
        verbose_name="Mensualité"
    )
    
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant"
    )
    
    date_paiement = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date de paiement"
    )
    
    mode_paiement = models.CharField(
        max_length=20,
        choices=MODE_PAIEMENT_CHOICES,
        verbose_name="Mode de paiement"
    )
    
    reference_paiement = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Référence de paiement",
        help_text="Numéro de chèque, référence virement, etc."
    )
    
    enregistre_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='paiements_enregistres',
        verbose_name="Enregistré par"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Notes supplémentaires sur le paiement"
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    class Meta:
        verbose_name = "Paiement élève"
        verbose_name_plural = "Paiements élèves"
        ordering = ['-date_paiement']
        indexes = [
            models.Index(fields=['eleve', 'annee_scolaire']),
            models.Index(fields=['etablissement', 'date_paiement']),
        ]
    
    def __str__(self):
        return f"Paiement {self.get_type_paiement_display()} - {self.eleve.nom_complet} - {self.montant}"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que si type_paiement est 'frais_inscription', frais_inscription doit être renseigné
        if self.type_paiement == 'frais_inscription' and not self.frais_inscription:
            raise ValidationError({
                'frais_inscription': "Le frais d'inscription doit être renseigné pour ce type de paiement."
            })
        
        # Vérifier que si type_paiement est 'mensualite', mensualite doit être renseigné
        if self.type_paiement == 'mensualite' and not self.mensualite:
            raise ValidationError({
                'mensualite': "La mensualité doit être renseignée pour ce type de paiement."
            })
    
    def save(self, *args, **kwargs):
        """
        Surcharge de save pour validation uniquement.
        IMPORTANT: Ne pas appeler ajouter_paiement() ici car cela est déjà géré dans les vues
        (payer_frais_inscription_directeur et payer_mensualite_directeur).
        Appeler ajouter_paiement() ici causerait un double comptage du paiement.
        """
        self.clean()
        super().save(*args, **kwargs)

