from django.db import models
from django.utils import timezone
from .compte_user import CompteUser


class NoteCommercial(models.Model):
    """
    Modèle pour les notes commerciales liées à un établissement
    """
    
    # On importe le modèle Prospection
    etablissement = models.ForeignKey(
        'school_admin.Prospection', # On importe le modèle Prospection
        on_delete=models.CASCADE, # On supprime la note si l'établissement est supprimé
        related_name='notes_commerciales', # On nomme la relation "notes_commerciales"
        verbose_name="Établissement" # On nomme le champ "Établissement"
    )
    # On crée le champ "contenu" de type texte
    contenu = models.TextField(verbose_name="Contenu de la note")
    # On crée le champ "date_creation" de type date et heure
    date_creation = models.DateTimeField(default=timezone.now, verbose_name="Date de création")
    # On crée le champ "cree_par" de type foreign key et on importe le modèle CompteUser
    cree_par = models.ForeignKey(
        CompteUser, # On importe le modèle CompteUser
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name="Créé par"
    )
    # On crée le champ "actif" de type booléen
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Note commerciale" # On nomme le modèle "Note commerciale"
        verbose_name_plural = "Notes commerciales" # On nomme le pluriel "Notes commerciales"
        ordering = ['-date_creation']

    def __str__(self):
        # On retourne la note du {date_creation} - {nom_etablissement}
        return f"Note du {self.date_creation.strftime('%d/%m/%Y')} - {self.etablissement.nom_etablissement}"
