"""Règles de service des enseignants du supérieur (équivalent TD, heures complémentaires)."""
from decimal import Decimal

from django.db import models

from .etablissement_model import Etablissement

SERVICE_PAR_GRADE_DEFAUT = {
    'professeur_titulaire': 192, 'maitre_conferences': 192, 'maitre_assistant': 192,
    'assistant': 192, 'charge_cours': 192, 'vacataire': 0,
}


def _service_defaut():
    return dict(SERVICE_PAR_GRADE_DEFAUT)


class ReglesService(models.Model):
    etablissement = models.OneToOneField(Etablissement, on_delete=models.CASCADE, related_name='regles_service')
    coef_cm = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.5'),
                                  verbose_name="1 h de CM vaut (h éq. TD)")
    coef_td = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1'),
                                  verbose_name="1 h de TD vaut (h éq. TD)")
    coef_tp = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.67'),
                                  verbose_name="1 h de TP vaut (h éq. TD)")
    taux_heure_complementaire = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="Taux de l'heure complémentaire (éq. TD)",
        help_text="Montant payé par heure éq. TD au-delà du service (et pour les vacataires sans tarif propre).",
    )
    service_par_grade = models.JSONField(default=_service_defaut, verbose_name="Service annuel par grade (h éq. TD)")
    semaines_annee = models.PositiveSmallIntegerField(
        default=28, verbose_name="Semaines d'enseignement (créneaux « toute l'année »)",
    )
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Règles de service des enseignants'
        verbose_name_plural = 'Règles de service des enseignants'

    def __str__(self):
        return f"Règles de service — {self.etablissement}"

    @classmethod
    def pour(cls, etablissement):
        r, _ = cls.objects.get_or_create(etablissement=etablissement)
        return r

    def service_du(self, professeur):
        if professeur.service_statutaire:
            return Decimal(professeur.service_statutaire)
        if professeur.type_contrat == 'vacataire' or professeur.grade_universitaire == 'vacataire':
            return Decimal(0)
        grades = {**SERVICE_PAR_GRADE_DEFAUT, **(self.service_par_grade or {})}
        return Decimal(str(grades.get(professeur.grade_universitaire or 'charge_cours', 192)))
