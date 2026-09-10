# school_admin/model/employe_dossier_model.py

from django.db import models
from django.core.exceptions import ValidationError


SEXE_CHOICES = [
    ('M', 'Masculin'),
    ('F', 'Féminin'),
]

TYPE_CONTRAT_CHOICES = [
    ('cdi', 'CDI'),
    ('cdd', 'CDD'),
    ('vacataire', 'Vacataire'),
    ('stage', 'Stage / Alternance'),
    ('convention', 'Convention'),
    ('prestation', 'Prestation de service'),
    ('autre', 'Autre'),
]


def employe_document_upload_to(instance, filename):
    if instance.professeur_id:
        return f'employes/professeurs/{instance.professeur_id}/{filename}'
    if instance.personnel_administratif_id:
        return f'employes/personnel/{instance.personnel_administratif_id}/{filename}'
    return f'employes/documents/{filename}'


class DocumentEmploye(models.Model):
    """Document rattaché à un professeur ou à un membre du personnel administratif."""

    professeur = models.ForeignKey(
        'school_admin.Professeur',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='documents',
        verbose_name='Professeur',
    )
    personnel_administratif = models.ForeignKey(
        'school_admin.PersonnelAdministratif',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='documents',
        verbose_name='Personnel administratif',
    )
    libelle = models.CharField(max_length=200, blank=True, verbose_name='Libellé du document')
    fichier = models.FileField(upload_to=employe_document_upload_to, verbose_name='Fichier')
    date_ajout = models.DateTimeField(auto_now_add=True, verbose_name="Date d'ajout")

    class Meta:
        verbose_name = 'Document employé'
        verbose_name_plural = 'Documents employés'
        ordering = ['-date_ajout']

    def __str__(self):
        return self.libelle or (self.fichier.name if self.fichier else 'Document')

    def clean(self):
        owners = sum([
            bool(self.professeur_id),
            bool(self.personnel_administratif_id),
        ])
        if owners != 1:
            raise ValidationError('Un document doit être rattaché à un seul employé.')

    @property
    def nom_fichier(self):
        if not self.fichier:
            return ''
        return self.fichier.name.split('/')[-1]


class DossierEmployeComplementaire(models.Model):
    """Informations complémentaires optionnelles du dossier employé (obligations légales)."""

    professeur = models.OneToOneField(
        'school_admin.Professeur',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dossier_complementaire',
        verbose_name='Professeur',
    )
    personnel_administratif = models.OneToOneField(
        'school_admin.PersonnelAdministratif',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dossier_complementaire',
        verbose_name='Personnel administratif',
    )

    date_naissance = models.DateField(null=True, blank=True, verbose_name='Date de naissance')
    lieu_naissance = models.CharField(max_length=150, blank=True, verbose_name='Lieu de naissance')
    nationalite = models.CharField(max_length=100, blank=True, verbose_name='Nationalité')
    adresse = models.TextField(blank=True, verbose_name='Adresse')
    numero_cni = models.CharField(max_length=50, blank=True, verbose_name='N° pièce d\'identité (CNI / passeport)')
    numero_cnss = models.CharField(max_length=50, blank=True, verbose_name='N° CNSS / sécurité sociale')
    type_contrat = models.CharField(
        max_length=20,
        choices=TYPE_CONTRAT_CHOICES,
        blank=True,
        verbose_name='Type de contrat',
    )
    date_fin_contrat = models.DateField(null=True, blank=True, verbose_name='Date de fin de contrat')
    salaire_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Salaire de base (FCFA)',
    )
    banque = models.CharField(max_length=120, blank=True, verbose_name='Banque')
    numero_compte_bancaire = models.CharField(max_length=80, blank=True, verbose_name='N° compte / RIB')
    diplome_plus_eleve = models.CharField(max_length=150, blank=True, verbose_name='Diplôme le plus élevé')
    numero_autorisation = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="N° autorisation d'enseignement / agrément",
    )
    contact_urgence_nom = models.CharField(max_length=120, blank=True, verbose_name="Contact d'urgence — nom")
    contact_urgence_telephone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Contact d'urgence — téléphone",
    )
    contact_urgence_lien = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Contact d'urgence — lien (conjoint, parent…)",
    )
    observations = models.TextField(blank=True, verbose_name='Observations / notes administratives')

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dossier employé complémentaire'
        verbose_name_plural = 'Dossiers employés complémentaires'

    def clean(self):
        owners = sum([
            bool(self.professeur_id),
            bool(self.personnel_administratif_id),
        ])
        if owners != 1:
            raise ValidationError('Un dossier doit être rattaché à un seul employé.')

    def get_type_contrat_display_label(self):
        if not self.type_contrat:
            return '—'
        return dict(TYPE_CONTRAT_CHOICES).get(self.type_contrat, self.type_contrat)
