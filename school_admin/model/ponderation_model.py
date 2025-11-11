"""Modèle pour la configuration des pondérations de calcul de moyenne."""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Ponderation(models.Model):
    """Paramètres de pondération des moyennes pour un établissement et une année donnée."""

    TYPE_CALCUL_CHOICES = [
        ('classique_50_50', 'Classique (50/50)'),
        ('exigeante_40_60', 'École exigeante (40/60)'),
        ('continu_60_40', 'Travail continu (60/40)'),
        ('speciale_30_70', 'Évaluation spéciale (30/70)'),
    ]

    METHOD_CONFIG = {
        'classique_50_50': {'classe': 50, 'examen': 50},
        'exigeante_40_60': {'classe': 40, 'examen': 60},
        'continu_60_40': {'classe': 60, 'examen': 40},
        'speciale_30_70': {'classe': 30, 'examen': 70},
    }

    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='ponderations',
        verbose_name="Établissement",
    )

    annee_scolaire = models.CharField(
        max_length=20,
        verbose_name="Année scolaire",
        help_text="Format attendu : 2024-2025",
    )

    type_calcul = models.CharField(
        max_length=20,
        choices=TYPE_CALCUL_CHOICES,
        default='classique_50_50',
        verbose_name="Type de calcul",
    )

    poids_classe = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Pourcentage du contrôle continu",
    )

    poids_examen = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Pourcentage des examens",
    )

    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    class Meta:
        verbose_name = "Pondération"
        verbose_name_plural = "Pondérations"
        unique_together = ['etablissement', 'annee_scolaire', 'type_calcul']
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.etablissement.nom} - {self.annee_scolaire} ({self.get_type_calcul_display()})"

    @property
    def somme_poids(self):
        """Retourne la somme des poids configurés."""
        return (self.poids_classe or 0) + (self.poids_examen or 0)

    @classmethod
    def get_or_create_for_year(cls, etablissement, annee_scolaire):
        """Récupère la pondération active pour l'année donnée ou crée une configuration par défaut."""
        defaults = cls._build_defaults('classique_50_50')
        defaults['actif'] = True
        pond, _ = cls.objects.get_or_create(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            defaults=defaults,
        )
        return pond

    def appliquer_methode(self, methode):
        """Applique une méthode de calcul prédéfinie aux pourcentages."""
        config = self.METHOD_CONFIG.get(methode)
        if not config:
            raise ValueError("Méthode de calcul inconnue")
        self.type_calcul = methode
        self.poids_classe = config['classe']
        self.poids_examen = config['examen']
        return self

    @classmethod
    def _build_defaults(cls, methode):
        config = cls.METHOD_CONFIG.get(methode, {'classe': 50, 'examen': 50})
        return {
            'type_calcul': methode,
            'poids_classe': config['classe'],
            'poids_examen': config['examen'],
        }

    @staticmethod
    def default_school_year():
        """Calcule l'année scolaire courante (ex: 2024-2025)."""
        today = timezone.now().date()
        if today.month >= 8:
            start_year = today.year
        else:
            start_year = today.year - 1
        return f"{start_year}-{start_year + 1}"

