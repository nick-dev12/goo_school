# school_admin/model/classe_model.py

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Libellés longs pour l'affichage (liste des classes, etc.) — évite « L1 » seul au profit de « Licence 1 »
NIVEAU_LMD_LIBELLES_COMPLETS = {
    'L1': 'Licence 1',
    'L2': 'Licence 2',
    'L3': 'Licence 3',
    'M1': 'Master 1',
    'M2': 'Master 2',
    'D1': 'Doctorat 1',
    'D2': 'Doctorat 2',
    'D3': 'Doctorat 3',
    'BTS': 'Brevet de Technicien Supérieur',
    'DUT': 'Diplôme Universitaire de Technologie',
    'BUT': 'Bachelor Universitaire de Technologie',
    'BT': 'Brevet de Technicien',
    'LP': 'Licence professionnelle',
    'CERT': 'Certificat',
    'DIPL': 'Diplôme',
    'AUTRE': 'Autre',
}


def libelle_cle_niveau_superieur(niveau_key):
    """
    Libellé long pour une clé de regroupement (L1, BTS, …) ou texte personnalisé (AUTRE).
    """
    if niveau_key is None or niveau_key == '':
        return ''
    key = str(niveau_key).strip()
    if key in NIVEAU_LMD_LIBELLES_COMPLETS:
        return NIVEAU_LMD_LIBELLES_COMPLETS[key]
    return key


class Classe(models.Model):
    """
    Modèle représentant une classe dans un établissement
    """
    NIVEAU_CHOICES = [
        ('maternelle', 'Maternelle'),
        ('primaire', 'Primaire'),
        ('college', 'Collège'),
        ('lycee', 'Lycée'),
        ('superieur', 'Supérieur'),
    ]
    
    # Informations de base
    nom = models.CharField(max_length=100, verbose_name="Nom de la classe")
    niveau = models.CharField(max_length=20, choices=NIVEAU_CHOICES, verbose_name="Niveau")
    code_classe = models.CharField(max_length=20, unique=True, verbose_name="Code de la classe")
    capacite_max = models.PositiveIntegerField(default=30, verbose_name="Capacité maximale")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    
    # Relation avec l'établissement
    etablissement = models.ForeignKey(
        'school_admin.Etablissement', 
        on_delete=models.CASCADE,
        related_name='classes',
        verbose_name="Établissement"
    )
    
    # Champs LMD (établissements supérieurs uniquement)
    academic_level = models.ForeignKey(
        'school_admin.AcademicLevel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='classes',
        verbose_name="Niveau académique (LMD)"
    )
    department = models.ForeignKey(
        'school_admin.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='classes',
        verbose_name="Filière / Département"
    )
    niveau_lmd = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Niveau (L1, BTS, DUT, etc.)",
        help_text="LMD, BTS, DUT, Certificat ou Autre pour les établissements supérieurs"
    )
    niveau_libelle = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Niveau personnalisé (si Autre)",
        help_text="Détail du niveau lorsque « Autre » est sélectionné (ex: Formation Court Métrage 6 mois)"
    )
    
    # Informations système
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    def __str__(self):
        return f"{self.nom} - {self.get_niveau_display()}"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de la classe"""
        return f"{self.nom} ({self.get_niveau_display()})"
    
    @property
    def nombre_eleves(self):
        """Retourne le nombre d'élèves dans cette classe"""
        from .eleve_model import Eleve
        return Eleve.objects.filter(classe=self, actif=True).count()
    
    @property
    def places_disponibles(self):
        """Retourne le nombre de places disponibles"""
        return max(0, self.capacite_max - self.nombre_eleves)
    
    @property
    def taux_occupation(self):
        """Retourne le taux d'occupation en pourcentage"""
        if self.capacite_max == 0:
            return 0
        return round((self.nombre_eleves / self.capacite_max) * 100, 1)

    def get_libelle_niveau_superieur_complet(self):
        """
        Libellé lisible du niveau pour le supérieur (ex. « Licence 1 » au lieu de « L1 »).
        """
        if self.niveau != 'superieur':
            return ''
        if self.niveau_lmd == 'AUTRE' and self.niveau_libelle:
            return self.niveau_libelle.strip()
        if self.niveau_lmd and self.niveau_lmd in NIVEAU_LMD_LIBELLES_COMPLETS:
            return NIVEAU_LMD_LIBELLES_COMPLETS[self.niveau_lmd]
        if self.niveau_lmd:
            return self.niveau_lmd
        if self.academic_level_id:
            return f'{self.academic_level.code} — {self.academic_level.nom}'
        # Comportement précédent : défaut « L1 » ; on affiche le libellé long équivalent
        return NIVEAU_LMD_LIBELLES_COMPLETS['L1']

    def get_libelle_niveau_complet_pour_eleve(self):
        """
        Libellé du niveau pour l’espace élève (supérieur : LMD long ; autres : cycle + niveau académique si présent).
        """
        if self.niveau == 'superieur':
            return self.get_libelle_niveau_superieur_complet()
        parts = [self.get_niveau_display()]
        if self.academic_level_id:
            parts.append(self.academic_level.nom)
        return ' — '.join(parts)
    
    class Meta:
        verbose_name = "Classe"
        verbose_name_plural = "Classes"
        ordering = ['niveau', 'nom']
        unique_together = None  # Remplacé par des contraintes conditionnelles
        constraints = [
            # Primaire/Secondaire : unicité (etablissement, niveau, nom)
            models.UniqueConstraint(
                fields=['etablissement', 'niveau', 'nom'],
                condition=Q(niveau__in=['maternelle', 'primaire', 'college', 'lycee']),
                name='unique_classe_primaire_secondaire',
            ),
            # Supérieur (niveau standard) : unicité (etablissement, niveau_lmd, nom)
            models.UniqueConstraint(
                fields=['etablissement', 'niveau_lmd', 'nom'],
                condition=Q(niveau='superieur') & Q(niveau_lmd__isnull=False) & ~Q(niveau_lmd='AUTRE'),
                name='unique_classe_superieur_standard',
            ),
            # Supérieur Autre : unicité (etablissement, niveau_libelle, nom)
            models.UniqueConstraint(
                fields=['etablissement', 'niveau_libelle', 'nom'],
                condition=Q(niveau='superieur') & Q(niveau_lmd='AUTRE') & Q(niveau_libelle__isnull=False),
                name='unique_classe_superieur_autre',
            ),
            # Supérieur sans niveau (fallback) : unicité (etablissement, nom)
            models.UniqueConstraint(
                fields=['etablissement', 'nom'],
                condition=Q(niveau='superieur') & Q(niveau_lmd__isnull=True),
                name='unique_classe_superieur_sans_lmd',
            ),
        ]
