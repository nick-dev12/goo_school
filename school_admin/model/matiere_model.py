from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.utils import timezone
from .etablissement_model import Etablissement
from .classe_model import Classe


class Matiere(models.Model):
    """
    Modèle pour les matières enseignées dans l'établissement
    """
    
    # Types de matières
    TYPE_MATIERE_CHOICES = [
        ('obligatoire', 'Matière obligatoire'),
        ('optionnelle', 'Matière optionnelle'),
        ('facultative', 'Matière facultative'),
        ('sport', 'Éducation physique et sportive'),
        ('art', 'Arts et culture'),
        ('technique', 'Matière technique'),
    ]
    
    # Niveaux d'enseignement
    NIVEAU_CHOICES = [
        ('maternelle', 'Maternelle'),
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('superieur', 'Supérieur'),
        ('tous', 'Tous niveaux'),
    ]
    
    # Informations de base
    nom = models.CharField(max_length=100, verbose_name="Nom de la matière")
    code = models.CharField(max_length=10, unique=True, verbose_name="Code de la matière")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    
    # Classification
    type_matiere = models.CharField(
        max_length=20, 
        choices=TYPE_MATIERE_CHOICES, 
        default='obligatoire',
        verbose_name="Type de matière"
    )
    niveau = models.CharField(
        max_length=20, 
        choices=NIVEAU_CHOICES, 
        default='tous',
        verbose_name="Niveau d'enseignement"
    )
    
    # Relations
    etablissement = models.ForeignKey(
        Etablissement, 
        on_delete=models.CASCADE, 
        related_name='matieres',
        verbose_name="Établissement"
    )
    department = models.ForeignKey(
        'school_admin.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matieres',
        verbose_name="Filière",
        help_text="Filière à laquelle appartient la matière (obligatoire pour enseignement supérieur)"
    )
    module = models.ForeignKey(
        'school_admin.Module',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matieres',
        verbose_name="Module",
        help_text="Module auquel appartient la matière (enseignement supérieur)"
    )
    classes = models.ManyToManyField(
        Classe,
        blank=True,
        related_name='matieres',
        verbose_name="Classes concernées"
    )
    
    # Informations administratives
    coefficient = models.DecimalField(
        max_digits=3, 
        decimal_places=1, 
        default=1.0,
        verbose_name="Coefficient",
        help_text="Utilisé pour primaire/secondaire"
    )
    credits = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        verbose_name="Crédits",
        help_text="Utilisé pour enseignement supérieur (si matière dans un module)"
    )
  
    
    # Statut
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Matière"
        verbose_name_plural = "Matières"
        ordering = ['nom']
        constraints = [
            # Supérieur avec module : unicité (nom, etablissement, department, module) - permet plusieurs "Mathématiques" dans différents modules
            models.UniqueConstraint(
                fields=['nom', 'etablissement', 'department', 'module'],
                condition=Q(department__isnull=False) & Q(module__isnull=False),
                name='matiere_unique_par_module',
            ),
            # Supérieur sans module (legacy) : unicité (nom, etablissement, department)
            models.UniqueConstraint(
                fields=['nom', 'etablissement', 'department'],
                condition=Q(department__isnull=False) & Q(module__isnull=True),
                name='matiere_unique_par_filiere_sans_module',
            ),
            # Primaire/Secondaire : unicité (nom, etablissement) quand pas de filière
            models.UniqueConstraint(
                fields=['nom', 'etablissement'],
                condition=Q(department__isnull=True),
                name='matiere_unique_sans_filiere',
            ),
        ]
    
    def __str__(self):
        return f"{self.nom} ({self.code})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de la matière"""
        return f"{self.nom} ({self.code})"
    
    @property
    def type_display(self):
        """Retourne l'affichage du type de matière"""
        return dict(self.TYPE_MATIERE_CHOICES).get(self.type_matiere, self.type_matiere)
    
    def get_poids_calcul(self, etablissement, classe=None):
        """
        Retourne le coefficient ou les crédits selon le type d'établissement.
        Pour le supérieur : utilise les crédits (matière ou module).
        Pour primaire/secondaire : utilise le coefficient.
        """
        if etablissement.type_etablissement == 'superieur':
            if self.module:
                if self.credits is not None and self.credits > 0:
                    return Decimal(str(self.credits))
                if classe:
                    mod_credits = self.module.get_credits_for_classe(classe)
                    if mod_credits and mod_credits > 0:
                        count = self.module.matieres.count()
                        return (Decimal(str(mod_credits)) / Decimal(str(count))) if count > 0 else Decimal('1')
                else:
                    total_mod = self.module.total_credits
                    if total_mod and total_mod > 0:
                        count = self.module.matieres.count()
                        return (Decimal(str(total_mod)) / Decimal(str(count))) if count > 0 else Decimal('1')
            return Decimal(str(self.coefficient)) if self.coefficient else Decimal('1')
        if etablissement.type_etablissement in ['lycée', 'collège_lycée', 'lycee_college', 'mixte', 'lycee', 'college']:
            from .coefficient_matiere_groupe_model import CoefficientMatiereGroupe
            coeff = CoefficientMatiereGroupe.get_coefficient_for_classe(self, classe)
            return Decimal(str(coeff)) if coeff else Decimal('1')
        return Decimal(str(self.coefficient)) if self.coefficient else Decimal('1')

    @property
    def niveau_display(self):
        """Retourne l'affichage du niveau d'enseignement"""
        return dict(self.NIVEAU_CHOICES).get(self.niveau, self.niveau)
    
    def get_classes_display(self):
        """Retourne l'affichage des classes concernées"""
        if not self.classes.exists():
            return "Aucune classe assignée"
        classes = [classe.nom for classe in self.classes.all()]
        return ", ".join(classes)
    
    def get_classes_count(self):
        """Retourne le nombre de classes assignées"""
        return self.classes.count()

    def get_classe_ids_pour_affectation_superieur(self):
        """
        Identifiants des classes cibles pour une affectation (supérieur) :
        classes liées à la matière, ou au module (ModuleClasse) si la matière n'en définit pas.
        Liste vide = aucune restriction fine (cohérence filière / établissement gérée côté contrôleurs).
        """
        ids = {c.id for c in self.classes.all()}
        if self.module_id:
            ids.update(c.id for c in self.module.classes.all())
        return sorted(ids)

    def get_classe_ids_pour_affectation_superieur_csv(self):
        """Pour attributs data-* dans les formulaires (JS)."""
        return ','.join(str(i) for i in self.get_classe_ids_pour_affectation_superieur())

    def classe_est_compatible_affectation_superieur(self, classe):
        """True si la classe peut recevoir cette matière selon les liaisons matière/module-classes."""
        ids = self.get_classe_ids_pour_affectation_superieur()
        if not ids:
            return True
        return classe.id in ids

    def save(self, *args, **kwargs):
        # Générer le code si pas défini
        if not self.code:
            self.code = self.nom[:3].upper()
        super().save(*args, **kwargs)
