"""Comptes de trésorerie, catégories, recettes et journal d'audit de l'école.

Ces tables prolongent la comptabilité générale. Elles ne remplacent pas
les écritures, ni la caisse des frais élèves, ni le registre des dépenses ARIA.
"""
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .comptabilite_generale_model import CompteComptable
from .etablissement_model import Etablissement


class CompteTresorerie(models.Model):
    """Caisse, banque ou mobile money nommé, relié à un compte du plan."""

    TYPE_CHOICES = [
        ('caisse', 'Caisse'),
        ('banque', 'Banque'),
        ('mobile_money', 'Mobile money'),
        ('autre', 'Autre'),
    ]
    STATUT_CHOICES = [
        ('ouvert', 'Ouvert'),
        ('ferme', 'Fermé'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='comptes_tresorerie',
    )
    type_compte = models.CharField(max_length=20, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=120)
    reference = models.CharField(max_length=80, blank=True, default='')
    compte_comptable = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        related_name='comptes_tresorerie',
    )
    devise = models.CharField(max_length=10, blank=True, default='')
    date_ouverture = models.DateField()
    solde_initial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ouvert')
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Compte de trésorerie"
        verbose_name_plural = "Comptes de trésorerie"
        constraints = [
            models.UniqueConstraint(
                fields=['etablissement', 'compte_comptable'],
                name='uniq_tresorerie_compte_comptable',
            ),
        ]
        ordering = ['type_compte', 'libelle']

    def __str__(self):
        return self.libelle


class CategorieFinanciere(models.Model):
    """Catégorie de l'école, reliée à un compte du plan. Modifiable."""

    TYPE_CHOICES = [
        ('recette', 'Recette'),
        ('sortie', 'Sortie'),
        ('financement', 'Financement'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='categories_financieres',
    )
    type_categorie = models.CharField(max_length=20, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=120)
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='enfants',
    )
    compte_comptable = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        related_name='categories_financieres',
    )
    actif = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Catégorie financière"
        verbose_name_plural = "Catégories financières"
        constraints = [
            models.UniqueConstraint(
                fields=['etablissement', 'type_categorie', 'libelle'],
                name='uniq_categorie_financiere_libelle',
            ),
        ]
        ordering = ['ordre', 'libelle']

    def __str__(self):
        return self.libelle


class PaiementCharge(models.Model):
    """Un versement sur une facture fournisseur. Plusieurs lignes possibles."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='paiements_charges',
    )
    facture = models.ForeignKey(
        'school_admin.FactureFournisseur',
        on_delete=models.PROTECT,
        related_name='paiements',
    )
    date_paiement = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='paiements_charges',
    )
    statut = models.CharField(
        max_length=12,
        choices=[
            ('brouillon', 'Brouillon'),
            ('validee', 'Validée'),
            ('annulee', 'Annulée'),
        ],
        default='validee',
    )
    motif_annulation = models.TextField(blank=True, default='')
    date_annulation = models.DateTimeField(null=True, blank=True)
    annule_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements_charges_annules',
    )
    annule_object_id = models.PositiveIntegerField(null=True, blank=True)
    annule_par = GenericForeignKey('annule_content_type', 'annule_object_id')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Paiement de charge"
        verbose_name_plural = "Paiements de charges"
        ordering = ['date_paiement', 'id']

    def __str__(self):
        return f"{self.montant} — {self.date_paiement}"


class RecetteEtablissement(models.Model):
    """Recette qui n'est pas déjà un paiement élève : activité, subvention ou divers."""

    NATURE_CHOICES = [
        ('activite', 'Activité'),
        ('subvention', 'Subvention'),
        ('divers', 'Divers'),
    ]
    DESTINATION_CHOICES = [
        ('fonctionnement', 'Fonctionnement'),
        ('equipement', 'Équipement'),
        ('projet', 'Projet'),
        ('autre', 'Autre'),
    ]
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('validee', 'Validée'),
        ('annulee', 'Annulée'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='recettes_etablissement',
    )
    annee_scolaire = models.ForeignKey(
        'school_admin.AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recettes_etablissement',
    )
    date_recette = models.DateField()
    nature = models.CharField(max_length=20, choices=NATURE_CHOICES)
    destination = models.CharField(
        max_length=20,
        choices=DESTINATION_CHOICES,
        blank=True,
        default='',
        help_text=(
            "Destination d'une subvention. Elle est affichée à côté du résultat. "
            "Elle ne retire pas le montant du résultat : seul le compte de la catégorie, "
            "s'il n'est pas en classe 7, laisse la recette hors résultat."
        ),
    )
    categorie = models.ForeignKey(
        CategorieFinanciere,
        on_delete=models.PROTECT,
        related_name='recettes',
    )
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        related_name='recettes',
    )
    libelle = models.CharField(max_length=200, blank=True, default='')
    origine = models.CharField(max_length=160, blank=True, default='')
    reference = models.CharField(max_length=80, blank=True, default='')
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='validee')
    motif_annulation = models.TextField(blank=True, default='')
    date_annulation = models.DateTimeField(null=True, blank=True)
    annule_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recettes_annulees',
    )
    annule_object_id = models.PositiveIntegerField(null=True, blank=True)
    annule_par = GenericForeignKey('annule_content_type', 'annule_object_id')
    date_creation = models.DateTimeField(auto_now_add=True)
    remboursements = GenericRelation(
        'school_admin.RemboursementOperation',
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='recette',
    )

    class Meta:
        verbose_name = "Recette de l'établissement"
        verbose_name_plural = "Recettes de l'établissement"
        ordering = ['-date_recette', '-id']
        indexes = [
            models.Index(fields=['etablissement', 'date_recette']),
        ]

    def __str__(self):
        return self.libelle or self.get_nature_display()

    def montant_rembourse(self):
        total = Decimal('0')
        for ligne in self.remboursements.all():
            if ligne.statut == 'validee':
                total += ligne.montant or Decimal('0')
        return total

    def net(self):
        if self.statut == 'annulee':
            return Decimal('0')
        return (self.montant or Decimal('0')) - self.montant_rembourse()

    def dans_le_resultat(self):
        """Vrai si le compte de la catégorie est en classe 7. La destination n'entre pas dans ce choix."""
        compte = getattr(self.categorie, 'compte_comptable', None) if self.categorie_id else None
        return bool(compte and compte.classe == '7')


class RemboursementOperation(models.Model):
    """Remboursement d'une recette. L'opération d'origine reste en base."""

    STATUT_CHOICES = [
        ('validee', 'Validée'),
        ('annulee', 'Annulée'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='remboursements_operations',
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    operation = GenericForeignKey('content_type', 'object_id')
    date_remboursement = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        related_name='remboursements_operations',
    )
    motif = models.CharField(max_length=200)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='validee')
    motif_annulation = models.TextField(blank=True, default='')
    date_annulation = models.DateTimeField(null=True, blank=True)
    annule_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remboursements_operations_annules',
    )
    annule_object_id = models.PositiveIntegerField(null=True, blank=True)
    annule_par = GenericForeignKey('annule_content_type', 'annule_object_id')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Remboursement d'opération"
        verbose_name_plural = "Remboursements d'opérations"
        ordering = ['date_remboursement', 'id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['etablissement', 'date_remboursement']),
        ]

    def __str__(self):
        return f"{self.montant} — {self.date_remboursement}"


class PretEtablissement(models.Model):
    """Argent emprunté. La réception augmente la trésorerie et la dette, pas le résultat."""

    STATUT_CHOICES = [
        ('en_cours', 'En cours'),
        ('solde', 'Soldé'),
        ('annulee', 'Annulé'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='prets',
    )
    annee_scolaire = models.ForeignKey(
        'school_admin.AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prets',
    )
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        related_name='prets',
    )
    reference = models.CharField(max_length=80)
    date_reception = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    taux = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    duree_mois = models.PositiveIntegerField(null=True, blank=True)
    objet = models.CharField(max_length=200)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='en_cours')
    motif_annulation = models.TextField(blank=True, default='')
    date_annulation = models.DateTimeField(null=True, blank=True)
    annule_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prets_annules',
    )
    annule_object_id = models.PositiveIntegerField(null=True, blank=True)
    annule_par = GenericForeignKey('annule_content_type', 'annule_object_id')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Prêt"
        verbose_name_plural = "Prêts"
        ordering = ['-date_reception', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['etablissement', 'reference'],
                name='uniq_pret_reference_etablissement',
            ),
        ]

    def __str__(self):
        return self.reference

    def capital_rembourse(self):
        total = Decimal('0')
        for ligne in self.remboursements.all():
            if ligne.statut == 'validee':
                total += ligne.capital or Decimal('0')
        return total

    def capital_restant(self):
        if self.statut == 'annulee':
            return Decimal('0')
        reste = (self.montant or Decimal('0')) - self.capital_rembourse()
        return reste if reste > 0 else Decimal('0')


class EcheancePret(models.Model):
    """Prévision. Elle ne passe aucune écriture."""

    pret = models.ForeignKey(
        PretEtablissement,
        on_delete=models.CASCADE,
        related_name='echeances',
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='echeances_prets',
    )
    numero = models.PositiveIntegerField()
    date_echeance = models.DateField()
    capital_prevu = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    interets_prevus = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    frais_prevus = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Échéance de prêt"
        verbose_name_plural = "Échéances de prêt"
        ordering = ['numero', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['pret', 'numero'],
                name='uniq_echeance_pret_numero',
            ),
        ]

    def __str__(self):
        return f"{self.pret.reference} — {self.numero}"

    @property
    def total_prevu(self):
        return (self.capital_prevu or Decimal('0')) + (self.interets_prevus or Decimal('0')) + (self.frais_prevus or Decimal('0'))


class RemboursementPret(models.Model):
    """Versement réel. Le capital diminue la dette. Intérêts et frais sont des charges."""

    STATUT_CHOICES = [
        ('validee', 'Validé'),
        ('annulee', 'Annulé'),
    ]

    pret = models.ForeignKey(
        PretEtablissement,
        on_delete=models.PROTECT,
        related_name='remboursements',
    )
    echeance = models.ForeignKey(
        EcheancePret,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remboursements',
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='remboursements_prets',
    )
    date_remboursement = models.DateField()
    capital = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    interets = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    frais = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        related_name='remboursements_prets',
    )
    motif = models.CharField(max_length=200)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='validee')
    motif_annulation = models.TextField(blank=True, default='')
    date_annulation = models.DateTimeField(null=True, blank=True)
    annule_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remboursements_prets_annules',
    )
    annule_object_id = models.PositiveIntegerField(null=True, blank=True)
    annule_par = GenericForeignKey('annule_content_type', 'annule_object_id')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Remboursement de prêt"
        verbose_name_plural = "Remboursements de prêt"
        ordering = ['date_remboursement', 'id']

    def __str__(self):
        return f"{self.total} — {self.date_remboursement}"

    @property
    def total(self):
        return (self.capital or Decimal('0')) + (self.interets or Decimal('0')) + (self.frais or Decimal('0'))


class JournalAuditFinancier(models.Model):
    """Trace qui a fait quoi. L'acteur peut être un directeur, pas seulement un CompteUser."""

    ACTION_CHOICES = [
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('validation', 'Validation'),
        ('annulation', 'Annulation'),
        ('remboursement', 'Remboursement'),
        ('rapprochement', 'Rapprochement'),
        ('cloture', 'Clôture'),
        ('correction', 'Correction'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='audits_financiers',
    )
    date = models.DateTimeField(auto_now_add=True)
    acteur_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audits_financiers_acteur',
    )
    acteur_object_id = models.PositiveIntegerField(null=True, blank=True)
    acteur = GenericForeignKey('acteur_content_type', 'acteur_object_id')
    cible_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name='audits_financiers_cible',
    )
    cible_object_id = models.PositiveIntegerField()
    cible = GenericForeignKey('cible_content_type', 'cible_object_id')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    anciennes_valeurs = models.JSONField(default=dict, blank=True)
    nouvelles_valeurs = models.JSONField(default=dict, blank=True)
    motif = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = "Audit financier"
        verbose_name_plural = "Audits financiers"
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['etablissement', 'date']),
            models.Index(fields=['cible_content_type', 'cible_object_id']),
        ]


class PieceFinanciere(models.Model):
    """Justificatif. Même stockage fichier que le reste du projet."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='pieces_financieres',
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    operation = GenericForeignKey('content_type', 'object_id')
    fichier = models.FileField(upload_to='finances/justificatifs/%Y/%m/')
    nom = models.CharField(max_length=180)
    depose_le = models.DateTimeField(auto_now_add=True)
    deposant_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pieces_financieres_deposees',
    )
    deposant_object_id = models.PositiveIntegerField(null=True, blank=True)
    deposant = GenericForeignKey('deposant_content_type', 'deposant_object_id')

    class Meta:
        verbose_name = "Pièce financière"
        verbose_name_plural = "Pièces financières"
        ordering = ['-depose_le']


class ReleveBancaire(models.Model):
    """Relevé d'un compte banque ou mobile money. Le pointage se fait sur les lignes."""

    STATUT_CHOICES = [
        ('en_cours', 'En cours'),
        ('cloture', 'Clôturé'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='releves_bancaires',
    )
    compte_tresorerie = models.ForeignKey(
        CompteTresorerie,
        on_delete=models.PROTECT,
        related_name='releves_bancaires',
    )
    reference = models.CharField(max_length=80)
    date_debut = models.DateField()
    date_fin = models.DateField()
    solde_ouverture = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    solde_cloture = models.DecimalField(max_digits=14, decimal_places=2)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='en_cours')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Relevé bancaire"
        verbose_name_plural = "Relevés bancaires"
        ordering = ['-date_fin', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['etablissement', 'compte_tresorerie', 'reference'],
                name='uniq_releve_bancaire_reference',
            ),
        ]
        indexes = [
            models.Index(fields=['etablissement', 'date_fin']),
        ]

    def __str__(self):
        return f"{self.reference} — {self.compte_tresorerie}"


class LigneReleve(models.Model):
    """Ligne d'un relevé. Pointée, elle ne se modifie plus. Le booléen MouvementTresorerie.pointe en est le miroir."""

    releve = models.ForeignKey(
        ReleveBancaire,
        on_delete=models.CASCADE,
        related_name='lignes',
    )
    date_operation = models.DateField()
    libelle = models.CharField(max_length=200)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reference = models.CharField(max_length=80, blank=True, default='')
    pointe = models.BooleanField(default=False)
    date_pointage = models.DateTimeField(null=True, blank=True)
    ecriture = models.ForeignKey(
        'school_admin.EcritureComptable',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='lignes_releve',
    )
    mouvement = models.ForeignKey(
        'school_admin.MouvementTresorerie',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lignes_releve',
    )

    class Meta:
        verbose_name = "Ligne de relevé"
        verbose_name_plural = "Lignes de relevé"
        ordering = ['date_operation', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['ecriture'],
                condition=models.Q(ecriture__isnull=False, pointe=True),
                name='uniq_ligne_releve_ecriture_pointee',
            ),
        ]

    def __str__(self):
        return f"{self.date_operation} — {self.libelle}"

    @property
    def montant(self):
        return (self.credit or Decimal('0')) - (self.debit or Decimal('0'))
