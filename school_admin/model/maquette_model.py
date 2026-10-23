"""
Maquette pédagogique du supérieur : parcours, groupes de TD / TP et inscription pédagogique
(parcours suivi, UE optionnelles choisies) d'un étudiant pour une année.
"""
from django.db import models

from .classe_model import Classe
from .eleve_model import Eleve


class Parcours(models.Model):
    """Spécialisation à l'intérieur d'une classe (ex. L3 Droit : Droit privé / Droit public)."""
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='parcours')
    nom = models.CharField(max_length=120, verbose_name="Nom du parcours")
    code = models.CharField(max_length=20, blank=True, verbose_name="Code")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Parcours'
        verbose_name_plural = 'Parcours'
        ordering = ['nom']
        constraints = [models.UniqueConstraint(fields=['classe', 'nom'], name='parcours_unique_par_classe')]

    def __str__(self):
        return f"{self.classe.nom} — {self.nom}"


class GroupeEnseignement(models.Model):
    """Groupe de TD ou de TP d'une classe (sous-ensemble d'étudiants)."""
    TYPE_CHOICES = [('td', 'Travaux dirigés'), ('tp', 'Travaux pratiques')]

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='groupes_enseignement')
    nom = models.CharField(max_length=30, verbose_name="Nom du groupe", help_text="Ex. G1, G2, TP-A.")
    type_groupe = models.CharField(max_length=4, choices=TYPE_CHOICES, default='td')
    capacite = models.PositiveSmallIntegerField(default=40, verbose_name="Capacité")
    etudiants = models.ManyToManyField(Eleve, blank=True, related_name='groupes_enseignement')

    class Meta:
        verbose_name = 'Groupe de TD / TP'
        verbose_name_plural = 'Groupes de TD / TP'
        ordering = ['type_groupe', 'nom']
        constraints = [models.UniqueConstraint(fields=['classe', 'type_groupe', 'nom'], name='groupe_unique_par_classe')]

    def __str__(self):
        return f"{self.get_type_groupe_display()} {self.nom} — {self.classe.nom}"

    @property
    def libelle(self):
        return f"{self.type_groupe.upper()} {self.nom}"


class InscriptionPedagogique(models.Model):
    """Ce que l'étudiant suit réellement : son parcours et ses UE optionnelles."""
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='inscriptions_pedagogiques')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='inscriptions_pedagogiques')
    annee_scolaire = models.ForeignKey('AnneeScolaire', on_delete=models.CASCADE,
                                       related_name='inscriptions_pedagogiques')
    parcours = models.ForeignKey(Parcours, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='inscriptions')
    ues_optionnelles = models.ManyToManyField('ModuleClasse', blank=True, related_name='inscriptions_optionnelles')
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inscription pédagogique'
        verbose_name_plural = 'Inscriptions pédagogiques'
        constraints = [models.UniqueConstraint(fields=['eleve', 'annee_scolaire'],
                                               name='inscription_pedagogique_unique')]

    def __str__(self):
        return f"{self.eleve} — {self.classe} ({self.annee_scolaire})"
