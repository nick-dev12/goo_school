"""
Pointage des enseignants : une séance par cours de l'emploi du temps et par jour.

Une séance n'est payée que si elle est validée : soit automatiquement (QR de la
borne scanné à l'heure, appel fait, cahier de texte rempli, aucune anomalie),
soit par un membre de la direction (censeur, surveillant, directeur).
"""
import secrets

from django.db import models
from django.utils import timezone

from .annee_scolaire_model import AnneeScolaire
from .etablissement_model import Etablissement


def _nouveau_secret():
    return secrets.token_urlsafe(24)


class BornePointage(models.Model):
    """Écran (tablette, téléphone, PC) qui affiche un QR renouvelé toutes les 30 secondes."""

    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='bornes_pointage')
    libelle = models.CharField(max_length=80, verbose_name="Nom de la borne")
    emplacement = models.CharField(max_length=120, blank=True, default='', verbose_name="Emplacement")
    secret = models.CharField(max_length=64, default=_nouveau_secret, editable=False)
    actif = models.BooleanField(default=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Borne de pointage"
        verbose_name_plural = "Bornes de pointage"
        ordering = ['libelle']

    def __str__(self):
        return self.libelle

    def regenerer_secret(self):
        self.secret = _nouveau_secret()
        self.save(update_fields=['secret'])

    @property
    def en_ligne(self):
        return bool(self.derniere_activite and (timezone.now() - self.derniere_activite).total_seconds() < 120)


class SeanceCours(models.Model):
    STATUT_CHOICES = [
        ('prevue', 'Prévue'),
        ('en_cours', 'En cours'),
        ('validee', 'Validée'),
        ('a_verifier', 'À vérifier'),
        ('absente', 'Non faite'),
        ('remplacee', 'Remplacée'),
        ('contestee', 'Contestée'),
        ('annulee', 'Annulée'),
    ]
    STATUTS_PAYES = ('validee', 'remplacee')

    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='seances_cours')
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='seances_cours')
    professeur = models.ForeignKey('school_admin.Professeur', on_delete=models.CASCADE, related_name='seances')
    classe = models.ForeignKey('school_admin.Classe', on_delete=models.CASCADE, related_name='seances')
    matiere = models.ForeignKey('school_admin.Matiere', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='seances')
    creneau = models.ForeignKey('school_admin.CreneauEmploiDuTemps', on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='seances')
    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    statut = models.CharField(max_length=12, choices=STATUT_CHOICES, default='prevue')

    debut_reel = models.DateTimeField(null=True, blank=True)
    fin_reelle = models.DateTimeField(null=True, blank=True)
    preuve_qr = models.BooleanField(default=False)
    borne = models.ForeignKey(BornePointage, on_delete=models.SET_NULL, null=True, blank=True, related_name='seances')
    motif_sans_qr = models.CharField(max_length=200, blank=True, default='')
    appel_fait = models.BooleanField(default=False)
    nb_eleves_appel = models.PositiveIntegerField(default=0)
    cahier_texte = models.TextField(blank=True, default='')
    anomalies = models.JSONField(default=list, blank=True)
    confiance = models.PositiveSmallIntegerField(default=0)

    remplacant = models.ForeignKey('school_admin.Professeur', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='seances_remplacees')
    absence_justifiee = models.BooleanField(default=False)
    motif_contestation = models.TextField(blank=True, default='')
    valide_par = models.CharField(max_length=120, blank=True, default='')
    valide_le = models.DateTimeField(null=True, blank=True)
    commentaire_validation = models.CharField(max_length=255, blank=True, default='')
    validation_auto = models.BooleanField(default=False)
    paie = models.ForeignKey('school_admin.PaieProfesseurPeriode', on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='seances')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Séance de cours"
        verbose_name_plural = "Séances de cours"
        ordering = ['date', 'heure_debut']
        constraints = [
            models.UniqueConstraint(fields=['creneau', 'date'], name='uniq_seance_creneau_date'),
        ]
        indexes = [
            models.Index(fields=['etablissement', 'date']),
            models.Index(fields=['professeur', 'date']),
            models.Index(fields=['etablissement', 'statut']),
        ]

    def __str__(self):
        return f"{self.date} {self.heure_debut:%H:%M} {self.classe} — {self.professeur}"

    @property
    def duree_minutes(self):
        debut = self.heure_debut.hour * 60 + self.heure_debut.minute
        fin = self.heure_fin.hour * 60 + self.heure_fin.minute
        return max(fin - debut, 0)

    @property
    def payee_a(self):
        """Enseignant qui touche la séance (le remplaçant le cas échéant)."""
        return self.remplacant if self.statut == 'remplacee' and self.remplacant_id else self.professeur
