"""
Crée 10 professeurs pour l'établissement collège + lycée (id=1).
"""
import os
import random
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from django.db import transaction

from school_admin.controllers.professeur_controller import ProfesseurController
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.matiere_model import Matiere
from school_admin.model.professeur_model import Professeur

ETABLISSEMENT_ID = 1

PROFESSEURS = [
    {
        "nom": "Dupont",
        "prenom": "Marie",
        "email": "marie.dupont@lycee.com",
        "telephone": "+221771234501",
        "matiere": "Français",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Martin",
        "prenom": "Jean",
        "email": "jean.martin@lycee.com",
        "telephone": "+221771234502",
        "matiere": "Mathématiques",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Bernard",
        "prenom": "Sophie",
        "email": "sophie.bernard@lycee.com",
        "telephone": "+221771234503",
        "matiere": "Histoire-Géographie",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Petit",
        "prenom": "Thomas",
        "email": "lamine@gmail.com",
        "telephone": "+221771234504",
        "matiere": "Anglais LV1",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Robert",
        "prenom": "Claire",
        "email": "claire.robert@lycee.com",
        "telephone": "+221771234505",
        "matiere": "SVT",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Richard",
        "prenom": "Pierre",
        "email": "pierre.richard@lycee.com",
        "telephone": "+221771234506",
        "matiere": "Physique-Chimie",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Durand",
        "prenom": "Lucas",
        "email": "lucas.durand@lycee.com",
        "telephone": "+221771234507",
        "matiere": "EPS",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Moreau",
        "prenom": "Nathalie",
        "email": "nathalie.moreau@lycee.com",
        "telephone": "+221771234508",
        "matiere": "Arts plastiques",
        "niveau_enseignement": "college",
        "secondaires": ["Éducation musicale"],
    },
    {
        "nom": "Simon",
        "prenom": "Paul",
        "email": "paul.simon@lycee.com",
        "telephone": "+221771234509",
        "matiere": "Technologie",
        "niveau_enseignement": "college",
        "secondaires": [],
    },
    {
        "nom": "Laurent",
        "prenom": "Isabelle",
        "email": "isabelle.laurent@lycee.com",
        "telephone": "+221771234510",
        "matiere": "Philosophie",
        "niveau_enseignement": "lycee",
        "secondaires": ["SES", "Espagnol LV2"],
    },
]


def main():
    etab = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    matieres = {
        m.nom: m for m in Matiere.objects.filter(etablissement=etab)
    }
    created = []

    with transaction.atomic():
        for data in PROFESSEURS:
            if Professeur.objects.filter(email=data["email"]).exists():
                print(f"~ {data['prenom']} {data['nom']} deja existant ({data['email']})")
                continue

            matiere_principale = matieres.get(data["matiere"])
            if not matiere_principale:
                raise ValueError(f"Matiere introuvable: {data['matiere']}")

            matricule = ProfesseurController.generate_matricule_professeur(etab)
            mot_de_passe = "".join(str(random.randint(0, 9)) for _ in range(4))

            prof = Professeur(
                nom=data["nom"],
                prenom=data["prenom"],
                email=data["email"],
                telephone=data["telephone"],
                matiere_principale=matiere_principale,
                niveau_enseignement=data["niveau_enseignement"],
                numero_employe=matricule,
                username=matricule,
                etablissement=etab,
                mot_de_passe_provisoire=mot_de_passe,
                actif=True,
            )
            prof.set_password(mot_de_passe)
            prof.save()

            secondaires = [
                matieres[n] for n in data.get("secondaires", []) if n in matieres
            ]
            if secondaires:
                prof.matieres_secondaires.set(secondaires)

            created.append(
                {
                    "nom": prof.nom_complet,
                    "matricule": matricule,
                    "mdp": mot_de_passe,
                    "matiere": matiere_principale.nom,
                }
            )
            print(
                f"+ {prof.nom_complet} | {matiere_principale.nom} | "
                f"matricule={matricule} | mdp={mot_de_passe}"
            )

    total = Professeur.objects.filter(etablissement=etab).count()
    print(f"\nTermine : {len(created)} professeur(s) cree(s). Total : {total}")


if __name__ == "__main__":
    main()
