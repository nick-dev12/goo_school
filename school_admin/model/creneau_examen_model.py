"""
Modèle pour la gestion des créneaux d'examens
"""
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from .session_examen_model import SessionExamen
from .classe_model import Classe
from .matiere_model import Matiere
from .professeur_model import Professeur
from .salle_model import Salle


class CreneauExamen(models.Model):
    """
    Modèle pour représenter un créneau horaire d'examen selon la logique sénégalaise
    Un créneau = une matière à un jour/heure spécifique pour un niveau de classes
    """
    
    # Relation avec la session d'examen globale
    session_examen = models.ForeignKey(
        SessionExamen,
        on_delete=models.CASCADE,
        related_name='creneaux',
        verbose_name="Session d'examen"
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_examens_annee_scolaire',
        verbose_name="Année scolaire"
    )
    
    # Matière concernée par ce créneau
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='creneaux_examens',
        verbose_name="Matière"
    )
    
    # Horaires du créneau
    date_examen = models.DateField(
        verbose_name="Date de l'examen"
    )
    
    heure_debut = models.TimeField(
        verbose_name="Heure de début"
    )
    
    heure_fin = models.TimeField(
        verbose_name="Heure de fin"
    )
    
    # Surveillance et salle (optionnels pour le créneau global)
    surveillant = models.ForeignKey(
        Professeur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_surveillance',
        verbose_name="Surveillant principal"
    )
    
    salle = models.ForeignKey(
        Salle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creneaux_examens',
        verbose_name="Salle principale"
    )
    
    # Informations complémentaires
    consignes_specifiques = models.TextField(
        blank=True,
        null=True,
        verbose_name="Consignes spécifiques",
        help_text="Instructions particulières pour ce créneau"
    )
    
    duree_estimee = models.DurationField(
        blank=True,
        null=True,
        verbose_name="Durée estimée"
    )
    
    # Statut
    est_confirme = models.BooleanField(
        default=False,
        verbose_name="Créneau confirmé"
    )
    
    est_annule = models.BooleanField(
        default=False,
        verbose_name="Créneau annulé"
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
        verbose_name = "Créneau d'examen"
        verbose_name_plural = "Créneaux d'examens"
        ordering = ['date_examen', 'heure_debut']
        unique_together = ['session_examen', 'matiere', 'date_examen']
    
    def __str__(self):
        return f"{self.session_examen.nom_examen} - {self.matiere.nom} ({self.date_examen} {self.heure_debut})"
    
    def clean(self):
        """
        Validation personnalisée
        """
        super().clean()
        
        # Vérifier que l'heure de fin est après l'heure de début
        if self.heure_fin and self.heure_debut and self.heure_fin <= self.heure_debut:
            raise ValidationError({
                'heure_fin': "L'heure de fin doit être après l'heure de début."
            })
        
        # Vérifier que la matière fait bien partie de la session d'examen
        if self.session_examen and self.matiere:
            if not self.session_examen.matieres.filter(id=self.matiere.id).exists():
                raise ValidationError({
                    'matiere': f"La matière {self.matiere.nom} ne fait pas partie de la session d'examen '{self.session_examen.nom_examen}'."
                })
        
        # La date doit tomber dans les dates de la session (et donc de la période)
        if self.session_examen and self.date_examen:
            sess = self.session_examen
            if self.date_examen < sess.date_debut or self.date_examen > sess.date_fin:
                raise ValidationError({
                    'date_examen': f"La date doit être comprise entre le {sess.date_debut:%d/%m/%Y} et le {sess.date_fin:%d/%m/%Y} (dates de la session)."
                })

        # Vérifier les conflits de salle
        if self.salle and self.date_examen and self.heure_debut and self.heure_fin:
            conflits_salle = CreneauExamen.objects.filter(
                salle=self.salle,
                date_examen=self.date_examen,
                est_annule=False,
                actif=True
            )
            
            if self.pk:
                conflits_salle = conflits_salle.exclude(pk=self.pk)
            
            for creneau in conflits_salle:
                if (self.heure_debut < creneau.heure_fin and self.heure_fin > creneau.heure_debut):
                    raise ValidationError({
                        'salle': f"La salle {self.salle.nom} est déjà réservée pour '{creneau.session_examen.nom_examen} - {creneau.matiere.nom}' de {creneau.heure_debut} à {creneau.heure_fin}."
                    })
        
        # Vérifier les conflits de surveillant
        if self.surveillant and self.date_examen and self.heure_debut and self.heure_fin:
            conflits_surveillant = CreneauExamen.objects.filter(
                surveillant=self.surveillant,
                date_examen=self.date_examen,
                est_annule=False,
                actif=True
            )
            
            if self.pk:
                conflits_surveillant = conflits_surveillant.exclude(pk=self.pk)
            
            for creneau in conflits_surveillant:
                if (self.heure_debut < creneau.heure_fin and self.heure_fin > creneau.heure_debut):
                    raise ValidationError({
                        'surveillant': f"{self.surveillant.nom_complet} surveille déjà '{creneau.session_examen.nom_examen} - {creneau.matiere.nom}' de {creneau.heure_debut} à {creneau.heure_fin}."
                    })

        # Une même classe ne peut pas composer deux épreuves en même temps (toutes sessions confondues)
        if self.session_examen and self.matiere and self.date_examen and self.heure_debut and self.heure_fin:
            from school_admin.services.examens_planning import classes_concernees
            mes_classes = set(c.id for c in classes_concernees(self.session_examen, self.matiere))
            autres = CreneauExamen.objects.filter(
                date_examen=self.date_examen, est_annule=False, actif=True,
                heure_debut__lt=self.heure_fin, heure_fin__gt=self.heure_debut,
                session_examen__etablissement_id=self.session_examen.etablissement_id,
            ).select_related('session_examen', 'matiere')
            if self.pk:
                autres = autres.exclude(pk=self.pk)
            for creneau in autres:
                communes = mes_classes & set(c.id for c in classes_concernees(creneau.session_examen, creneau.matiere))
                if communes:
                    from school_admin.model.classe_model import Classe
                    noms = ', '.join(Classe.objects.filter(id__in=communes).order_by('nom').values_list('nom', flat=True)[:4])
                    raise ValidationError({
                        'heure_debut': f"Conflit d'horaire : {noms} compose(nt) déjà « {creneau.matiere.nom} » "
                                       f"de {creneau.heure_debut:%H:%M} à {creneau.heure_fin:%H:%M}."
                    })

    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour calculer la durée
        """
        # Calculer la durée estimée
        if self.heure_debut and self.heure_fin:
            from datetime import datetime
            debut = datetime.combine(datetime.today(), self.heure_debut)
            fin = datetime.combine(datetime.today(), self.heure_fin)
            self.duree_estimee = fin - debut
        
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def duree_format(self):
        """
        Retourne la durée formatée en heures et minutes
        """
        if self.duree_estimee:
            total_seconds = int(self.duree_estimee.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if hours > 0:
                return f"{hours}h{minutes:02d}"
            else:
                return f"{minutes} min"
        return "Non définie"
    
    @property
    def est_passe(self):
        """
        Vérifie si le créneau est passé
        """
        aujourdhui = timezone.now().date()
        heure_actuelle = timezone.now().time()
        
        if self.date_examen < aujourdhui:
            return True
        elif self.date_examen == aujourdhui and self.heure_fin < heure_actuelle:
            return True
        return False
    
    @property
    def est_en_cours(self):
        """
        Vérifie si le créneau est en cours
        """
        aujourdhui = timezone.now().date()
        heure_actuelle = timezone.now().time()
        
        if self.date_examen == aujourdhui:
            if self.heure_debut <= heure_actuelle <= self.heure_fin:
                return True
        return False
    
    @property
    def est_a_venir(self):
        """
        Vérifie si le créneau est à venir
        """
        aujourdhui = timezone.now().date()
        heure_actuelle = timezone.now().time()
        
        if self.date_examen > aujourdhui:
            return True
        elif self.date_examen == aujourdhui and self.heure_debut > heure_actuelle:
            return True
        return False
    
    @property
    def statut_creneau(self):
        """
        Retourne le statut du créneau
        """
        if self.est_annule:
            return 'annule'
        elif self.est_passe:
            return 'passe'
        elif self.est_en_cours:
            return 'en_cours'
        else:
            return 'a_venir'
    
    @classmethod
    def get_creneaux_session(cls, session_examen):
        """
        Récupère tous les créneaux d'une session d'examen
        """
        return cls.objects.filter(
            session_examen=session_examen,
            actif=True
        ).select_related('matiere', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    @classmethod
    def get_creneaux_matiere(cls, matiere):
        """
        Récupère tous les créneaux d'une matière
        """
        return cls.objects.filter(
            matiere=matiere,
            actif=True
        ).select_related('session_examen', 'surveillant', 'salle').order_by('date_examen', 'heure_debut')
    
    @classmethod
    def get_creneaux_date(cls, etablissement, date):
        """
        Récupère tous les créneaux d'une date donnée
        """
        return cls.objects.filter(
            session_examen__etablissement=etablissement,
            date_examen=date,
            est_annule=False,
            actif=True
        ).select_related('session_examen', 'matiere', 'surveillant', 'salle').order_by('heure_debut')

