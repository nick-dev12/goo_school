"""Inscrire 10 eleves par classe pour l'etablissement primaire Artisant."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

import django

django.setup()

from django.db import transaction
from django.utils import timezone

from school_admin.model.etablissement_model import Etablissement
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.parent_model import Parent
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.personal_views.secretaire_view import (
    _archiver_inscription_eleve_parent,
    formater_nom,
    formater_prenom,
)

NOMS = [
    "Mbarga", "Ngo", "Essomba", "Fouda", "Owona", "Atemkeng", "Biya", "Nkolo",
    "Mvondo", "Etoa", "Abega", "Bella", "Manga", "Ondo", "Zogo", "Tchoumi",
    "Kamga", "Djoumessi", "Fotso", "Kuete", "Ngono", "Meka", "Bengono", "Ebogo",
    "Ndongo", "Tchakounte", "Wamba", "Simo", "Fomekong", "Tchokouani",
    "Mbouda", "Ndjock", "Eloundou", "Messina", "Ayissi", "Nkeng", "Bikoi",
    "Ngalle", "Tabi", "Kemajou", "Nguema", "Eyenga", "Mba", "Ndengue",
    "Onana", "Bengono", "Assomo", "Nkou", "Ewodo", "Mballa",
]

PRENOMS_M = [
    "Jean", "Paul", "Serge", "David", "Eric", "Patrick", "Alain", "Bruno",
    "Christian", "Daniel", "Franck", "Gilles", "Herve", "Isaac", "Joel",
    "Kevin", "Lionel", "Martin", "Nicolas", "Olivier", "Philippe", "Roger",
    "Samuel", "Thierry", "Victor",
]

PRENOMS_F = [
    "Marie", "Claire", "Julie", "Amina", "Grace", "Sandrine", "Patricia",
    "Esther", "Ruth", "Sarah", "Diane", "Florence", "Helene", "Irene",
    "Jeanne", "Laure", "Michele", "Nadine", "Odile", "Pauline", "Rita",
    "Sophie", "Therese", "Ursule", "Valerie",
]

PRENOMS_PARENT = ["Joseph", "Pierre", "Antoine", "Henri", "Luc", "Marc", "Thomas", "Yves"]
PRENOMS_PARENT_F = ["Jeanne", "Marthe", "Therese", "Anne", "Cecile", "Francine", "Monique"]


def age_naissance_pour_classe(classe_nom: str, index: int) -> date:
    """Ages approximatifs primaire (CP ~6 ans ... CM2 ~11 ans)."""
    base_ages = {
        "CP A": 6,
        "CE1 A": 7,
        "CE2 A": 8,
        "CM1 A": 9,
        "CM2 A": 10,
    }
    age = base_ages.get(classe_nom, 8)
    # Decaler un peu pour diversifier
    jours = (index * 37) % 300
    return date.today().replace(year=date.today().year - age) - timedelta(days=jours)


def main():
    e = Etablissement.objects.get(email="oyonoeffe09@gmail.com")
    annee = AnneeScolaire.objects.filter(etablissement=e, est_active=True).first()
    if not annee:
        raise SystemExit("Aucune annee scolaire active")

    classes = list(
        Classe.objects.filter(etablissement=e, actif=True).order_by("nom")
    )
    order = ["CP A", "CE1 A", "CE2 A", "CM1 A", "CM2 A"]
    classes = sorted(classes, key=lambda c: order.index(c.nom) if c.nom in order else 99)

    today = date.today()
    created_total = 0
    name_idx = 0

    with transaction.atomic():
        for classe in classes:
            deja = Eleve.objects.filter(etablissement=e, classe=classe, actif=True).count()
            a_creer = max(0, 10 - deja)
            print(f"{classe.nom}: {deja} existants, creation de {a_creer}")
            for i in range(a_creer):
                sexe = "M" if (name_idx + i) % 2 == 0 else "F"
                nom = NOMS[name_idx % len(NOMS)]
                if sexe == "M":
                    prenom = PRENOMS_M[name_idx % len(PRENOMS_M)]
                    parent_lien = "pere"
                    parent_prenom = PRENOMS_PARENT[name_idx % len(PRENOMS_PARENT)]
                else:
                    prenom = PRENOMS_F[name_idx % len(PRENOMS_F)]
                    parent_lien = "mere"
                    parent_prenom = PRENOMS_PARENT_F[name_idx % len(PRENOMS_PARENT_F)]

                nom_f = formater_nom(nom)
                prenom_f = formater_prenom(prenom)
                parent_nom_f = formater_nom(nom)
                parent_prenom_f = formater_prenom(parent_prenom)

                matricule = Eleve.generer_matricule_eleve(e)
                mdp_eleve = Eleve.generer_mot_de_passe()
                matricule_parent = Parent.generer_matricule_parent(e)
                mdp_parent = Parent.generer_mot_de_passe()
                telephone = f"+2376{700000000 + name_idx:08d}"[-13:]
                # ensure unique-ish phone: +2376XXXXXXXX
                telephone = f"+2376{80000000 + name_idx:08d}"

                eleve = Eleve(
                    nom=nom_f,
                    prenom=prenom_f,
                    date_naissance=age_naissance_pour_classe(classe.nom, i),
                    lieu_naissance="Yaounde",
                    sexe=sexe,
                    nationalite="Camerounaise",
                    adresse=f"Quartier {classe.nom}, Yaounde",
                    numero_eleve=matricule,
                    matricule_eleve=matricule,
                    etablissement=e,
                    classe=classe,
                    date_inscription=today,
                    statut="nouvelle",
                    parent_nom=parent_nom_f,
                    parent_prenom=parent_prenom_f,
                    parent_telephone=telephone,
                    parent_adresse=f"Quartier {classe.nom}, Yaounde",
                    parent_profession="Commercant" if sexe == "F" else "Enseignant",
                    parent_lien=parent_lien,
                    mot_de_passe_provisoire=mdp_eleve,
                    mot_de_passe_eleve_modifie=False,
                    document_acte_naissance=True,
                    document_photo_identite=True,
                    document_autorisation_parentale=True,
                    username=matricule,
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                    actif=True,
                )
                eleve.set_password(mdp_eleve)
                eleve.save()

                parent = Parent(
                    matricule_parental=matricule_parent,
                    type_parent=parent_lien if parent_lien in ("mere", "pere", "tuteur") else "tuteur",
                    nom=parent_nom_f,
                    prenom=parent_prenom_f,
                    telephone=telephone,
                    email="",
                    adresse=f"Quartier {classe.nom}, Yaounde",
                    profession=eleve.parent_profession or "",
                    etablissement=e,
                    mot_de_passe_provisoire=mdp_parent,
                    mot_de_passe_modifie=False,
                    username=matricule_parent,
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
                parent.set_password(mdp_parent)
                parent.save()

                LienFamilial.objects.create(
                    parent=parent,
                    eleve=eleve,
                    type_lien=parent.type_parent,
                    statut="valide",
                    est_inscripteur=True,
                    actif=True,
                )

                _archiver_inscription_eleve_parent(
                    eleve=eleve,
                    parent=parent,
                    etablissement=e,
                    annee_scolaire=annee,
                    date_inscription=today,
                )

                if e.module_comptabilite:
                    try:
                        from school_admin.utils.comptabilite_utils import creer_frais_inscription

                        creer_frais_inscription(eleve, annee, "inscription")
                    except Exception as exc:
                        print(f"  [warn] frais inscription: {exc}")

                created_total += 1
                name_idx += 1
                print(
                    f"  OK {classe.nom} | {eleve.prenom} {eleve.nom} | "
                    f"{matricule} / {mdp_eleve} | parent {matricule_parent} / {mdp_parent}"
                )

            # si deja >= 10, avancer name_idx quand meme pour diversite globale
            if a_creer == 0:
                name_idx += 10

        e.date_derniere_facturation = timezone.now()
        e.save(update_fields=["date_derniere_facturation"])

    print("---")
    print(f"Total crees: {created_total}")
    for c in classes:
        n = Eleve.objects.filter(etablissement=e, classe=c, actif=True).count()
        print(f"  {c.nom}: {n} eleves")


if __name__ == "__main__":
    main()
