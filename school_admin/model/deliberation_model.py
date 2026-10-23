"""
Délibérations du supérieur (LMD) : jury, décisions par étudiant, UE capitalisées.

Une délibération porte sur une classe et, soit un semestre (période), soit l'année entière
(bilan annuel : passage, passage conditionnel avec dettes, redoublement). Une fois clôturée,
les notes de la période sont verrouillées et les UE acquises sont capitalisées pour la suite
du cursus.
"""
from django.db import models

from .classe_model import Classe
from .eleve_model import Eleve
from .etablissement_model import Etablissement


class Deliberation(models.Model):
    SESSION_NORMALE = 'normale'
    SESSION_RATTRAPAGE = 'rattrapage'
    SESSION_CHOICES = [(SESSION_NORMALE, 'Session normale'), (SESSION_RATTRAPAGE, 'Session de rattrapage')]
    STATUT_BROUILLON = 'brouillon'
    STATUT_CLOTUREE = 'cloturee'
    STATUT_CHOICES = [(STATUT_BROUILLON, 'En cours'), (STATUT_CLOTUREE, 'Clôturée')]

    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='deliberations')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='deliberations')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.CASCADE, related_name='deliberations')
    periode = models.ForeignKey(
        'PeriodeScolaire', on_delete=models.CASCADE, null=True, blank=True, related_name='deliberations',
        help_text="Semestre délibéré. Vide = délibération annuelle (passage en année supérieure).",
    )
    session = models.CharField(max_length=12, choices=SESSION_CHOICES, default=SESSION_NORMALE)
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default=STATUT_BROUILLON)
    date_deliberation = models.DateField(null=True, blank=True, verbose_name="Date de la délibération")
    president = models.CharField(max_length=150, blank=True, verbose_name="Président du jury")
    membres = models.TextField(blank=True, verbose_name="Membres du jury", help_text="Un membre par ligne.")
    observations = models.TextField(blank=True, verbose_name="Observations du jury")
    cloturee_le = models.DateTimeField(null=True, blank=True)
    cloturee_par = models.CharField(max_length=150, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Délibération'
        verbose_name_plural = 'Délibérations'
        ordering = ['-date_creation']
        constraints = [
            models.UniqueConstraint(fields=['classe', 'annee_scolaire', 'periode', 'session'],
                                    name='deliberation_unique_classe_periode_session'),
        ]

    def __str__(self):
        return f"Délibération {self.classe} — {self.libelle_portee}"

    @property
    def est_annuelle(self):
        return self.periode_id is None

    @property
    def est_cloturee(self):
        return self.statut == self.STATUT_CLOTUREE

    @property
    def libelle_portee(self):
        portee = self.periode.nom_periode if self.periode_id else 'Bilan annuel'
        if self.session == self.SESSION_RATTRAPAGE:
            portee += ' — rattrapage'
        return portee

    @property
    def liste_membres(self):
        return [m.strip() for m in (self.membres or '').splitlines() if m.strip()]


class DecisionJury(models.Model):
    ADMIS = 'admis'
    ADMIS_COMPENSATION = 'admis_compensation'
    ADMIS_CONDITIONNEL = 'admis_conditionnel'
    AJOURNE = 'ajourne'
    INCOMPLET = 'incomplet'
    REDOUBLE = 'redouble'
    DECISION_CHOICES = [
        (ADMIS, 'Admis'),
        (ADMIS_COMPENSATION, 'Admis par compensation'),
        (ADMIS_CONDITIONNEL, 'Admis avec dettes (passage conditionnel)'),
        (AJOURNE, 'Ajourné'),
        (INCOMPLET, 'Incomplet'),
        (REDOUBLE, 'Redouble'),
    ]

    deliberation = models.ForeignKey(Deliberation, on_delete=models.CASCADE, related_name='decisions')
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='decisions_jury')
    moyenne = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    points_jury = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    moyenne_jury = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    credits_acquis = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    credits_total = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    decision = models.CharField(max_length=24, choices=DECISION_CHOICES, default=AJOURNE)
    mention = models.CharField(max_length=30, blank=True)
    motif_jury = models.CharField(max_length=255, blank=True, verbose_name="Motif (points de jury, observation)")
    detail_ues = models.JSONField(default=list, blank=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Décision du jury'
        verbose_name_plural = 'Décisions du jury'
        constraints = [
            models.UniqueConstraint(fields=['deliberation', 'eleve'], name='decision_jury_unique'),
        ]

    def __str__(self):
        return f"{self.eleve} — {self.get_decision_display()}"

    @property
    def est_admis(self):
        return self.decision in (self.ADMIS, self.ADMIS_COMPENSATION, self.ADMIS_CONDITIONNEL)

    @property
    def dettes(self):
        return [ue for ue in (self.detail_ues or []) if not ue.get('acquise')]


class UECapitalisee(models.Model):
    """UE définitivement acquise par un étudiant : conservée s'il redouble ou passe avec des dettes."""
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='ues_capitalisees')
    module = models.ForeignKey('Module', on_delete=models.CASCADE, related_name='capitalisations')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.SET_NULL, null=True, blank=True)
    periode = models.ForeignKey('PeriodeScolaire', on_delete=models.SET_NULL, null=True, blank=True)
    moyenne = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    credits = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    mode = models.CharField(max_length=20, default='acquise')
    deliberation = models.ForeignKey(Deliberation, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='capitalisations')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'UE capitalisée'
        verbose_name_plural = 'UE capitalisées'
        constraints = [models.UniqueConstraint(fields=['eleve', 'module'], name='ue_capitalisee_unique')]

    def __str__(self):
        return f"{self.eleve} — {self.module} ({self.credits} cr.)"
