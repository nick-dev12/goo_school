# school_admin/model/affectation_model.py

from django.db import models
from django.core.exceptions import ValidationError
from .professeur_model import Professeur
from .classe_model import Classe
from .matiere_model import Matiere


class AffectationProfesseur(models.Model):
    """
    Modèle pour gérer les affectations des professeurs aux classes avec statut
    """
    
    STATUT_CHOICES = [
        ('principal', 'Professeur Principal'),
        ('classique', 'Professeur Classique'),
    ]
    
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='affectations',
        verbose_name="Professeur"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='affectations',
        verbose_name="Classe"
    )
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='affectations',
        verbose_name="Matière enseignée",
        null=True,
        blank=True,
        help_text="Matière que le professeur enseigne dans cette classe"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='affectations_professeurs',
        verbose_name="Année scolaire"
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='classique',
        verbose_name="Statut"
    )
    date_affectation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'affectation"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    class Meta:
        verbose_name = "Affectation Professeur"
        verbose_name_plural = "Affectations Professeurs"
        unique_together = ['professeur', 'classe', 'matiere']
        ordering = ['-date_affectation']
    
    def __str__(self):
        return f"{self.professeur.nom_complet} - {self.classe.nom} ({self.get_statut_display()})"
    
    def clean(self):
        """
        Validation personnalisée pour s'assurer qu'il n'y a qu'un seul professeur principal par classe
        et qu'il n'y a pas deux enseignants de la même matière dans la même classe
        """
        # Si une matière est spécifiée, vérifier que le professeur peut l'enseigner
        if self.matiere:
            # Vérifier que la matière est soit la matière principale soit une matière secondaire du professeur
            matieres_enseignables = [self.professeur.matiere_principale.id] + list(
                self.professeur.matieres_secondaires.values_list('id', flat=True)
            )
            
            if self.matiere.id not in matieres_enseignables:
                raise ValidationError(
                    f"Le professeur {self.professeur.nom_complet} ne peut pas enseigner {self.matiere.nom}. "
                    f"Cette matière n'est ni sa matière principale ni une de ses matières secondaires."
                )
        
        # Définir la matière par défaut si elle n'est pas spécifiée
        if not self.matiere:
            self.matiere = self.professeur.matiere_principale
        
        # Vérifier s'il y a déjà un professeur de la même matière pour cette classe
        existing_same_matiere = AffectationProfesseur.objects.filter(
            classe=self.classe,
            matiere=self.matiere,
            actif=True
        ).exclude(pk=self.pk)
        
        if existing_same_matiere.exists():
            existing_prof = existing_same_matiere.first()
            raise ValidationError(
                f"Il y a déjà un professeur de {self.matiere.nom} "
                f"({existing_prof.professeur.nom_complet}) affecté à la classe {self.classe.nom}. "
                f"Une classe ne peut avoir qu'un seul enseignant par matière."
            )
        
        # Vérifier s'il y a déjà un professeur principal pour cette classe
        if self.statut == 'principal':
            existing_principal = AffectationProfesseur.objects.filter(
                classe=self.classe,
                statut='principal',
                actif=True
            ).exclude(pk=self.pk)
            
            if existing_principal.exists():
                raise ValidationError(
                    f"Il y a déjà un professeur principal pour la classe {self.classe.nom}. "
                    f"Veuillez d'abord retirer le statut principal de l'autre professeur."
                )
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def statut_display(self):
        """Retourne l'affichage du statut"""
        return dict(self.STATUT_CHOICES).get(self.statut, self.statut)
    
    @property
    def is_principal(self):
        """Retourne True si c'est un professeur principal"""
        return self.statut == 'principal'
