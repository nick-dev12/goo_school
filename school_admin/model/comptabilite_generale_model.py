"""Comptabilité générale : plan SYSCOHADA, journaux, exercices, écritures."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .annee_scolaire_model import AnneeScolaire
from .etablissement_model import Etablissement


class CompteComptable(models.Model):
    """Compte du plan SYSCOHADA (éducation) pour un établissement."""

    CLASSE_CHOICES = [
        ('1', 'Classe 1 — Financement permanent'),
        ('2', 'Classe 2 — Actif immobilisé'),
        ('3', 'Classe 3 — Stocks'),
        ('4', 'Classe 4 — Tiers'),
        ('5', 'Classe 5 — Trésorerie'),
        ('6', 'Classe 6 — Charges'),
        ('7', 'Classe 7 — Produits'),
        ('8', 'Classe 8 — Autres charges et produits'),
    ]
    NATURE_CHOICES = [
        ('actif', 'Actif'),
        ('passif', 'Passif'),
        ('charge', 'Charge'),
        ('produit', 'Produit'),
        ('hors', 'Hors bilan'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='comptes_comptables',
        verbose_name="Établissement",
    )
    numero = models.CharField(max_length=12, verbose_name="Numéro")
    libelle = models.CharField(max_length=160, verbose_name="Libellé")
    classe = models.CharField(max_length=1, choices=CLASSE_CHOICES, verbose_name="Classe")
    nature = models.CharField(max_length=10, choices=NATURE_CHOICES, default='actif')
    est_auxiliaire = models.BooleanField(default=False, verbose_name="Auxiliaire")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Compte comptable"
        verbose_name_plural = "Comptes comptables"
        unique_together = ['etablissement', 'numero']
        ordering = ['numero']

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class JournalComptable(models.Model):
    """Journal (Caisse, Banque, Achats, Ventes/Scolarité, OD)."""

    CODE_CHOICES = [
        ('CAI', 'Caisse'),
        ('BAN', 'Banque'),
        ('ACH', 'Achats'),
        ('SCO', 'Ventes / Scolarité'),
        ('OD', 'Opérations diverses'),
        ('PAI', 'Paie'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='journaux_comptables',
    )
    code = models.CharField(max_length=8)
    libelle = models.CharField(max_length=80)
    compte_contrepartie = models.ForeignKey(
        CompteComptable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='journaux_contrepartie',
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Journal comptable"
        verbose_name_plural = "Journaux comptables"
        unique_together = ['etablissement', 'code']
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.libelle}"


class ExerciceComptable(models.Model):
    """Exercice annuel, lié optionnellement à l'année scolaire."""

    STATUT_CHOICES = [
        ('ouvert', 'Ouvert'),
        ('cloture', 'Clôturé'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='exercices_comptables',
    )
    libelle = models.CharField(max_length=20, help_text="Ex. 2026")
    date_debut = models.DateField()
    date_fin = models.DateField()
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exercices_comptables',
    )
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='ouvert')
    date_cloture = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Exercice comptable"
        verbose_name_plural = "Exercices comptables"
        unique_together = ['etablissement', 'libelle']
        ordering = ['-date_debut']

    def __str__(self):
        return self.libelle

    def est_ouvert(self):
        return self.statut == 'ouvert'


class PeriodeComptable(models.Model):
    """Mois / trimestre / semestre verrouillable."""

    TYPE_CHOICES = [
        ('mois', 'Mois'),
        ('trimestre', 'Trimestre'),
        ('semestre', 'Semestre'),
    ]

    exercice = models.ForeignKey(
        ExerciceComptable,
        on_delete=models.CASCADE,
        related_name='periodes',
    )
    type_periode = models.CharField(max_length=12, choices=TYPE_CHOICES, default='mois')
    libelle = models.CharField(max_length=40)
    date_debut = models.DateField()
    date_fin = models.DateField()
    verrouillee = models.BooleanField(default=False)
    date_verrouillage = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Période comptable"
        verbose_name_plural = "Périodes comptables"
        ordering = ['date_debut']

    def __str__(self):
        return f"{self.exercice.libelle} — {self.libelle}"


class EcritureComptable(models.Model):
    """Pièce (en-tête) d'une écriture équilibrée."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='ecritures_comptables',
    )
    exercice = models.ForeignKey(
        ExerciceComptable,
        on_delete=models.PROTECT,
        related_name='ecritures',
    )
    journal = models.ForeignKey(
        JournalComptable,
        on_delete=models.PROTECT,
        related_name='ecritures',
    )
    numero = models.CharField(max_length=24)
    date_ecriture = models.DateField()
    libelle = models.CharField(max_length=200)
    reference = models.CharField(max_length=80, blank=True, default='')
    source = models.CharField(
        max_length=40,
        blank=True,
        default='',
        help_text="paiement_eleve, depense, paie, od, virement…",
    )
    source_id = models.PositiveIntegerField(null=True, blank=True)
    validee = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    creee_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ecritures_creees',
    )

    class Meta:
        verbose_name = "Écriture comptable"
        verbose_name_plural = "Écritures comptables"
        unique_together = ['etablissement', 'journal', 'numero']
        ordering = ['-date_ecriture', '-id']
        indexes = [
            models.Index(fields=['etablissement', 'date_ecriture']),
            models.Index(fields=['source', 'source_id']),
        ]

    def __str__(self):
        return f"{self.journal.code}-{self.numero} {self.libelle}"

    def total_debit(self):
        return self.lignes.aggregate(s=Sum('debit'))['s'] or Decimal('0.00')

    def total_credit(self):
        return self.lignes.aggregate(s=Sum('credit'))['s'] or Decimal('0.00')

    def est_equilibree(self):
        return self.total_debit() == self.total_credit()


class LigneEcriture(models.Model):
    ecriture = models.ForeignKey(
        EcritureComptable,
        on_delete=models.CASCADE,
        related_name='lignes',
    )
    compte = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        related_name='lignes',
    )
    libelle = models.CharField(max_length=200, blank=True, default='')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    auxiliaire = models.CharField(max_length=80, blank=True, default='')

    class Meta:
        verbose_name = "Ligne d'écriture"
        verbose_name_plural = "Lignes d'écriture"
        ordering = ['id']

    def clean(self):
        if self.debit and self.credit:
            raise ValidationError("Une ligne ne peut pas être à la fois débit et crédit.")
        if not self.debit and not self.credit:
            raise ValidationError("Indiquez un débit ou un crédit.")


class FournisseurEtablissement(models.Model):
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='fournisseurs',
    )
    nom = models.CharField(max_length=160)
    telephone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ['nom']

    def __str__(self):
        return self.nom


class FactureFournisseur(models.Model):
    STATUT_CHOICES = [
        ('a_payer', 'À payer'),
        ('partiel', 'Partiellement payée'),
        ('payee', 'Payée'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='factures_fournisseurs',
    )
    fournisseur = models.ForeignKey(
        FournisseurEtablissement,
        on_delete=models.CASCADE,
        related_name='factures',
    )
    numero = models.CharField(max_length=40)
    libelle = models.CharField(max_length=200)
    date_facture = models.DateField()
    date_echeance = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    montant_paye = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='a_payer')

    class Meta:
        verbose_name = "Facture fournisseur"
        verbose_name_plural = "Factures fournisseurs"
        ordering = ['date_echeance']

    def reste_a_payer(self):
        return (self.montant or Decimal('0')) - (self.montant_paye or Decimal('0'))

    def __str__(self):
        return f"{self.numero} — {self.fournisseur.nom}"


class Immobilisation(models.Model):
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='immobilisations',
    )
    libelle = models.CharField(max_length=160)
    categorie = models.CharField(
        max_length=40,
        choices=[
            ('batiment', 'Bâtiment'),
            ('bus', 'Flotte de bus'),
            ('informatique', 'Parc informatique'),
            ('mobilier', 'Mobilier de classe'),
            ('autre', 'Autre'),
        ],
        default='autre',
    )
    date_acquisition = models.DateField()
    valeur_origine = models.DecimalField(max_digits=14, decimal_places=2)
    duree_annees = models.PositiveIntegerField(default=5)
    compte_immobilisation = models.ForeignKey(
        CompteComptable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='immobilisations',
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Immobilisation"
        verbose_name_plural = "Immobilisations"
        ordering = ['libelle']

    def dotation_annuelle(self):
        if not self.duree_annees:
            return Decimal('0.00')
        return (self.valeur_origine / Decimal(self.duree_annees)).quantize(Decimal('0.01'))

    def __str__(self):
        return self.libelle


class MouvementTresorerie(models.Model):
    """Virement interne (caisse → banque) ou rapprochement."""

    TYPE_CHOICES = [
        ('virement_interne', 'Virement interne'),
        ('rapprochement', 'Rapprochement bancaire'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='mouvements_tresorerie',
    )
    type_mouvement = models.CharField(max_length=24, choices=TYPE_CHOICES)
    date_mouvement = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    libelle = models.CharField(max_length=200)
    pointe = models.BooleanField(default=False)
    date_pointage = models.DateTimeField(null=True, blank=True)
    ecriture = models.ForeignKey(
        EcritureComptable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mouvements_tresorerie',
    )

    class Meta:
        verbose_name = "Mouvement de trésorerie"
        verbose_name_plural = "Mouvements de trésorerie"
        ordering = ['-date_mouvement']

    def __str__(self):
        return f"{self.get_type_mouvement_display()} {self.montant}"
