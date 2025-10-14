from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

class AffectationSalle(models.Model):
    """Modèle pour gérer les affectations des salles aux classes"""
    
    JOUR_SEMAINE_CHOICES = [
        ('lundi', 'Lundi'),
        ('mardi', 'Mardi'),
        ('mercredi', 'Mercredi'),
        ('jeudi', 'Jeudi'),
        ('vendredi', 'Vendredi'),
        ('samedi', 'Samedi'),
        ('dimanche', 'Dimanche'),
    ]
    
    PERIODE_CHOICES = [
        ('matin', 'Matin'),
        ('apres_midi', 'Après-midi'),
        ('soir', 'Soir'),
        ('journee_complete', 'Journée complète'),
    ]
    
    STATUT_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('temporaire', 'Temporaire'),
    ]

    # Relations principales
    classe = models.ForeignKey(
        'Classe',
        on_delete=models.CASCADE,
        related_name='affectations_salles',
        verbose_name="Classe"
    )
    salle = models.ForeignKey(
        'Salle',
        on_delete=models.CASCADE,
        related_name='affectations_classes',
        verbose_name="Salle"
    )
    
    # Informations d'affectation
    jour_semaine = models.CharField(
        max_length=10,
        choices=JOUR_SEMAINE_CHOICES,
        verbose_name="Jour de la semaine"
    )
    periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        default='journee_complete',
        verbose_name="Période"
    )
    
    # Heures (optionnelles pour une future intégration emploi du temps)
    heure_debut = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Heure de début"
    )
    heure_fin = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Heure de fin"
    )
    
    # Statut et gestion
    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default='active',
        verbose_name="Statut"
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    
    # Commentaires
    commentaire = models.TextField(
        blank=True,
        null=True,
        verbose_name="Commentaire",
        help_text="Commentaire sur cette affectation"
    )
    
    class Meta:
        verbose_name = "Affectation Salle"
        verbose_name_plural = "Affectations Salles"
        ordering = ['classe__nom', 'jour_semaine', 'periode']
        # Contrainte pour éviter les doublons d'affectation
        unique_together = ('classe', 'salle', 'jour_semaine', 'periode', 'actif')
    
    def __str__(self):
        return f"{self.classe.nom} - {self.salle.nom} ({self.get_jour_semaine_display()}, {self.get_periode_display()})"
    
    @property
    def nom_complet(self):
        """Retourne le nom complet de l'affectation"""
        return f"{self.classe.nom} → {self.salle.nom} ({self.get_jour_semaine_display()}, {self.get_periode_display()})"
    
    @property
    def est_active(self):
        """Vérifie si l'affectation est active"""
        return self.actif and self.statut == 'active'
    
    
    def clean(self):
        """Validation personnalisée"""
        super().clean()
        
        
        # Vérifier que les heures sont cohérentes
        if self.heure_debut and self.heure_fin and self.heure_debut >= self.heure_fin:
            raise ValidationError("L'heure de fin doit être postérieure à l'heure de début.")
        
        # Vérifier que la salle est disponible pour cette classe à ce moment
        if self.actif and self.statut == 'active':
            # Vérifier s'il y a un conflit avec une autre affectation active
            conflits = AffectationSalle.objects.filter(
                salle=self.salle,
                jour_semaine=self.jour_semaine,
                periode=self.periode,
                actif=True,
                statut='active'
            ).exclude(pk=self.pk)
            
            # Vérifier les conflits d'heures si spécifiées
            if self.heure_debut and self.heure_fin:
                conflits_heures = conflits.filter(
                    heure_debut__isnull=False,
                    heure_fin__isnull=False
                ).filter(
                    models.Q(
                        heure_debut__lt=self.heure_fin,
                        heure_fin__gt=self.heure_debut
                    )
                )
                
                if conflits_heures.exists():
                    conflit = conflits_heures.first()
                    raise ValidationError(
                        f"Conflit d'horaire détecté avec la classe {conflit.classe.nom} "
                        f"({conflit.heure_debut} - {conflit.heure_fin})"
                    )
            
            # Vérifier les conflits de période
            elif conflits.exists():
                conflit = conflits.first()
                raise ValidationError(
                    f"La salle {self.salle.nom} est déjà affectée à la classe {conflit.classe.nom} "
                    f"le {self.get_jour_semaine_display()} en {self.get_periode_display()}"
                )
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_affectations_classe(cls, classe, jour=None, periode=None):
        """Récupère les affectations d'une classe"""
        queryset = cls.objects.filter(classe=classe, actif=True, statut='active')
        
        if jour:
            queryset = queryset.filter(jour_semaine=jour)
        if periode:
            queryset = queryset.filter(periode=periode)
            
        return queryset.order_by('jour_semaine', 'periode')
    
    @classmethod
    def get_affectations_salle(cls, salle, jour=None, periode=None):
        """Récupère les affectations d'une salle"""
        queryset = cls.objects.filter(salle=salle, actif=True, statut='active')
        
        if jour:
            queryset = queryset.filter(jour_semaine=jour)
        if periode:
            queryset = queryset.filter(periode=periode)
            
        return queryset.order_by('jour_semaine', 'periode')
    
    @classmethod
    def get_disponibilites_salle(cls, salle, jour, periode):
        """Vérifie si une salle est disponible pour un jour et une période donnés"""
        return not cls.objects.filter(
            salle=salle,
            jour_semaine=jour,
            periode=periode,
            actif=True,
            statut='active'
        ).exists()
