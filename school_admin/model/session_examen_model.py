"""
Modèle pour la gestion des sessions d'examens
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .etablissement_model import Etablissement
from .periode_model import PeriodeScolaire
from .classe_model import Classe
from .matiere_model import Matiere
from .professeur_model import Professeur
from .salle_model import Salle


class SessionExamen(models.Model):
    """
    Modèle pour représenter une session d'examen programmée
    """
    
    # Informations de base
    nom_examen = models.CharField(
        max_length=200,
        verbose_name="Nom de l'examen",
        help_text="Ex: Examen de Mathématiques, Devoir surveillé de Français"
    )
    
    # Relations
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='sessions_examens',
        verbose_name="Établissement"
    )
    
    periode = models.ForeignKey(
        PeriodeScolaire,
        on_delete=models.CASCADE,
        related_name='sessions_examens',
        verbose_name="Période scolaire"
    )
    
    # Les classes concernées (relation many-to-many)
    classes = models.ManyToManyField(
        Classe,
        related_name='sessions_examens',
        verbose_name="Classes concernées"
    )
    
    # Matières concernées (relation many-to-many pour la logique sénégalaise)
    matieres = models.ManyToManyField(
        Matiere,
        related_name='sessions_examens',
        verbose_name="Matières de l'examen"
    )
    
    # Période de la session (dates de début et fin)
    date_debut = models.DateField(
        verbose_name="Date de début de la session"
    )
    
    date_fin = models.DateField(
        verbose_name="Date de fin de la session"
    )
    
    # Informations complémentaires
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description",
        help_text="Instructions ou informations supplémentaires"
    )
    
    duree_totale = models.DurationField(
        blank=True,
        null=True,
        verbose_name="Durée totale estimée",
        help_text="Durée totale de la session d'examens"
    )
    
    # Statut
    est_publie = models.BooleanField(
        default=False,
        verbose_name="Publié",
        help_text="L'examen est-il visible par les élèves et parents ?"
    )
    
    est_annule = models.BooleanField(
        default=False,
        verbose_name="Annulé"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    class Meta:
        verbose_name = "Session d'examen"
        verbose_name_plural = "Sessions d'examens"
        ordering = ['-date_creation']
    
    def __str__(self):
        matieres_str = ", ".join([m.nom for m in self.matieres.all()[:3]])
        if self.matieres.count() > 3:
            matieres_str += f" (+{self.matieres.count() - 3} autres)"
        return f"{self.nom_examen} - {matieres_str} ({self.periode.nom_periode})"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que la date de fin est après la date de début
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            raise ValidationError({
                'date_fin': "La date de fin doit être après la date de début."
            })
        
        # Vérifier que la session est dans la période scolaire
        if self.periode and self.date_debut and self.date_fin:
            if self.date_debut < self.periode.date_debut or self.date_fin > self.periode.date_fin:
                raise ValidationError({
                    'date_debut': f"La session doit être comprise entre le {self.periode.date_debut} et le {self.periode.date_fin}."
                })
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour calculer la durée
        """
        # Calculer la durée totale si les dates sont définies
        if self.date_debut and self.date_fin:
            from datetime import timedelta
            self.duree_totale = (self.date_fin - self.date_debut) + timedelta(days=1)
        
        super().save(*args, **kwargs)
    
    @property
    def duree_format(self):
        """
        Retourne la durée formatée en jours et heures
        """
        if self.duree_totale:
            total_seconds = int(self.duree_totale.total_seconds())
            jours = total_seconds // 86400
            heures = (total_seconds % 86400) // 3600
            
            if jours > 0:
                return f"{jours}j {heures}h"
            else:
                return f"{heures}h"
        return "Non définie"
    
    @property
    def est_passe(self):
        """
        Vérifie si la session d'examen est passée
        """
        aujourdhui = timezone.now().date()
        return self.date_fin < aujourdhui
    
    @property
    def est_en_cours(self):
        """
        Vérifie si la session d'examen est en cours
        """
        aujourdhui = timezone.now().date()
        return self.date_debut <= aujourdhui <= self.date_fin
    
    @property
    def est_a_venir(self):
        """
        Vérifie si la session d'examen est à venir
        """
        aujourdhui = timezone.now().date()
        return self.date_debut > aujourdhui
    
    @property
    def statut_examen(self):
        """
        Retourne le statut de l'examen (passé, en cours, à venir, annulé)
        """
        if self.est_annule:
            return 'annule'
        elif self.est_passe:
            return 'passe'
        elif self.est_en_cours:
            return 'en_cours'
        else:
            return 'a_venir'
    
    @property
    def classes_str(self):
        """
        Retourne une chaîne avec les noms des classes
        """
        return ", ".join([classe.nom for classe in self.classes.all()])
    
    @property
    def matieres_liste(self):
        """
        Retourne une chaîne avec les noms des matières
        """
        return ", ".join([matiere.nom for matiere in self.matieres.all()])
    
    @property
    def nombre_matieres(self):
        """
        Retourne le nombre de matières dans la session
        """
        return self.matieres.count()
    
    @property
    def nombre_classes(self):
        """
        Retourne le nombre de classes concernées
        """
        return self.classes.count()
    
    @classmethod
    def get_sessions_periode(cls, periode):
        """
        Récupère toutes les sessions d'une période donnée
        """
        return cls.objects.filter(
            periode=periode,
            actif=True
        ).order_by('date_debut')
    
    @classmethod
    def get_sessions_classe(cls, classe):
        """
        Récupère toutes les sessions d'une classe donnée
        """
        return cls.objects.filter(
            classes=classe,
            actif=True
        ).order_by('date_debut')
    
    @classmethod
    def get_sessions_periode_date(cls, etablissement, date):
        """
        Récupère toutes les sessions actives à une date donnée
        """
        return cls.objects.filter(
            etablissement=etablissement,
            date_debut__lte=date,
            date_fin__gte=date,
            est_annule=False,
            actif=True
        ).order_by('date_debut')

