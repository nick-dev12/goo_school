"""
Inscrit 10 eleves par classe pour l'etablissement collège + lycée (id=1).
Reproduit le flux d'inscription (Eleve, Parent, LienFamilial, archivage).
"""
import os
import sys
from datetime import date, timedelta

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from django.db import transaction

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.personal_views.secretaire_view import _archiver_inscription_eleve_parent
from school_admin.utils.formatting_utils import formater_nom, formater_prenom

ETABLISSEMENT_ID = 1
ELEVES_PAR_CLASSE = 10

PRENOMS_M = [
    "Amadou", "Ibrahima", "Moussa", "Ousmane", "Cheikh",
    "Mamadou", "Abdou", "Modou", "Pape", "Serigne",
]
PRENOMS_F = [
    "Fatou", "Aissatou", "Mariama", "Awa", "Khady",
    "Ndèye", "Coumba", "Bineta", "Sokhna", "Rokhaya",
]
NOMS = [
    "Diop", "Ndiaye", "Fall", "Sow", "Ba",
    "Gueye", "Sy", "Mbaye", "Cissé", "Faye",
]

# Annee de naissance moyenne par niveau (inscription 2026)
ANNEE_NAISSANCE = {
    "6ème": 2014,
    "5ème": 2013,
    "4ème": 2012,
    "3ème": 2011,
    "2nde": 2010,
    "1ère": 2009,
    "Terminale": 2008,
}


def extract_niveau(classe_nom):
    for key in ANNEE_NAISSANCE:
        if classe_nom.startswith(key):
            return key
    return "6ème"


def date_naissance_pour_classe(classe_nom, index):
    annee = ANNEE_NAISSANCE.get(extract_niveau(classe_nom), 2012)
    mois = (index % 12) + 1
    jour = (index % 27) + 1
    return date(annee, mois, jour)


def creer_eleve(classe, index, etab, annee, date_inscription):
    is_garcon = index % 2 == 0
    sexe = "M" if is_garcon else "F"
    prenom = (PRENOMS_M if is_garcon else PRENOMS_F)[index - 1]
    nom = NOMS[(index - 1) % len(NOMS)]
    prenom = formater_prenom(prenom)
    nom = formater_nom(nom)

    matricule = Eleve.generer_matricule_eleve(etab)
    mdp_eleve = Eleve.generer_mot_de_passe()
    parent_lien = "pere" if is_garcon else "mere"

    parent_nom = formater_nom(f"Parent {nom}")
    parent_prenom = formater_prenom("Famille")
    parent_tel = f"+22177{classe.id:02d}{index:02d}0001"[-13:]
    if Parent.objects.filter(telephone=parent_tel, etablissement=etab).exists():
        parent_tel = f"+22178{classe.id:02d}{index:02d}0002"[-13:]

    matricule_parent = Parent.generer_matricule_parent(etab)
    mdp_parent = Parent.generer_mot_de_passe()

    eleve = Eleve(
        nom=nom,
        prenom=prenom,
        date_naissance=date_naissance_pour_classe(classe.nom, index),
        lieu_naissance="Dakar",
        sexe=sexe,
        nationalite="Sénégalaise",
        adresse=f"Quartier {classe.nom}, Dakar",
        numero_eleve=matricule,
        matricule_eleve=matricule,
        etablissement=etab,
        classe=classe,
        date_inscription=date_inscription,
        statut="nouvelle",
        parent_nom=parent_nom,
        parent_prenom=parent_prenom,
        parent_telephone=parent_tel,
        parent_adresse=f"Quartier {classe.nom}, Dakar",
        parent_profession="Commerçant",
        parent_lien=parent_lien,
        mot_de_passe_provisoire=mdp_eleve,
        mot_de_passe_eleve_modifie=False,
        document_acte_naissance=True,
        document_photo_identite=True,
        username=matricule,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    eleve.set_password(mdp_eleve)
    eleve.save()

    parent = Parent(
        matricule_parental=matricule_parent,
        type_parent=parent_lien,
        nom=parent_nom,
        prenom=parent_prenom,
        telephone=parent_tel,
        email="",
        adresse=f"Quartier {classe.nom}, Dakar",
        profession="Commerçant",
        etablissement=etab,
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
        type_lien=parent_lien,
        statut="valide",
        est_inscripteur=True,
        actif=True,
    )

    _archiver_inscription_eleve_parent(
        eleve=eleve,
        parent=parent,
        etablissement=etab,
        annee_scolaire=annee,
        date_inscription=date_inscription,
    )

    if etab.module_comptabilite:
        try:
            from school_admin.utils.comptabilite_utils import creer_frais_inscription
            creer_frais_inscription(eleve, annee, "inscription")
        except Exception:
            pass

    return eleve


def main():
    etab = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    annee = AnneeScolaire.get_session_active(etab)
    if not annee:
        print("Aucune annee scolaire active.")
        return

    classes = list(
        Classe.objects.filter(etablissement=etab, actif=True).order_by("niveau", "nom")
    )
    date_inscription = date.today()
    total = 0

    with transaction.atomic():
        for classe in classes:
            for i in range(1, ELEVES_PAR_CLASSE + 1):
                if classe.places_disponibles <= 0:
                    print(f"Classe {classe.nom} pleine, arret.")
                    break
                creer_eleve(classe, i, etab, annee, date_inscription)
                total += 1
            nb = Eleve.objects.filter(classe=classe, actif=True).count()
            print(f"+ {classe.nom} : {nb} eleve(s)")

    print(f"\nTermine : {total} eleve(s) inscrit(s) pour {len(classes)} classes.")
    print(f"Total etablissement : {Eleve.objects.filter(etablissement=etab, actif=True).count()}")


if __name__ == "__main__":
    main()
