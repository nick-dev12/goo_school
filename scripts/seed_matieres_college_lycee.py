"""
Crée les matières collège + lycée pour un établissement collège_lycée
et les relie aux classes avec coefficients par groupe.
"""
import os
import re
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from decimal import Decimal

from django.db import transaction

from school_admin.model.classe_model import Classe
from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere

ETABLISSEMENT_ID = 1

# Coefficients par nom de groupe (extrait du nom de classe, ex. « 6ème A » → « 6ème »)
MATIERES = [
    {
        "nom": "Français",
        "code": "FRA",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 3,
            "5ème": 3,
            "4ème": 3,
            "3ème": 3,
            "2nde": 2,
            "1ère": 2,
            "Terminale": 2,
        },
    },
    {
        "nom": "Mathématiques",
        "code": "MAT",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 3,
            "5ème": 3,
            "4ème": 3,
            "3ème": 3,
            "2nde": 3,
            "1ère": 3,
            "Terminale": 3,
        },
    },
    {
        "nom": "Histoire-Géographie",
        "code": "HIG",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 2,
            "5ème": 2,
            "4ème": 2,
            "3ème": 2,
            "2nde": 2,
            "1ère": 2,
            "Terminale": 2,
        },
    },
    {
        "nom": "Anglais LV1",
        "code": "ANG",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 2,
            "5ème": 2,
            "4ème": 2,
            "3ème": 2,
            "2nde": 2,
            "1ère": 2,
            "Terminale": 2,
        },
    },
    {
        "nom": "SVT",
        "code": "SVT",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 2,
            "5ème": 2,
            "4ème": 2,
            "3ème": 2,
            "2nde": 2,
            "1ère": 2,
            "Terminale": 2,
        },
    },
    {
        "nom": "Physique-Chimie",
        "code": "PHY",
        "type_matiere": "obligatoire",
        "niveau": "tous",
        "groupes": {
            "6ème": 1.5,
            "5ème": 2,
            "4ème": 2,
            "3ème": 2,
            "2nde": 2,
            "1ère": 2,
            "Terminale": 2,
        },
    },
    {
        "nom": "EPS",
        "code": "EPS",
        "type_matiere": "sport",
        "niveau": "tous",
        "groupes": {
            "6ème": 1,
            "5ème": 1,
            "4ème": 1,
            "3ème": 1,
            "2nde": 1,
            "1ère": 1,
            "Terminale": 1,
        },
    },
    {
        "nom": "Arts plastiques",
        "code": "ART",
        "type_matiere": "art",
        "niveau": "college",
        "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1},
    },
    {
        "nom": "Technologie",
        "code": "TEC",
        "type_matiere": "technique",
        "niveau": "college",
        "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1},
    },
    {
        "nom": "Éducation musicale",
        "code": "MUS",
        "type_matiere": "art",
        "niveau": "college",
        "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1},
    },
    {
        "nom": "Philosophie",
        "code": "PHI",
        "type_matiere": "obligatoire",
        "niveau": "lycee",
        "groupes": {"1ère": 2, "Terminale": 2},
    },
    {
        "nom": "SES",
        "code": "SES",
        "type_matiere": "obligatoire",
        "niveau": "lycee",
        "groupes": {"2nde": 1.5, "1ère": 2, "Terminale": 2},
    },
    {
        "nom": "Espagnol LV2",
        "code": "ESP",
        "type_matiere": "facultative",
        "niveau": "lycee",
        "groupes": {"2nde": 1.5, "1ère": 1.5, "Terminale": 1.5},
    },
]


def extract_groupe(classe_nom):
    match = re.match(r"^(.+?)\s+([A-Z0-9]+)$", classe_nom)
    if match:
        return match.group(1).strip()
    return classe_nom


def unique_code(base_code, etab):
    prefix = (etab.code_etablissement or "ETB")[:6].upper().replace("-", "")
    code = f"{prefix}-{base_code}"[:10]
    counter = 1
    candidate = code
    while Matiere.objects.filter(code=candidate).exists():
        suffix = str(counter)
        candidate = f"{code[: max(1, 10 - len(suffix))]}{suffix}"
        counter += 1
    return candidate


def classes_for_groupes(classes, groupes):
    selected = []
    for classe in classes:
        if extract_groupe(classe.nom) in groupes:
            selected.append(classe)
    return selected


def main():
    etab = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    classes = list(Classe.objects.filter(etablissement=etab).order_by("niveau", "nom"))
    if not classes:
        print("Aucune classe trouvée pour l'établissement.")
        return

    created = 0
    updated = 0

    with transaction.atomic():
        for data in MATIERES:
            groupes = data["groupes"]
            default_coef = Decimal(str(next(iter(groupes.values()))))
            code = unique_code(data["code"], etab)

            matiere, was_created = Matiere.objects.get_or_create(
                nom=data["nom"],
                etablissement=etab,
                department=None,
                defaults={
                    "code": code,
                    "type_matiere": data["type_matiere"],
                    "niveau": data["niveau"],
                    "coefficient": default_coef,
                    "actif": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
                matiere.type_matiere = data["type_matiere"]
                matiere.niveau = data["niveau"]
                matiere.coefficient = default_coef
                matiere.actif = True
                matiere.save()

            linked = classes_for_groupes(classes, groupes)
            matiere.classes.set(linked)

            for nom_groupe, coef in groupes.items():
                CoefficientMatiereGroupe.objects.update_or_create(
                    matiere=matiere,
                    etablissement=etab,
                    nom_groupe=nom_groupe,
                    defaults={"coefficient": Decimal(str(coef))},
                )

            print(
                f"{'+' if was_created else '~'} {matiere.nom} ({matiere.code}) "
                f"- {len(linked)} classe(s), {len(groupes)} groupe(s)"
            )

    total = Matiere.objects.filter(etablissement=etab).count()
    print(f"\nTerminé : {created} créée(s), {updated} mise(s) à jour. Total matières : {total}")


if __name__ == "__main__":
    main()
