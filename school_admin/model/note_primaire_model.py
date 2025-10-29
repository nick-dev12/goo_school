# school_admin/model/note_primaire_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class NotePrimaire(models.Model):
    """
    Modèle pour gérer les notes des élèves aux évaluations primaires.
    """
    from .eleve_model import Eleve
    from .evaluation_primaire_model import EvaluationPrimaire
    
    eleve = models.ForeignKey(
        'Eleve',
        on_delete=models.CASCADE,
        related_name='notes_primaire',
        verbose_name="Élève"
    )
    evaluation_primaire = models.ForeignKey(
        'EvaluationPrimaire',
        on_delete=models.CASCADE,
        related_name='notes_primaire',
        verbose_name="Évaluation"
    )
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True,
        verbose_name="Note obtenue"
    )
    appreciation = models.TextField(
        blank=True,
        null=True,
        verbose_name="Appréciation"
    )
    absent = models.BooleanField(
        default=False,
        verbose_name="Absent"
    )
    retenue = models.BooleanField(
        default=False,
        verbose_name="Note retenue pour la moyenne"
    )
    date_saisie = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de saisie"
    )
    
    class Meta:
        verbose_name = "Note Primaire"
        verbose_name_plural = "Notes Primaire"
        unique_together = ['eleve', 'evaluation_primaire']
        ordering = ['-evaluation_primaire__date_evaluation']
    
    def __str__(self):
        if self.absent:
            return f"{self.eleve.nom_complet} - {self.evaluation_primaire.titre} : Absent"
        elif self.note is not None:
            return f"{self.eleve.nom_complet} - {self.evaluation_primaire.titre} : {self.note}/{self.evaluation_primaire.bareme}"
        else:
            return f"{self.eleve.nom_complet} - {self.evaluation_primaire.titre} : Non noté"
    
    def clean(self):
        """
        Validation personnalisée
        """
        # Vérifier que l'élève appartient à la classe de l'évaluation
        if self.eleve.classe != self.evaluation_primaire.classe:
            raise ValidationError({
                'eleve': "L'élève n'appartient pas à la classe de cette évaluation."
            })
        
        # Vérifier que la note ne dépasse pas le barème
        if self.note is not None and not self.absent:
            if self.note > self.evaluation_primaire.bareme:
                raise ValidationError({
                    'note': f"La note ne peut pas dépasser le barème ({self.evaluation_primaire.bareme})."
                })
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def note_sur_20(self):
        """Convertit la note sur 20"""
        if self.absent:
            return None
        if self.note is not None and self.evaluation_primaire.bareme > 0:
            return round((self.note / self.evaluation_primaire.bareme) * 20, 2)
        return None
    
    @property
    def pourcentage(self):
        """Calcul du pourcentage"""
        if self.absent:
            return None
        if self.note is not None and self.evaluation_primaire.bareme > 0:
            return round((self.note / self.evaluation_primaire.bareme) * 100, 1)
        return None
    
    @property
    def appreciation_auto(self):
        """Génère une appréciation automatique selon la note"""
        if self.absent:
            return "Absent"
        
        note_sur_20 = self.note_sur_20
        if note_sur_20 is None:
            return "Non évalué"
        elif note_sur_20 >= 16:
            return "Excellent"
        elif note_sur_20 >= 14:
            return "Très bien"
        elif note_sur_20 >= 12:
            return "Bien"
        elif note_sur_20 >= 10:
            return "Assez bien"
        elif note_sur_20 >= 8:
            return "Passable"
        else:
            return "Insuffisant"


class MoyenneMatierePrimaire(models.Model):
    """
    Modèle pour stocker les moyennes calculées par matière pour chaque élève.
    """
    from .eleve_model import Eleve
    from .classe_model import Classe
    from .matiere_model import Matiere
    from .periode_model import PeriodeScolaire
    
    eleve = models.ForeignKey(
        'Eleve',
        on_delete=models.CASCADE,
        related_name='moyennes_matieres_primaire',
        verbose_name="Élève"
    )
    classe = models.ForeignKey(
        'Classe',
        on_delete=models.CASCADE,
        related_name='moyennes_matieres_primaire',
        verbose_name="Classe"
    )
    matiere = models.ForeignKey(
        'Matiere',
        on_delete=models.CASCADE,
        related_name='moyennes_primaire',
        verbose_name="Matière"
    )
    periode_scolaire = models.ForeignKey(
        'PeriodeScolaire',
        on_delete=models.CASCADE,
        related_name='moyennes_matieres_primaire',
        verbose_name="Période scolaire"
    )
    moyenne = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Moyenne sur 20"
    )
    nombre_notes = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de notes"
    )
    appreciation = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Appréciation"
    )
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de calcul"
    )
    soumis = models.BooleanField(
        default=False,
        verbose_name="Soumis",
        help_text="Indique si cette moyenne a été soumise et verrouillée"
    )
    date_soumission = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de soumission"
    )
    
    class Meta:
        verbose_name = "Moyenne Matière Primaire"
        verbose_name_plural = "Moyennes Matières Primaire"
        unique_together = ['eleve', 'matiere', 'periode_scolaire']
        ordering = ['eleve', 'matiere']
    
    def __str__(self):
        if self.moyenne is not None:
            return f"{self.eleve.nom_complet} - {self.matiere.nom} : {self.moyenne}/20"
        else:
            return f"{self.eleve.nom_complet} - {self.matiere.nom} : Non calculée"
    
    def clean(self):
        """
        Validation personnalisée
        """
        # Vérifier que l'élève appartient à la classe
        if self.eleve.classe != self.classe:
            raise ValidationError({
                'eleve': "L'élève n'appartient pas à cette classe."
            })
    
    def save(self, *args, **kwargs):
        self.clean()
        
        # Générer l'appréciation automatique si la moyenne est définie
        if self.moyenne is not None:
            self.appreciation = self.get_appreciation_auto()
        
        super().save(*args, **kwargs)
    
    def get_appreciation_auto(self):
        """Génère une appréciation automatique selon la moyenne"""
        if self.moyenne is None:
            return "Non évalué"
        elif self.moyenne >= 16:
            return "Excellent"
        elif self.moyenne >= 14:
            return "Très bien"
        elif self.moyenne >= 12:
            return "Bien"
        elif self.moyenne >= 10:
            return "Assez bien"
        elif self.moyenne >= 8:
            return "Passable"
        else:
            return "Insuffisant"
    
    @classmethod
    def calculer_et_enregistrer(cls, eleve, matiere, periode_scolaire):
        """
        Calcule et enregistre la moyenne d'un élève pour une matière et une période.
        """
        from .evaluation_primaire_model import EvaluationPrimaire
        
        # Récupérer toutes les notes de l'élève pour cette matière et cette période
        evaluations = EvaluationPrimaire.objects.filter(
            classe=eleve.classe,
            matiere=matiere,
            periode_scolaire=periode_scolaire,
            actif=True
        )
        
        notes = NotePrimaire.objects.filter(
            eleve=eleve,
            evaluation_primaire__in=evaluations,
            absent=False
        ).exclude(note__isnull=True)
        
        if notes.exists():
            # Calculer la moyenne sur 20
            total = sum(note.note_sur_20 for note in notes if note.note_sur_20 is not None)
            nombre_notes = notes.count()
            moyenne = round(Decimal(total) / Decimal(nombre_notes), 2) if nombre_notes > 0 else None
        else:
            moyenne = None
            nombre_notes = 0
        
        # Créer ou mettre à jour la moyenne
        moyenne_obj, created = cls.objects.update_or_create(
            eleve=eleve,
            matiere=matiere,
            periode_scolaire=periode_scolaire,
            defaults={
                'classe': eleve.classe,
                'moyenne': moyenne,
                'nombre_notes': nombre_notes
            }
        )
        
        return moyenne_obj

