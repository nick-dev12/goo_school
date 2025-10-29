"""
Modèle pour la gestion des notes d'examens
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from .eleve_model import Eleve
from .creneau_examen_model import CreneauExamen
from .session_examen_model import SessionExamen
from .matiere_model import Matiere
from .professeur_model import Professeur
from .classe_model import Classe


class NoteExamen(models.Model):
    """
    Modèle pour enregistrer les notes des élèves aux examens
    """
    
    eleve = models.ForeignKey(
        Eleve,
        on_delete=models.CASCADE,
        related_name='notes_examens',
        verbose_name="Élève"
    )
    
    session_examen = models.ForeignKey(
        SessionExamen,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name="Session d'examen"
    )
    
    creneau_examen = models.ForeignKey(
        CreneauExamen,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name="Créneau d'examen",
        null=True,
        blank=True
    )
    
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='notes_examens',
        verbose_name="Matière"
    )
    
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='notes_examens_saisies',
        verbose_name="Professeur"
    )
    
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='notes_examens',
        verbose_name="Classe"
    )
    
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Note sur 20",
        null=True,
        blank=True
    )
    
    bareme = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(0)],
        verbose_name="Barème"
    )
    
    note_sur_20 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Note ramenée sur 20"
    )
    
    absent = models.BooleanField(
        default=False,
        verbose_name="Élève absent"
    )
    
    retenue = models.BooleanField(
        default=True,
        verbose_name="Note retenue pour la moyenne"
    )
    
    commentaire = models.TextField(
        blank=True,
        null=True,
        verbose_name="Commentaire/Appréciation"
    )
    
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de saisie"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification"
    )
    
    soumis = models.BooleanField(
        default=False,
        verbose_name="Note soumise (verrouillée)"
    )
    
    date_soumission = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de soumission"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    class Meta:
        verbose_name = "Note d'examen"
        verbose_name_plural = "Notes d'examens"
        unique_together = ['eleve', 'session_examen', 'matiere']
        ordering = ['-date_saisie']
    
    def __str__(self):
        return f"{self.eleve.nom_complet} - {self.matiere.nom} - {self.session_examen.nom_examen}: {self.note_sur_20}/20"
    
    def clean(self):
        """Validation du modèle"""
        super().clean()
        
        # Vérifier que l'élève appartient à la classe
        if self.eleve.classe != self.classe:
            raise ValidationError({
                'eleve': "L'élève n'appartient pas à cette classe."
            })
        
        # Vérifier que la matière fait partie de la session d'examen
        if self.session_examen and self.matiere not in self.session_examen.matieres.all():
            raise ValidationError({
                'matiere': "La matière ne fait pas partie de cette session d'examen."
            })
        
        # Si note présente, calculer note_sur_20
        if self.note is not None and not self.absent:
            if self.bareme <= 0:
                raise ValidationError({
                    'bareme': "Le barème doit être supérieur à 0."
                })
    
    def save(self, *args, **kwargs):
        """Calcul automatique de la note sur 20"""
        if self.note is not None and not self.absent:
            if self.bareme > 0:
                self.note_sur_20 = (self.note / self.bareme) * 20
            else:
                self.note_sur_20 = 0
        else:
            self.note_sur_20 = None
        
        super().save(*args, **kwargs)
    
    @property
    def note_format(self):
        """Retourne la note formatée"""
        if self.absent:
            return "Absent"
        elif self.note_sur_20 is not None:
            return f"{self.note_sur_20:.2f}/20"
        else:
            return "Non noté"
    
    @property
    def appreciation_auto(self):
        """Génère une appréciation automatique selon la note"""
        if self.absent:
            return "Absent"
        elif self.note_sur_20 is None:
            return "Non évalué"
        elif self.note_sur_20 >= 16:
            return "Excellent"
        elif self.note_sur_20 >= 14:
            return "Très bien"
        elif self.note_sur_20 >= 12:
            return "Bien"
        elif self.note_sur_20 >= 10:
            return "Assez bien"
        else:
            return "Insuffisant"
    
    @classmethod
    def get_notes_session(cls, session_examen, matiere=None, classe=None):
        """Récupère les notes d'une session d'examen"""
        queryset = cls.objects.filter(session_examen=session_examen, actif=True)
        
        if matiere:
            queryset = queryset.filter(matiere=matiere)
        
        if classe:
            queryset = queryset.filter(classe=classe)
        
        return queryset.select_related('eleve', 'matiere', 'classe', 'professeur')
    
    @classmethod
    def calculer_moyenne_classe(cls, session_examen, matiere, classe):
        """Calcule la moyenne de la classe pour un examen"""
        notes = cls.objects.filter(
            session_examen=session_examen,
            matiere=matiere,
            classe=classe,
            absent=False,
            note_sur_20__isnull=False,
            actif=True
        )
        
        if notes.exists():
            total = sum(n.note_sur_20 for n in notes)
            return round(total / notes.count(), 2)
        
        return None

