"""Caisse école, paie du mois et absences / remplacements enseignants."""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from .annee_scolaire_model import AnneeScolaire
from .etablissement_model import Etablissement
from .professeur_model import Professeur


class DepenseEtablissement(models.Model):
    """Sortie de caisse de l'école (pas les dépenses de la société ARIA)."""

    MOTIF_CHOICES = [
        ('salaire', 'Salaire / vacataire'),
        ('loyer', 'Loyer'),
        ('electricite', 'Électricité / eau'),
        ('fournitures', 'Fournitures'),
        ('carburant', 'Carburant / transport'),
        ('autre', 'Autre'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='depenses_caisse',
        verbose_name="Établissement",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='depenses_caisse',
        verbose_name="Année scolaire",
    )
    date_depense = models.DateField(verbose_name="Date")
    motif = models.CharField(
        max_length=20,
        choices=MOTIF_CHOICES,
        default='autre',
        verbose_name="Motif",
    )
    libelle = models.CharField(
        max_length=160,
        blank=True,
        default='',
        verbose_name="Précision",
        help_text="Optionnel. Ex. : Orange Money septembre, loyer bâtiment A.",
    )
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant",
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Enregistré le")
    enregistre_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='depenses_caisse_enregistrees',
        verbose_name="Enregistré par",
    )

    class Meta:
        verbose_name = "Dépense d'établissement"
        verbose_name_plural = "Dépenses d'établissement"
        ordering = ['-date_depense', '-id']

    def __str__(self):
        return f"{self.get_motif_display()} {self.montant} ({self.date_depense})"

    def libelle_affiche(self):
        precision = (self.libelle or '').strip()
        if precision:
            return precision
        return self.get_motif_display()


class PaieProfesseurPeriode(models.Model):
    """Marque une période de volume horaire comme payée."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='paies_professeurs',
        verbose_name="Établissement",
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='paies_periodes',
        verbose_name="Professeur",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paies_professeurs',
        verbose_name="Année scolaire",
    )
    date_debut = models.DateField(verbose_name="Début de période")
    date_fin = models.DateField(verbose_name="Fin de période")
    heures = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Heures")
    montant_brut = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Brut")
    retenue_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Charges %",
    )
    montant_net = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Net versé")
    date_paiement = models.DateTimeField(default=timezone.now, verbose_name="Payé le")
    enregistre_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paies_professeurs_enregistrees',
        verbose_name="Enregistré par",
    )

    class Meta:
        verbose_name = "Paie professeur"
        verbose_name_plural = "Paies professeurs"
        ordering = ['-date_paiement']
        constraints = [
            models.UniqueConstraint(
                fields=['professeur', 'date_debut', 'date_fin'],
                name='uniq_paie_professeur_periode',
            ),
        ]

    def __str__(self):
        return f"{self.professeur_id} {self.date_debut}–{self.date_fin} {self.montant_net}"


class AbsenceEnseignant(models.Model):
    """Jour d'absence d'un professeur, avec remplaçant optionnel."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='absences_enseignants',
        verbose_name="Établissement",
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='absences_enseignant',
        verbose_name="Professeur absent",
    )
    remplacant = models.ForeignKey(
        Professeur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remplacements_effectues',
        verbose_name="A fait le cours",
    )
    date = models.DateField(verbose_name="Date")
    minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="Minutes",
        help_text="Durée des créneaux EDT de ce jour.",
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Absence enseignant"
        verbose_name_plural = "Absences enseignants"
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['professeur', 'date'],
                name='uniq_absence_enseignant_jour',
            ),
        ]

    def __str__(self):
        return f"{self.professeur_id} absent {self.date}"
