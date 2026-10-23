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

    # Supérieur : une même matière (EC) peut être partagée entre plusieurs enseignants.
    ROLE_COMPLET = 'complet'
    ROLE_CHOICES = [
        ('complet', 'EC complet (CM, TD et TP)'),
        ('cm', 'Cours magistral (CM)'),
        ('td', 'Travaux dirigés (TD)'),
        ('tp', 'Travaux pratiques (TP)'),
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
    role_enseignement = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default=ROLE_COMPLET,
        verbose_name="Rôle dans la matière",
    )
    groupe = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name="Groupe",
        help_text="Groupe de TD / TP (ex. G1, G2). Vide = toute la classe.",
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
        # Contrainte unique incluant l'année scolaire pour permettre plusieurs affectations pour différentes années
        unique_together = ['professeur', 'classe', 'matiere', 'annee_scolaire', 'role_enseignement', 'groupe']
        ordering = ['-date_affectation']
        indexes = [
            models.Index(fields=['professeur', 'classe', 'matiere', 'annee_scolaire']),
            models.Index(fields=['annee_scolaire', 'actif']),
        ]
    
    def __str__(self):
        return f"{self.professeur.nom_complet} - {self.classe.nom} ({self.get_statut_display()})"

    @property
    def libelle_role(self):
        """« CM », « TD G1 »… (vide pour un EC complet)."""
        if self.role_enseignement == self.ROLE_COMPLET:
            return ''
        return f"{self.role_enseignement.upper()} {self.groupe}".strip()
    
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
        
        # Vérifier s'il y a déjà un professeur de la même matière pour cette classe et cette année scolaire
        existing_same_matiere = AffectationProfesseur.objects.filter(
            classe=self.classe,
            matiere=self.matiere,
            actif=True
        )
        # Filtrer par année scolaire si elle est définie
        if self.annee_scolaire:
            existing_same_matiere = existing_same_matiere.filter(annee_scolaire=self.annee_scolaire)
        else:
            # Si pas d'année scolaire, vérifier uniquement les affectations sans année scolaire
            existing_same_matiere = existing_same_matiere.filter(annee_scolaire__isnull=True)
        existing_same_matiere = existing_same_matiere.exclude(pk=self.pk)
        
        self.groupe = (self.groupe or '').strip().upper()
        superieur = getattr(self.classe.etablissement, 'type_etablissement', None) == 'superieur'
        if not superieur:
            # Primaire / secondaire : un seul enseignant par matière, rôle non utilisé.
            self.role_enseignement, self.groupe = self.ROLE_COMPLET, ''
        elif self.role_enseignement == self.ROLE_COMPLET:
            self.groupe = ''
        if superieur and self.role_enseignement != self.ROLE_COMPLET:
            # Conflit si le même rôle et groupe sont déjà pris, ou si quelqu'un assure tout l'EC.
            existing_same_matiere = existing_same_matiere.filter(
                models.Q(role_enseignement=self.ROLE_COMPLET)
                | models.Q(role_enseignement=self.role_enseignement, groupe=self.groupe)
            )
        if existing_same_matiere.exists():
            existing = existing_same_matiere.first()
            annee_info = f" pour l'année scolaire {self.annee_scolaire.libelle}" if self.annee_scolaire else ""
            if superieur:
                role_txt = existing.libelle_role or "l'EC complet"
                raise ValidationError(
                    f"{existing.professeur.nom_complet} assure déjà {role_txt} de {self.matiere.nom} "
                    f"en {self.classe.nom}{annee_info}. Choisissez un autre rôle (CM, TD, TP) ou un autre groupe."
                )
            raise ValidationError(
                f"Il y a déjà un professeur de {self.matiere.nom} "
                f"({existing.professeur.nom_complet}) affecté à la classe {self.classe.nom}{annee_info}. "
                f"Une classe ne peut avoir qu'un seul enseignant par matière par année scolaire."
            )
        
        # Vérifier s'il y a déjà un professeur principal pour cette classe et cette année scolaire
        if self.statut == 'principal':
            existing_principal = AffectationProfesseur.objects.filter(
                classe=self.classe,
                statut='principal',
                actif=True
            )
            # Filtrer par année scolaire si elle est définie
            if self.annee_scolaire:
                existing_principal = existing_principal.filter(annee_scolaire=self.annee_scolaire)
            else:
                # Si pas d'année scolaire, vérifier uniquement les affectations sans année scolaire
                existing_principal = existing_principal.filter(annee_scolaire__isnull=True)
            existing_principal = existing_principal.exclude(pk=self.pk)
            
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
