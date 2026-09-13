# school_admin/model/module_model.py

from decimal import Decimal
from django.db import models
from django.db.models import Sum


class ModuleDepartment(models.Model):
    """
    Association module ↔ spécialité (filière).
    Permet un module mutualisé entre plusieurs filières ou un module dédié à une seule.
    """
    module = models.ForeignKey(
        'school_admin.Module',
        on_delete=models.CASCADE,
        related_name='module_departments',
        verbose_name="Module",
    )
    department = models.ForeignKey(
        'school_admin.Department',
        on_delete=models.CASCADE,
        related_name='module_departments',
        verbose_name="Spécialité",
    )

    class Meta:
        verbose_name = "Module-Spécialité"
        verbose_name_plural = "Modules-Spécialités"
        unique_together = ['module', 'department']

    def __str__(self):
        return f"{self.module.nom} — {self.department.nom}"


class ModuleClasse(models.Model):
    """
    Table de liaison Module-Classe avec crédits spécifiques par classe.
    Un même module peut avoir des crédits différents selon la classe (ex: L1=3, L2=4).
    """
    module = models.ForeignKey(
        'school_admin.Module',
        on_delete=models.CASCADE,
        related_name='module_classes',
        verbose_name="Module"
    )
    classe = models.ForeignKey(
        'school_admin.Classe',
        on_delete=models.CASCADE,
        related_name='module_classe_credits',
        verbose_name="Classe"
    )
    credits = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Crédits pour cette classe"
    )
    numero_ue = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name="Numéro d'unité d'enseignement (UE)",
        help_text="Ex. UE3.1.1 — affiché sur le bulletin pour cette association module / classe.",
    )
    periode = models.ForeignKey(
        'school_admin.PeriodeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='module_classes',
        verbose_name="Période rattachée",
        help_text="Semestre auquel ce module est rattaché pour cette classe.",
    )

    class Meta:
        verbose_name = "Module-Classe (crédits)"
        verbose_name_plural = "Modules-Classes (crédits)"
        unique_together = ['module', 'classe']

    def __str__(self):
        periode_label = self.periode.nom_periode if self.periode_id else "Sans période"
        return f"{self.module.nom} - {self.classe.nom}: {self.credits} crédits ({periode_label})"


class Module(models.Model):
    """
    Module pédagogique pour l'enseignement supérieur (système LMD).
    Un module regroupe une ou plusieurs matières et peut avoir des crédits
    définis directement ou calculés à partir des crédits des matières.
    """
    nom = models.CharField(max_length=255, verbose_name="Nom du module")
    code = models.CharField(max_length=20, verbose_name="Code du module")
    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='modules',
        verbose_name="Établissement"
    )
    department = models.ForeignKey(
        'school_admin.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modules',
        verbose_name="Spécialité principale",
        help_text="Renseignée si le module est propre à une seule spécialité ; vide si mutualisé.",
    )
    departments = models.ManyToManyField(
        'school_admin.Department',
        through='school_admin.ModuleDepartment',
        related_name='modules_lies',
        verbose_name="Spécialités concernées",
        blank=True,
        help_text="Une ou plusieurs spécialités auxquelles ce module est rattaché.",
    )
    niveau_lmd = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Niveau LMD",
        help_text="L1, L2, BTS, DUT, etc."
    )
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    classes = models.ManyToManyField(
        'school_admin.Classe',
        through='school_admin.ModuleClasse',
        related_name='modules',
        verbose_name="Classes concernées",
        blank=True,
        help_text="Classes qui suivent ce module avec crédits spécifiques par classe"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ['etablissement', 'ordre', 'nom']
        unique_together = ['etablissement', 'code']

    def __str__(self):
        return f"{self.nom} ({self.code})"

    @property
    def is_shared(self):
        """True si le module est rattaché à plusieurs spécialités."""
        count = self.module_departments.count()
        if count:
            return count > 1
        return False

    def get_linked_departments(self):
        """Spécialités liées au module (M2M ou FK legacy)."""
        qs = self.module_departments.select_related('department').order_by(
            'department__ordre', 'department__nom'
        )
        if qs.exists():
            return [md.department for md in qs]
        if self.department_id:
            return [self.department]
        return []

    def get_linked_department_ids(self):
        ids = list(self.module_departments.values_list('department_id', flat=True))
        if ids:
            return ids
        if self.department_id:
            return [self.department_id]
        return []

    def get_departments_display(self):
        labels = [d.nom for d in self.get_linked_departments()]
        return ', '.join(labels) if labels else ''

    def sync_primary_department(self):
        """Synchronise la FK legacy department selon les liaisons M2M."""
        dep_ids = list(self.module_departments.values_list('department_id', flat=True))
        if len(dep_ids) == 1:
            self.department_id = dep_ids[0]
        elif len(dep_ids) > 1:
            self.department_id = None
        self.save(update_fields=['department', 'date_modification'])

    def get_credits_for_classe(self, classe):
        """Retourne les crédits du module pour une classe donnée."""
        try:
            mc = self.module_classes.get(classe=classe)
            return mc.credits
        except ModuleClasse.DoesNotExist:
            result = self.matieres.aggregate(total=Sum('credits'))
            return result['total'] or Decimal('0')

    @property
    def total_credits(self):
        """
        Retourne les crédits affichés (premier module_classe ou somme des matières).
        Pour les crédits par classe, utiliser get_credits_for_classe().
        """
        first_mc = self.module_classes.select_related('classe').first()
        if first_mc is not None:
            return first_mc.credits
        result = self.matieres.aggregate(total=Sum('credits'))
        return result['total'] or Decimal('0')
