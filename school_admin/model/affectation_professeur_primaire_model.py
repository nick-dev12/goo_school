# school_admin/model/affectation_professeur_primaire_model.py

from django.db import models
from django.core.exceptions import ValidationError
from .professeur_model import Professeur
from .classe_model import Classe
from .matiere_model import Matiere


class AffectationProfesseurPrimaire(models.Model):
    """
    Modèle pour gérer les affectations polyvalentes des enseignants primaires.
    Un enseignant primaire peut enseigner plusieurs matières dans une même classe.
    """
    
    STATUT_CHOICES = [
        ('principal', 'Professeur Principal'),
        ('polyvalent', 'Professeur Polyvalent'),
    ]
    
    professeur = models.ForeignKey(
        Professeur,
        on_delete=models.CASCADE,
        related_name='affectations_primaire',
        verbose_name="Professeur"
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name='affectations_primaire',
        verbose_name="Classe"
    )
    matieres = models.ManyToManyField(
        Matiere,
        related_name='affectations_primaire',
        verbose_name="Matières enseignées",
        help_text="Toutes les matières que le professeur enseigne dans cette classe"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='affectations_professeurs_primaire',
        verbose_name="Année scolaire"
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='polyvalent',
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
        verbose_name = "Affectation Professeur Primaire"
        verbose_name_plural = "Affectations Professeurs Primaire"
        # Contrainte unique incluant l'année scolaire pour permettre plusieurs affectations pour différentes années
        unique_together = ['professeur', 'classe', 'annee_scolaire']
        ordering = ['-date_affectation']
        indexes = [
            models.Index(fields=['professeur', 'classe', 'annee_scolaire']),
            models.Index(fields=['annee_scolaire', 'actif']),
        ]
    
    def __str__(self):
        matieres_list = ", ".join([m.nom for m in self.matieres.all()[:3]])
        if self.matieres.count() > 3:
            matieres_list += "..."
        return f"{self.professeur.nom_complet} - {self.classe.nom} ({matieres_list})"
    
    def clean(self):
        """
        Validation personnalisée pour s'assurer de la cohérence des affectations
        """
        # Vérifier que l'établissement est de type primaire (garde-fou principal)
        etablissement = getattr(self.professeur, "etablissement", None)
        if not etablissement or getattr(etablissement, "type_etablissement", None) != 'primary':
            raise ValidationError(
                "Ce type d'affectation est réservé aux établissements de type primaire."
            )
        
        # Vérifier que la classe est bien de niveau primaire
        # On harmonise la casse pour éviter les faux positifs (ex: "primaire" en base)
        niveau_classe = (self.classe.niveau or "").strip().lower()
        if niveau_classe != 'primaire':
            raise ValidationError(
                "Ce type d'affectation est réservé aux classes du primaire."
            )
        
        # Vérifier qu'il n'y a pas déjà une affectation active pour ce professeur dans cette classe et cette année scolaire
        if self.pk is None:  # Nouvelle affectation
            existing = AffectationProfesseurPrimaire.objects.filter(
                professeur=self.professeur,
                classe=self.classe,
                actif=True
            )
            # Filtrer par année scolaire si elle est définie
            if self.annee_scolaire:
                existing = existing.filter(annee_scolaire=self.annee_scolaire)
            else:
                # Si pas d'année scolaire, vérifier uniquement les affectations sans année scolaire
                existing = existing.filter(annee_scolaire__isnull=True)
            
            if existing.exists():
                annee_info = f" pour l'année scolaire {self.annee_scolaire.libelle}" if self.annee_scolaire else ""
                raise ValidationError(
                    f"Le professeur {self.professeur.nom_complet} est déjà affecté à la classe {self.classe.nom}{annee_info}."
                )
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def affecter_toutes_matieres(cls, professeur, classe):
        """
        Affecte toutes les matières disponibles de la classe au professeur.
        Utile pour les enseignants polyvalents du primaire.
        """
        # Créer ou récupérer l'affectation
        affectation, created = cls.objects.get_or_create(
            professeur=professeur,
            classe=classe,
            defaults={'statut': 'polyvalent', 'actif': True}
        )
        
        # Récupérer toutes les matières du primaire
        matieres_primaire = Matiere.objects.filter(
            etablissement=professeur.etablissement,
            niveau__in=['primaire', 'tous']
        )
        
        # Ajouter toutes les matières
        affectation.matieres.set(matieres_primaire)
        
        return affectation
    
    @classmethod
    def get_matieres_enseignees(cls, professeur, classe):
        """
        Retourne les matières enseignées par le professeur dans la classe.
        """
        try:
            affectation = cls.objects.get(
                professeur=professeur,
                classe=classe,
                actif=True
            )
            return affectation.matieres.all()
        except cls.DoesNotExist:
            return Matiere.objects.none()
    
    @property
    def statut_display(self):
        """Retourne l'affichage du statut"""
        return dict(self.STATUT_CHOICES).get(self.statut, self.statut)
    
    @property
    def is_principal(self):
        """Retourne True si c'est un professeur principal"""
        return self.statut == 'principal'
    
    @property
    def nombre_matieres(self):
        """Retourne le nombre de matières enseignées"""
        return self.matieres.count()

