# school_admin/model/evaluation_primaire_model.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from .professeur_model import Professeur
from .classe_model import Classe
from .periode_model import PeriodeScolaire
from .matiere_model import Matiere


class EvaluationPrimaire(models.Model):
    """
    Modèle pour gérer les évaluations créées par les professeurs du primaire.
    Chaque évaluation est liée à une matière spécifique.
    """
    
    titre = models.CharField(
        max_length=200,
        verbose_name="Titre de l'évaluation"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description"
    )
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='evaluations_primaire',
        verbose_name="Matière",
        help_text="Matière concernée par cette évaluation"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='evaluations_primaire',
        verbose_name="Classe"
    )
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='evaluations_primaire',
        verbose_name="Professeur"
    )
    date_evaluation = models.DateField(
        verbose_name="Date de l'évaluation"
    )
    bareme = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(0)],
        verbose_name="Barème (points maximum)"
    )
    periode_scolaire = models.ForeignKey(
        PeriodeScolaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluations_primaire',
        verbose_name="Période scolaire"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    class Meta:
        verbose_name = "Évaluation Primaire"
        verbose_name_plural = "Évaluations Primaire"
        ordering = ['-date_evaluation']
    
    def __str__(self):
        return f"{self.matiere.nom} - {self.titre} - {self.classe.nom} ({self.date_evaluation})"
    
    def clean(self):
        """
        Validation personnalisée
        """
        # Vérifier que le professeur enseigne bien cette matière dans cette classe
        from .affectation_professeur_primaire_model import AffectationProfesseurPrimaire
        
        try:
            affectation = AffectationProfesseurPrimaire.objects.get(
                professeur=self.professeur,
                classe=self.classe,
                actif=True
            )
            
            if self.matiere not in affectation.matieres.all():
                raise ValidationError({
                    'matiere': f"Le professeur {self.professeur.nom_complet} n'enseigne pas {self.matiere.nom} dans la classe {self.classe.nom}."
                })
        except AffectationProfesseurPrimaire.DoesNotExist:
            raise ValidationError({
                'professeur': f"Le professeur {self.professeur.nom_complet} n'est pas affecté à la classe {self.classe.nom}."
            })
        
        # Vérifier que la classe est bien de niveau primaire
        # Accepter soit le niveau "Primaire" soit les codes spécifiques (CI, CP, CE1, CE2, CM1, CM2)
        niveau_primaire = ['Primaire', 'CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2']
        if self.classe.niveau not in niveau_primaire and not self.classe.nom.startswith(('CI', 'CP', 'CE1', 'CE2', 'CM1', 'CM2')):
            raise ValidationError({
                'classe': "Ce type d'évaluation est réservé aux classes du primaire."
            })
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def est_passe(self):
        """Vérifie si l'évaluation est passée"""
        from datetime import date
        return self.date_evaluation < date.today()
    
    @property
    def est_a_venir(self):
        """Vérifie si l'évaluation est à venir"""
        from datetime import date
        return self.date_evaluation > date.today()
    
    @property
    def nombre_notes_saisies(self):
        """Retourne le nombre de notes saisies pour cette évaluation"""
        return self.notes_primaire.filter(absent=False).count()
    
    @property
    def nombre_eleves(self):
        """Retourne le nombre total d'élèves de la classe"""
        return self.classe.nombre_eleves
    
    @property
    def pourcentage_notes_saisies(self):
        """Retourne le pourcentage de notes saisies"""
        if self.nombre_eleves > 0:
            return round((self.nombre_notes_saisies / self.nombre_eleves) * 100, 1)
        return 0

