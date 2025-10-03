import os
import django
import sys

# Configurer l'environnement Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

# Importer les modèles et contrôleurs après avoir configuré Django
from school_admin.controllers.etablissement_controller import EtablissementController

# Tester la génération de code pour différents types d'établissements
types = ['primary', 'secondary', 'highschool', 'unknown']

print("Test de génération de codes d'établissement :")
print("-" * 40)

for type_etab in types:
    code = EtablissementController.generate_etablissement_code(type_etab)
    print(f"Type: {type_etab:<10} -> Code généré: {code}")

print("-" * 40)
print("Test terminé avec succès.")
