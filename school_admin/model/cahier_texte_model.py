"""Cahier de texte : ce qui a été fait à chaque cours et le travail donné, pour tous les types d'établissement."""
from django.db import models

from .annee_scolaire_model import AnneeScolaire
from .etablissement_model import Etablissement


class CahierTexte(models.Model):
    # Brouillon : modifiable par l'enseignant, invisible des élèves et de la direction.
    # Validé : envoyé à la direction et visible des élèves ; verrouillé, sauf si la direction
    # accepte une demande de modification (l'entrée redevient alors un brouillon).
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('valide', 'Validé'),
    ]
    DEMANDE_CHOICES = [
        ('', 'Aucune'),
        ('en_attente', 'En attente'),
        ('acceptee', 'Acceptée'),
        ('refusee', 'Refusée'),
    ]

    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='cahiers_texte')
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='cahiers_texte')
    professeur = models.ForeignKey('school_admin.Professeur', on_delete=models.CASCADE, related_name='cahiers_texte')
    classe = models.ForeignKey('school_admin.Classe', on_delete=models.CASCADE, related_name='cahiers_texte')
    matiere = models.ForeignKey('school_admin.Matiere', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='cahiers_texte')
    seance = models.OneToOneField('school_admin.SeanceCours', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='cahier')
    date = models.DateField()
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)

    titre = models.CharField(max_length=200, verbose_name="Leçon / chapitre")
    objectifs = models.TextField(blank=True, default='', verbose_name="Objectifs")
    contenu = models.TextField(verbose_name="Déroulement de la séance")
    travail_a_faire = models.TextField(blank=True, default='', verbose_name="Travail à faire")
    date_travail = models.DateField(null=True, blank=True, verbose_name="Pour le")
    observations = models.TextField(blank=True, default='', verbose_name="Observations (privées)")
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='brouillon')
    date_validation = models.DateTimeField(null=True, blank=True)
    demande_statut = models.CharField(max_length=12, choices=DEMANDE_CHOICES, blank=True, default='')
    demande_motif = models.TextField(blank=True, default='')
    demande_le = models.DateTimeField(null=True, blank=True)
    demande_reponse = models.CharField(max_length=255, blank=True, default='')
    demande_traitee_par = models.CharField(max_length=120, blank=True, default='')
    demande_traitee_le = models.DateTimeField(null=True, blank=True)
    redige_par_ia = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Entrée du cahier de texte"
        verbose_name_plural = "Cahier de texte"
        ordering = ['-date', '-heure_debut']
        indexes = [
            models.Index(fields=['classe', 'date']),
            models.Index(fields=['professeur', 'date']),
        ]

    def __str__(self):
        return f"{self.date} {self.classe} — {self.titre}"

    @property
    def est_valide(self):
        return self.statut == 'valide'

    @property
    def modifiable(self):
        return self.statut == 'brouillon'
