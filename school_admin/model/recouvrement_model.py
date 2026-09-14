"""
Modèles Vague 1 recouvrement : relances, reçus séquentiels, moratoires.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from .annee_scolaire_model import AnneeScolaire
from .comptabilite_eleve_model import ComptabiliteEleve
from .eleve_model import Eleve
from .etablissement_model import Etablissement


class CompteurRecuPaiement(models.Model):
    """Compteur séquentiel de reçus par établissement et année scolaire."""

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='compteurs_recus_paiement',
        verbose_name="Établissement",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='compteurs_recus_paiement',
        verbose_name="Année scolaire",
    )
    dernier_numero = models.PositiveIntegerField(
        default=0,
        verbose_name="Dernier numéro attribué",
    )

    class Meta:
        verbose_name = "Compteur de reçus de paiement"
        verbose_name_plural = "Compteurs de reçus de paiement"
        unique_together = ['etablissement', 'annee_scolaire']

    def __str__(self):
        return f"Reçus {self.etablissement.nom} {self.annee_scolaire.libelle} → {self.dernier_numero}"


class RelanceImpaye(models.Model):
    """Trace d'une relance SMS / WhatsApp pour un impayé."""

    CANAL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('in_app', 'Notification in-app'),
    ]
    STATUT_CHOICES = [
        ('envoye', 'Envoyé'),
        ('partiel', 'Partiellement envoyé'),
        ('echec', 'Échec'),
        ('ignore', 'Ignoré'),
    ]
    DECLENCHE_CHOICES = [
        ('automatique', 'Automatique'),
        ('manuel', 'Manuel (1 clic)'),
    ]

    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='relances_impayes',
        verbose_name="Établissement",
    )
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='relances_impayes',
        verbose_name="Élève",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='relances_impayes',
        verbose_name="Année scolaire",
    )
    telephone = models.CharField(max_length=30, blank=True, verbose_name="Téléphone destinataire")
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES, default='whatsapp')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='envoye')
    declenche_par = models.CharField(
        max_length=20,
        choices=DECLENCHE_CHOICES,
        default='manuel',
    )
    message = models.TextField(verbose_name="Message envoyé")
    montant_du = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    date_echeance = models.DateField(null=True, blank=True)
    erreur = models.TextField(blank=True)
    date_envoi = models.DateTimeField(default=timezone.now)
    enregistre_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='relances_impayes_envoyees',
    )

    class Meta:
        verbose_name = "Relance impayé"
        verbose_name_plural = "Relances impayés"
        ordering = ['-date_envoi']
        indexes = [
            models.Index(fields=['etablissement', 'date_envoi']),
            models.Index(fields=['eleve', 'annee_scolaire', 'date_envoi']),
        ]

    def __str__(self):
        return f"Relance {self.eleve} {self.date_envoi:%Y-%m-%d} ({self.canal})"


class Moratoire(models.Model):
    """Moratoire simple : nouvelle grille d'échéances, rupture si une échéance reste impayée."""

    STATUT_CHOICES = [
        ('actif', 'Actif'),
        ('solde', 'Soldé'),
        ('rompu', 'Rompu'),
        ('annule', 'Annulé'),
    ]

    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='moratoires',
        verbose_name="Élève",
    )
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='moratoires',
        verbose_name="Établissement",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name='moratoires',
        verbose_name="Année scolaire",
    )
    comptabilite_eleve = models.ForeignKey(
        ComptabiliteEleve,
        on_delete=models.CASCADE,
        related_name='moratoires',
        verbose_name="Comptabilité élève",
    )
    motif = models.TextField(verbose_name="Motif")
    montant_total = models.DecimalField(max_digits=12, decimal_places=2)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_rupture = models.DateTimeField(null=True, blank=True)
    motif_rupture = models.CharField(max_length=255, blank=True)
    cree_par = models.ForeignKey(
        'school_admin.CompteUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moratoires_crees',
    )

    class Meta:
        verbose_name = "Moratoire"
        verbose_name_plural = "Moratoires"
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['etablissement', 'statut']),
            models.Index(fields=['eleve', 'annee_scolaire', 'statut']),
        ]

    def __str__(self):
        return f"Moratoire {self.eleve} ({self.get_statut_display()})"

    def montant_paye(self):
        total = Decimal('0.00')
        for echeance in self.echeances.all():
            total += echeance.montant_paye or Decimal('0.00')
        return total

    def reste_a_payer(self):
        reste = self.montant_total - self.montant_paye()
        return reste if reste > Decimal('0.00') else Decimal('0.00')


class EcheanceMoratoire(models.Model):
    """Une ligne de la nouvelle grille d'échéances d'un moratoire."""

    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('paye', 'Payé'),
        ('en_retard', 'En retard'),
        ('impaye', 'Impayé'),
    ]

    moratoire = models.ForeignKey(
        Moratoire,
        on_delete=models.CASCADE,
        related_name='echeances',
        verbose_name="Moratoire",
    )
    numero = models.PositiveIntegerField(verbose_name="N° d'échéance")
    date_echeance = models.DateField(verbose_name="Date d'échéance")
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    montant_paye = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    date_paiement = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Échéance de moratoire"
        verbose_name_plural = "Échéances de moratoire"
        unique_together = ['moratoire', 'numero']
        ordering = ['numero']

    def __str__(self):
        return f"Échéance {self.numero} — {self.moratoire}"

    def get_reste_a_payer(self):
        reste = self.montant - (self.montant_paye or Decimal('0.00'))
        return reste if reste > Decimal('0.00') else Decimal('0.00')

    def est_totalement_paye(self):
        return self.montant_paye >= self.montant

    def ajouter_paiement(self, montant):
        actuel = Decimal(str(self.montant_paye or 0))
        ajout = Decimal(str(montant))
        nouveau = actuel + ajout
        if nouveau > self.montant:
            nouveau = self.montant
        self.montant_paye = nouveau
        if self.est_totalement_paye():
            self.statut = 'paye'
            if not self.date_paiement:
                self.date_paiement = timezone.now()
        else:
            self.statut = 'en_attente'
        self.save(update_fields=['montant_paye', 'statut', 'date_paiement'])
