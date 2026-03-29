"""
Modèle pour la gestion des périodes scolaires
"""
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone
from .etablissement_model import Etablissement

# Licence 1 → Doctorat 3 (périodes rattachées à un niveau LMD) — libellés explicites (pas d'abréviations seules)
NIVEAUX_PERIODE_SUPERIEUR = [
    ('L1', 'Licence 1'),
    ('L2', 'Licence 2'),
    ('L3', 'Licence 3'),
    ('M1', 'Master 1'),
    ('M2', 'Master 2'),
    ('D1', 'Doctorat 1'),
    ('D2', 'Doctorat 2'),
    ('D3', 'Doctorat 3'),
]
NIVEAUX_PERIODE_SUPERIEUR_KEYS = {k for k, _ in NIVEAUX_PERIODE_SUPERIEUR}

# Numérotation LMD : S1–S6 (Licence), S7–S10 (Master), S11–S16 (Doctorat).
# Chaque entrée : (valeur stockée dans nom_periode, libellé affiché en français clair).
SEMESTRES_PAR_NIVEAU_LMD = {
    'L1': [
        ('Semestre 1', 'Semestre 1 — 1er semestre de Licence 1'),
        ('Semestre 2', 'Semestre 2 — 2e semestre de Licence 1'),
    ],
    'L2': [
        ('Semestre 3', 'Semestre 3 — 1er semestre de Licence 2'),
        ('Semestre 4', 'Semestre 4 — 2e semestre de Licence 2'),
    ],
    'L3': [
        ('Semestre 5', 'Semestre 5 — 1er semestre de Licence 3'),
        ('Semestre 6', 'Semestre 6 — 2e semestre de Licence 3'),
    ],
    'M1': [
        ('Semestre 7', 'Semestre 7 — 1er semestre de Master 1'),
        ('Semestre 8', 'Semestre 8 — 2e semestre de Master 1'),
    ],
    'M2': [
        ('Semestre 9', 'Semestre 9 — 1er semestre de Master 2'),
        ('Semestre 10', 'Semestre 10 — 2e semestre de Master 2'),
    ],
    'D1': [
        ('Semestre 11', 'Semestre 11 — 1er semestre de Doctorat 1'),
        ('Semestre 12', 'Semestre 12 — 2e semestre de Doctorat 1'),
    ],
    'D2': [
        ('Semestre 13', 'Semestre 13 — 1er semestre de Doctorat 2'),
        ('Semestre 14', 'Semestre 14 — 2e semestre de Doctorat 2'),
    ],
    'D3': [
        ('Semestre 15', 'Semestre 15 — 1er semestre de Doctorat 3'),
        ('Semestre 16', 'Semestre 16 — 2e semestre de Doctorat 3'),
    ],
}


def semestres_choices_pour_niveau(niveau_code: str):
    """Liste de (nom_periode, libellé long) pour un code niveau LMD."""
    return list(SEMESTRES_PAR_NIVEAU_LMD.get((niveau_code or '').strip(), []))


def est_semestre_valide_pour_niveau(nom_periode: str, niveau_lmd: str) -> bool:
    """Indique si le couple (semestre officiel, niveau) est autorisé."""
    nk = (niveau_lmd or '').strip()
    nom = (nom_periode or '').strip()
    if not nk or not nom:
        return False
    return any(n == nom for n, _ in SEMESTRES_PAR_NIVEAU_LMD.get(nk, []))


def libelle_long_semestre(nom_periode: str, niveau_lmd: str) -> str:
    """Libellé long du semestre pour affichage (cartes, listes)."""
    nk = (niveau_lmd or '').strip()
    nom = (nom_periode or '').strip()
    for n, lib in SEMESTRES_PAR_NIVEAU_LMD.get(nk, []):
        if n == nom:
            return lib
    return nom


# Tous les noms de semestre possibles (validation souple / imports)
ENSEMBLE_NOMS_SEMESTRE_LMD = {
    nom for choices in SEMESTRES_PAR_NIVEAU_LMD.values() for nom, _ in choices
}


def est_premier_semestre_annee_universitaire(nom_periode: str, niveau_lmd: str) -> bool:
    """1er semestre de l'année pour le niveau (ex. S1 pour L1, S3 pour L2)."""
    pairs = SEMESTRES_PAR_NIVEAU_LMD.get((niveau_lmd or '').strip(), [])
    if len(pairs) < 2:
        return False
    return (nom_periode or '').strip() == pairs[0][0]


def est_deuxieme_semestre_annee_universitaire(nom_periode: str, niveau_lmd: str) -> bool:
    """2e semestre de l'année pour le niveau (ex. S2 pour L1, S4 pour L2) — bilan annuel possible."""
    pairs = SEMESTRES_PAR_NIVEAU_LMD.get((niveau_lmd or '').strip(), [])
    if len(pairs) < 2:
        return False
    return (nom_periode or '').strip() == pairs[1][0]


def nom_semestre_paire_meme_annee(nom_periode: str, niveau_lmd: str):
    """
    Autre semestre de la même année universitaire (S1↔S2, S3↔S4, etc.).
    Retourne le nom officiel (ex. « Semestre 1 ») ou None.
    """
    nk = (niveau_lmd or '').strip()
    nom = (nom_periode or '').strip()
    pairs = SEMESTRES_PAR_NIVEAU_LMD.get(nk, [])
    noms = [p[0] for p in pairs]
    if len(noms) < 2 or nom not in noms:
        return None
    idx = noms.index(nom)
    return noms[1 - idx]


def periode_scolaire_paire_pour_classe(etablissement, classe, annee_scolaire, periode_ref):
    """
    Trouve l'autre période (semestre pair) pour la même année scolaire et le même périmètre LMD que la classe.
    `periode_ref` est typiquement le semestre affiché (ex. Semestre 2).
    """
    if not annee_scolaire or not classe:
        return None
    autre_nom = nom_semestre_paire_meme_annee(periode_ref.nom_periode, classe.niveau_lmd)
    if not autre_nom:
        return None
    qs = PeriodeScolaire.objects.filter(
        etablissement=etablissement,
        annee_scolaire_fk=annee_scolaire,
        est_active=True,
        nom_periode=autre_nom,
    )
    return PeriodeScolaire.filter_queryset_for_classe(qs, etablissement, classe).order_by('date_debut').first()


class PeriodeScolaire(models.Model):
    """
    Modèle pour définir les périodes scolaires de l'établissement
    (Trimestres, Semestres, etc.)
    """
    
    TYPE_PERIODE_CHOICES = [
        ('trimestre', 'Trimestre'),
        ('semestre', 'Semestre'),
        ('annee', 'Année complète'),
    ]
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='periodes_scolaires',
        verbose_name="Établissement"
    )
    
    nom_periode = models.CharField(
        max_length=100,
        verbose_name="Nom de la période",
        help_text="Ex: 1er Trimestre, Semestre 1"
    )
    
    type_periode = models.CharField(
        max_length=20,
        choices=TYPE_PERIODE_CHOICES,
        default='trimestre',
        verbose_name="Type de période"
    )

    # Établissements supérieurs : rattachement à un niveau LMD (Licence → Doctorat).
    # Chaîne vide = périodes « globales » ou anciennes données (visibles pour tous les niveaux).
    niveau_lmd = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name="Niveau LMD",
        help_text="L1, L2, … pour les périodes propres à un niveau (supérieur uniquement).",
    )
    
    date_debut = models.DateField(
        verbose_name="Date de début",
        help_text="Date de début de la période"
    )
    
    date_fin = models.DateField(
        verbose_name="Date de fin",
        help_text="Date de fin de la période"
    )
    
    annee_scolaire = models.CharField(
        max_length=20,
        verbose_name="Année scolaire",
        help_text="Ex: 2025-2026"
    )
    annee_scolaire_fk = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='periodes_scolaires_annee_scolaire',
        verbose_name="Année scolaire (référence)"
    )
    
    est_active = models.BooleanField(
        default=True,
        verbose_name="Période active",
        help_text="Indique si cette période est actuellement active"
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
        verbose_name = "Période scolaire"
        verbose_name_plural = "Périodes scolaires"
        ordering = ['annee_scolaire', 'niveau_lmd', 'date_debut']
        constraints = [
            models.UniqueConstraint(
                fields=['etablissement', 'nom_periode', 'annee_scolaire', 'niveau_lmd'],
                name='unique_periode_par_niveau_annee',
            ),
        ]
    
    def __str__(self):
        return f"{self.nom_periode} ({self.annee_scolaire})"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que la date de fin est après la date de début
        if self.date_fin and self.date_debut and self.date_fin <= self.date_debut:
            raise ValidationError({
                'date_fin': "La date de fin doit être après la date de début."
            })
        
        # Cohérence LMD (supérieur) : semestre officiel ↔ niveau
        et = self.etablissement
        if et and getattr(et, 'type_etablissement', None) == 'superieur':
            nk = (self.niveau_lmd or '').strip()
            if nk and self.nom_periode and not est_semestre_valide_pour_niveau(self.nom_periode, nk):
                raise ValidationError({
                    'nom_periode': "Ce semestre ne correspond pas au niveau choisi (ex. : Licence 1 → Semestre 1 et 2 ; Licence 2 → Semestre 3 et 4, etc.)."
                })

        # Chevauchement : même année scolaire et même périmètre de niveau (niveau_lmd)
        if self.etablissement:
            scope = (self.niveau_lmd or '')
            periodes_existantes = PeriodeScolaire.objects.filter(
                etablissement=self.etablissement,
                annee_scolaire=self.annee_scolaire,
                niveau_lmd=scope,
            )
            if self.pk:
                periodes_existantes = periodes_existantes.exclude(pk=self.pk)
            for periode in periodes_existantes:
                if self.date_debut <= periode.date_fin and self.date_fin >= periode.date_debut:
                    raise ValidationError({
                        'date_debut': f"Une erreur s'est produite car une autre période ('{periode.nom_periode}') est déjà enregistrée dans ces tranches de l'année."
                    })
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour exécuter la validation
        """
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def libelle_niveau_lmd(self) -> str:
        """Libellé du niveau LMD pour l'affichage (supérieur)."""
        nk = (self.niveau_lmd or '').strip()
        if not nk:
            return ''
        return dict(NIVEAUX_PERIODE_SUPERIEUR).get(nk, nk)

    @property
    def libelle_affichage_superieur(self) -> str:
        """Titre lisible : semestre officiel + parcours (sans se limiter au code L1)."""
        nk = (self.niveau_lmd or '').strip()
        if not nk:
            return self.nom_periode
        long_sem = libelle_long_semestre(self.nom_periode, nk)
        return long_sem or self.nom_periode

    @property
    def duree_jours(self):
        """
        Calcule la durée de la période en jours
        """
        if self.date_debut and self.date_fin:
            return (self.date_fin - self.date_debut).days + 1
        return 0
    
    @property
    def est_en_cours(self):
        """
        Vérifie si la période est actuellement en cours
        """
        aujourdhui = timezone.now().date()
        return self.date_debut <= aujourdhui <= self.date_fin
    
    @property
    def est_future(self):
        """
        Vérifie si la période est dans le futur
        """
        aujourdhui = timezone.now().date()
        return self.date_debut > aujourdhui
    
    @property
    def est_passee(self):
        """
        Vérifie si la période est passée
        """
        aujourdhui = timezone.now().date()
        return self.date_fin < aujourdhui
    
    @property
    def statut_periode(self):
        """
        Retourne le statut de la période (en cours, à venir, terminée)
        """
        if self.est_en_cours:
            return 'en_cours'
        elif self.est_future:
            return 'a_venir'
        else:
            return 'terminee'
    
    @classmethod
    def get_periode_active(cls, etablissement):
        """
        Récupère la période actuellement active pour un établissement
        """
        aujourdhui = timezone.now().date()
        return cls.objects.filter(
            etablissement=etablissement,
            est_active=True,
            date_debut__lte=aujourdhui,
            date_fin__gte=aujourdhui
        ).first()
    
    @classmethod
    def get_periodes_annee(cls, etablissement, annee_scolaire):
        """
        Récupère toutes les périodes d'une année scolaire
        """
        return cls.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire
        ).order_by('date_debut')

    @classmethod
    def filter_queryset_for_classe(cls, queryset, etablissement, classe=None):
        """
        Filtre les périodes selon le niveau LMD de la classe (établissements supérieurs).
        Les périodes sans niveau (niveau_lmd vide) restent visibles pour tous les niveaux.
        Sans classe (tableaux de bord globaux) : aucun filtrage par niveau.
        """
        if classe is None:
            return queryset
        if not etablissement or getattr(etablissement, 'type_etablissement', None) != 'superieur':
            return queryset.filter(niveau_lmd='')
        if getattr(classe, 'niveau', None) == 'superieur':
            nk = (getattr(classe, 'niveau_lmd', None) or '').strip()
            if nk:
                return queryset.filter(Q(niveau_lmd='') | Q(niveau_lmd=nk))
            return queryset.filter(niveau_lmd='')
        return queryset.filter(niveau_lmd='')

