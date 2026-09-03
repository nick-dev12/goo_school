"""
Crée les affectations professeur-classe-matière pour l'établissement collège + lycée.
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from django.core.exceptions import ValidationError
from django.db import transaction

from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.professeur_model import Professeur

ETABLISSEMENT_ID = 1


def matieres_enseignables(professeur):
    matieres = []
    if professeur.matiere_principale_id:
        matieres.append(professeur.matiere_principale)
    matieres.extend(list(professeur.matieres_secondaires.all()))
    seen = set()
    unique = []
    for m in matieres:
        if m.id not in seen:
            seen.add(m.id)
            unique.append(m)
    return unique


def main():
    etab = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    annee = AnneeScolaire.get_session_active(etab)
    if not annee:
        print("Aucune annee scolaire active. Creez-en une avant les affectations.")
        return

    professeurs = Professeur.objects.filter(etablissement=etab, actif=True).select_related(
        "matiere_principale"
    ).prefetch_related("matieres_secondaires", "matieres_secondaires__classes")

    created = 0
    skipped = 0
    errors = []

    with transaction.atomic():
        for prof in professeurs:
            for matiere in matieres_enseignables(prof):
                classes = matiere.classes.filter(etablissement=etab, actif=True).order_by("niveau", "nom")
                for classe in classes:
                    exists = AffectationProfesseur.objects.filter(
                        professeur=prof,
                        classe=classe,
                        matiere=matiere,
                        annee_scolaire=annee,
                    ).exists()
                    if exists:
                        skipped += 1
                        continue

                    affectation = AffectationProfesseur(
                        professeur=prof,
                        classe=classe,
                        matiere=matiere,
                        annee_scolaire=annee,
                        statut="classique",
                        actif=True,
                    )
                    try:
                        affectation.save()
                        created += 1
                    except ValidationError as exc:
                        errors.append(
                            f"{prof.nom_complet} / {matiere.nom} / {classe.nom}: {exc.messages}"
                        )

    total = AffectationProfesseur.objects.filter(
        professeur__etablissement=etab,
        annee_scolaire=annee,
        actif=True,
    ).count()

    print(f"Annee scolaire active : {annee.libelle}")
    print(f"Affectations creees : {created}")
    print(f"Affectations deja existantes (ignorees) : {skipped}")
    print(f"Total affectations actives : {total}")

    if errors:
        print(f"\nErreurs ({len(errors)}) :")
        for err in errors[:20]:
            print(f"  - {err}")

    print("\nDetail par professeur :")
    for prof in professeurs.order_by("nom", "prenom"):
        nb = prof.affectations.filter(annee_scolaire=annee, actif=True).count()
        matieres = ", ".join(m.nom for m in matieres_enseignables(prof))
        print(f"  {prof.nom_complet} ({matieres}) : {nb} affectation(s)")


if __name__ == "__main__":
    main()
