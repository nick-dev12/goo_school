"""
Modèle pour stocker les moyennes calculées par période selon la pondération configurée.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal


class MoyennePeriode(models.Model):
    """
    Modèle pour enregistrer les moyennes calculées selon la pondération configurée.
    Stocke à la fois les moyennes par matière et la moyenne générale de la période.
    """
    
    eleve = models.ForeignKey(
        'school_admin.Eleve',
        on_delete=models.CASCADE,
        related_name='moyennes_periodes',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='moyennes_periodes',
        verbose_name="Établissement"
    )
    
    periode = models.ForeignKey(
        'school_admin.PeriodeScolaire',
        on_delete=models.CASCADE,
        related_name='moyennes_periodes',
        verbose_name="Période scolaire"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moyennes_periodes_annee_scolaire',
        verbose_name="Année scolaire"
    )
    
    matiere = models.ForeignKey(
        'school_admin.Matiere',
        on_delete=models.CASCADE,
        related_name='moyennes_periodes',
        verbose_name="Matière",
        null=True,
        blank=True,
        help_text="Null pour la ligne de moyenne générale"
    )
    
    # Données pour le calcul
    moyenne_classe = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Moyenne de contrôle continu"
    )
    
    note_examen = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Note d'examen"
    )

    note_rattrapage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Note de rattrapage",
        help_text="Session dont le nom contient « rattrap » ; retenue si supérieure à la note d'examen pour le calcul LMD.",
    )
    
    moyenne_matiere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Moyenne de la matière (calculée selon pondération)"
    )
    
    coefficient = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(0)],
        verbose_name="Coefficient de la matière"
    )

    credits = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Crédits utilisés au calcul (supérieur)",
        help_text="Crédits de la matière au moment du calcul (enseignement supérieur)"
    )
    
    total_matiere = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Total matière (moyenne_matiere × coefficient)"
    )
    
    moyenne_avec_coefficient = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Moyenne avec coefficient (moyenne_matiere × coefficient)",
        help_text="Moyenne de l'élève multipliée par le coefficient de la matière"
    )
    
    # Moyenne générale (valable pour toutes les matières de la période)
    moyenne_generale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        null=True,
        blank=True,
        verbose_name="Moyenne générale de la période"
    )
    
    rang = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Rang de l'élève dans la classe"
    )
    
    appreciation_matiere = models.TextField(
        blank=True,
        null=True,
        verbose_name="Appréciation de la matière"
    )
    
    appreciation_generale = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Appréciation générale"
    )
    
    decision_conseil = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Décision du conseil"
    )

    numero_serie = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Numéro de série du bulletin"
    )

    signature_numerique = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name="Signature numérique (SHA-256)"
    )

    qr_code_data = models.TextField(
        blank=True,
        null=True,
        verbose_name="Payload encodé dans le QR code"
    )

    qr_code_image = models.ImageField(
        upload_to='bulletins/qrcodes/',
        blank=True,
        null=True,
        verbose_name="Image du QR code du bulletin"
    )

    qr_code_generated_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Date de génération du QR code"
    )

    est_publie = models.BooleanField(
        default=False,
        verbose_name="Bulletin publié"
    )

    afficher_bulletin = models.BooleanField(
        default=True,
        verbose_name="Bulletin visible par l'élève",
        help_text="Détermine si la moyenne générale et le bulletin sont visibles dans l'espace élève."
    )

    date_publication = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de publication"
    )
    
    # Métadonnées
    poids_classe = models.PositiveSmallIntegerField(
        default=50,
        verbose_name="Poids contrôle continu (%)",
        help_text="Pourcentage utilisé pour le calcul"
    )
    
    poids_examen = models.PositiveSmallIntegerField(
        default=50,
        verbose_name="Poids examen (%)",
        help_text="Pourcentage utilisé pour le calcul"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date du calcul"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification"
    )
    
    est_moyenne_generale = models.BooleanField(
        default=False,
        verbose_name="Est moyenne générale",
        help_text="True si cette ligne représente la moyenne générale (sans matière)"
    )
    
    class Meta:
        verbose_name = "Moyenne de période"
        verbose_name_plural = "Moyennes de période"
        unique_together = [
            ['eleve', 'etablissement', 'periode', 'matiere', 'est_moyenne_generale'],
        ]
        ordering = ['periode', 'eleve', '-est_moyenne_generale', 'matiere']
        indexes = [
            models.Index(fields=['eleve', 'periode']),
            models.Index(fields=['etablissement', 'periode']),
        ]
    
    def __str__(self):
        if self.est_moyenne_generale or not self.matiere:
            return f"{self.eleve.nom_complet} - Moyenne générale - {self.periode.nom_periode}: {self.moyenne_generale}/20"
        else:
            return f"{self.eleve.nom_complet} - {self.matiere.nom} - {self.periode.nom_periode}: {self.moyenne_matiere}/20"
    
    def calculer_moyenne_matiere(self):
        """
        Calcule la moyenne de la matière selon la pondération configurée.
        Formule : (moyenne_classe × poids_classe/100) + (note_examen × poids_examen/100)
        """
        if self.moyenne_classe is None and self.note_examen is None:
            return None
        
        poids_classe_decimal = Decimal(str(self.poids_classe)) / Decimal('100')
        poids_examen_decimal = Decimal(str(self.poids_examen)) / Decimal('100')
        
        total = Decimal('0')
        poids_total = Decimal('0')
        
        if self.moyenne_classe is not None:
            total += Decimal(str(self.moyenne_classe)) * poids_classe_decimal
            poids_total += poids_classe_decimal
        
        if self.note_examen is not None:
            total += Decimal(str(self.note_examen)) * poids_examen_decimal
            poids_total += poids_examen_decimal
        
        if poids_total > 0:
            moyenne = total / poids_total
            return moyenne.quantize(Decimal('0.01'))
        return None
    
    def calculer_total_matiere(self):
        """Calcule le total matière (moyenne_matiere × coefficient)."""
        if self.moyenne_matiere is not None and self.coefficient:
            return (Decimal(str(self.moyenne_matiere)) * Decimal(str(self.coefficient))).quantize(Decimal('0.01'))
        return None
    
    def save(self, *args, **kwargs):
        """Surcharge pour calculer automatiquement moyenne_matiere et total_matiere."""
        if self.matiere and not self.est_moyenne_generale:  # Seulement pour les matières
            if self.moyenne_matiere is None:
                self.moyenne_matiere = self.calculer_moyenne_matiere()
            if self.total_matiere is None and self.moyenne_matiere is not None:
                self.total_matiere = self.calculer_total_matiere()
        super().save(*args, **kwargs)


class MoyenneAnnuelle(models.Model):
    """
    Modèle pour stocker la moyenne annuelle calculée pour un élève.
    La moyenne annuelle est calculée en additionnant toutes les moyennes des périodes
    et en divisant par le nombre de périodes.
    """
    
    eleve = models.ForeignKey(
        'school_admin.Eleve',
        on_delete=models.CASCADE,
        related_name='moyennes_annuelles',
        verbose_name="Élève"
    )
    
    etablissement = models.ForeignKey(
        'school_admin.Etablissement',
        on_delete=models.CASCADE,
        related_name='moyennes_annuelles',
        verbose_name="Établissement"
    )
    
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.CASCADE,
        related_name='moyennes_annuelles',
        verbose_name="Année scolaire"
    )
    
    periode_calcul = models.ForeignKey(
        'school_admin.PeriodeScolaire',
        on_delete=models.CASCADE,
        related_name='moyennes_annuelles_calculees',
        verbose_name="Période où le calcul a été effectué",
        help_text="La période à partir de laquelle la moyenne annuelle a été calculée"
    )
    
    moyenne_annuelle = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Moyenne annuelle"
    )
    
    nombre_periodes = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de périodes utilisées pour le calcul",
        help_text="Nombre de périodes dont les moyennes ont été additionnées"
    )
    
    date_calcul = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de calcul"
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )
    
    class Meta:
        verbose_name = "Moyenne annuelle"
        verbose_name_plural = "Moyennes annuelles"
        unique_together = ('eleve', 'etablissement', 'annee_scolaire', 'periode_calcul')
        ordering = ['-date_calcul', 'eleve__nom', 'eleve__prenom']
        indexes = [
            models.Index(fields=['eleve', 'annee_scolaire', 'periode_calcul']),
            models.Index(fields=['etablissement', 'annee_scolaire']),
        ]
    
    def __str__(self):
        return f"Moyenne annuelle {self.eleve.nom_complet} - {self.annee_scolaire.libelle} ({self.periode_calcul.nom_periode})"
