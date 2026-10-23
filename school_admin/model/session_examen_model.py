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
    # Nature de la session : décide de son rôle dans le calcul des moyennes.
    TYPE_COMPOSITION = 'composition'
    TYPE_EXAMEN = 'examen'
    TYPE_BLANC = 'examen_blanc'
    TYPE_RATTRAPAGE = 'rattrapage'
    TYPE_CHOICES = [
        (TYPE_COMPOSITION, 'Composition / devoir de synthèse'),
        (TYPE_EXAMEN, 'Examen de fin de période (session normale)'),
        (TYPE_BLANC, 'Examen blanc (BFEM, Bac, CFEE…)'),
        (TYPE_RATTRAPAGE, 'Rattrapage (2e session)'),
    ]
    type_session = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default=TYPE_COMPOSITION,
        verbose_name="Type de session",
    )
    compte_bulletin = models.BooleanField(
        default=True, verbose_name="Compte dans le bulletin",
        help_text="Décocher pour un examen blanc d'entraînement : les notes restent visibles mais n'entrent pas dans les moyennes.",
    )
    
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
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions_examens_annee_scolaire',
        verbose_name="Année scolaire"
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
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({
                'date_fin': "La date de fin ne peut pas précéder la date de début."
            })
        
        # Vérifier que la session est dans la période scolaire (un rattrapage peut se tenir après sa fin)
        if self.periode and self.date_debut and self.date_fin and self.type_session != self.TYPE_RATTRAPAGE:
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
        # Un examen blanc ne compte pas au bulletin par défaut (à la création).
        if not self.pk and self.type_session == self.TYPE_BLANC and self.compte_bulletin is True and \
                not getattr(self, '_compte_bulletin_explicite', False):
            self.compte_bulletin = False
        
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
    def est_rattrapage(self):
        return self.type_session == self.TYPE_RATTRAPAGE

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




class ReglesExamen(models.Model):
    """Règles de calcul des examens propres à l'établissement (absences, rattrapage, LMD)."""
    RATTRAPAGE_MEILLEURE = 'meilleure'
    RATTRAPAGE_REMPLACE = 'remplace'
    ABSENCE_ZERO = 'zero'
    ABSENCE_NEUTRE = 'neutre'

    etablissement = models.OneToOneField(Etablissement, on_delete=models.CASCADE, related_name='regles_examen')
    absence_injustifiee = models.CharField(
        max_length=10, default=ABSENCE_ZERO,
        choices=[(ABSENCE_ZERO, 'Compte 0/20'), (ABSENCE_NEUTRE, 'Neutralisée (comme une absence justifiée)')],
        verbose_name="Absence non justifiée à un examen",
    )
    regle_rattrapage = models.CharField(
        max_length=10, default=RATTRAPAGE_MEILLEURE,
        choices=[(RATTRAPAGE_MEILLEURE, 'La meilleure des deux notes'),
                 (RATTRAPAGE_REMPLACE, 'La note de rattrapage remplace la 1re session')],
        verbose_name="Note retenue après rattrapage",
    )
    seuil_validation = models.DecimalField(max_digits=4, decimal_places=2, default=10,
                                           verbose_name="Moyenne de validation")
    note_eliminatoire = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="Note éliminatoire (supérieur)",
        help_text="Une matière sous cette note empêche la compensation (vide = pas de note éliminatoire).",
    )
    compensation_semestrielle = models.BooleanField(
        default=True, verbose_name="Compensation entre UE dans le semestre (LMD)",
    )
    # Progression annuelle (supérieur, LMD)
    compensation_annuelle = models.BooleanField(
        default=False, verbose_name="Compensation annuelle entre les deux semestres",
        help_text="Si la moyenne de l'année atteint le seuil, toutes les UE de l'année sont acquises.",
    )
    pourcentage_passage_conditionnel = models.PositiveSmallIntegerField(
        default=75, verbose_name="Passage conditionnel à partir de (% des crédits de l'année)",
        help_text="Ex. 75 % = 45 crédits sur 60 : l'étudiant passe avec des dettes (UE à repasser). 100 = désactivé.",
    )
    poids_cc = models.JSONField(
        default=dict, blank=True, verbose_name="Pondération du contrôle continu par type (%)",
        help_text="Ex. {\"td\": 30, \"tp\": 20, \"devoir\": 30, \"partiel\": 20}. Vide = types à égalité.",
    )
    points_jury_max = models.DecimalField(
        max_digits=4, decimal_places=2, default=1, verbose_name="Points de jury maximum",
        help_text="Bonus que le jury peut accorder à la moyenne d'un étudiant lors de la délibération.",
    )
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Règles d'examen"
        verbose_name_plural = "Règles d'examen"

    def __str__(self):
        return f"Règles d'examen — {self.etablissement}"

    @classmethod
    def pour(cls, etablissement):
        regles, _ = cls.objects.get_or_create(etablissement=etablissement)
        return regles
