from django.db import models
from django.utils import timezone
from .matiere_model import Matiere
from .etablissement_model import Etablissement


class CoefficientMatiereGroupe(models.Model):
    """
    Modèle pour stocker le coefficient d'une matière par groupe de classes.
    Permet d'avoir des coefficients différents pour une même matière selon les groupes.
    Exemple: Mathématiques coefficient 6 pour le groupe "6eme", coefficient 4 pour le groupe "5eme".
    """
    
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name='coefficients_par_groupe',
        verbose_name="Matière"
    )
    
    etablissement = models.ForeignKey(
        Etablissement,
        on_delete=models.CASCADE,
        related_name='coefficients_matiere_groupe',
        verbose_name="Établissement"
    )
    
    nom_groupe = models.CharField(
        max_length=100,
        verbose_name="Nom du groupe de classes",
        help_text="Ex: '6eme', '5eme', 'Premiere L', etc."
    )
    
    coefficient = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=1.0,
        verbose_name="Coefficient",
        help_text="Coefficient de la matière pour ce groupe de classes"
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Coefficient Matière par Groupe"
        verbose_name_plural = "Coefficients Matière par Groupe"
        unique_together = ['matiere', 'etablissement', 'nom_groupe']
        ordering = ['matiere', 'nom_groupe']
        indexes = [
            models.Index(fields=['matiere', 'etablissement']),
            models.Index(fields=['nom_groupe']),
        ]
    
    def __str__(self):
        return f"{self.matiere.nom} - {self.nom_groupe} (coeff: {self.coefficient})"
    
    @classmethod
    def get_coefficient_for_classe(cls, matiere, classe):
        """
        Récupère le coefficient d'une matière pour une classe donnée.
        Détermine le groupe de la classe et retourne le coefficient correspondant.
        
        Args:
            matiere: Instance de Matiere
            classe: Instance de Classe
            
        Returns:
            Decimal: Le coefficient de la matière pour cette classe, ou le coefficient par défaut de la matière
        """
        import re
        
        # Extraire le nom du groupe depuis le nom de la classe
        # Ex: "6eme A" -> "6eme", "Premiere L1" -> "Premiere L"
        match = re.match(r'^(.+?)\s+([A-Z0-9]+)$', classe.nom)
        if match:
            nom_groupe = match.group(1).strip()
        else:
            nom_groupe = classe.nom
        
        # Chercher le coefficient pour ce groupe
        coefficient_obj = cls.objects.filter(
            matiere=matiere,
            etablissement=classe.etablissement,
            nom_groupe=nom_groupe
        ).first()
        
        if coefficient_obj:
            return coefficient_obj.coefficient
        
        # Si aucun coefficient spécifique trouvé, retourner le coefficient par défaut de la matière
        return matiere.coefficient

