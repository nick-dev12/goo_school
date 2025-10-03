from django.core.management.base import BaseCommand
from school_admin.model.etablissement_model import Etablissement
import random
import string

class Command(BaseCommand):
    help = 'Génère des codes uniques pour tous les établissements existants'

    def generate_etablissement_code(self, type_etablissement):
        """
        Génère un code unique pour un établissement avec un préfixe basé sur le type
        """
        # Définir le préfixe en fonction du type d'établissement
        prefixes = {
            'primary': 'PRI-',
            'secondary': 'COL-',
            'highschool': 'LYC-'
        }
        
        prefix = prefixes.get(type_etablissement, 'ETB-')
        
        # Générer une partie numérique aléatoire (5 chiffres)
        numeric_part = ''.join(random.choices(string.digits, k=5))
        
        # Générer une partie alphabétique aléatoire (2 lettres majuscules)
        alpha_part = ''.join(random.choices(string.ascii_uppercase, k=2))
        
        # Combiner pour former le code complet
        code = f"{prefix}{numeric_part}{alpha_part}"
        
        return code

    def handle(self, *args, **options):
        # Récupérer tous les établissements
        etablissements = Etablissement.objects.all()
        
        self.stdout.write(f"Trouvé {etablissements.count()} établissements à mettre à jour.")
        
        # Générer un code unique pour chaque établissement
        for etablissement in etablissements:
            # Générer un code unique
            code = self.generate_etablissement_code(etablissement.type_etablissement)
            
            # Vérifier que le code est unique
            while Etablissement.objects.filter(code_etablissement=code).exists():
                code = self.generate_etablissement_code(etablissement.type_etablissement)
            
            # Assigner le code à l'établissement
            etablissement.code_etablissement = code
            etablissement.save()
            
            self.stdout.write(f"Établissement {etablissement.nom} mis à jour avec le code {code}")
        
        self.stdout.write(self.style.SUCCESS(f"Tous les établissements ont été mis à jour avec succès."))
