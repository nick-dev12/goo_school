#!/usr/bin/env python
"""
Crée 3 établissements de démonstration marketing (sans envoi d'email)
et les peuple : session, périodes, classes, matières, professeurs, élèves.

Usage (VPS) :
  cd /home/nick/aria/goo_school
  ./venv/bin/python scripts/seed_ecoles_marketing_taysir.py
"""
from __future__ import annotations

import os
import random
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from django.db import transaction

from school_admin.controllers.classe_controller import ClasseController
from school_admin.controllers.etablissement_controller import EtablissementController
from school_admin.controllers.professeur_controller import ProfesseurController
from school_admin.model.academic_structure_model import AcademicCycle, AcademicLevel, Department
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.coefficient_matiere_groupe_model import CoefficientMatiereGroupe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.matiere_model import Matiere
from school_admin.model.module_model import Module, ModuleClasse, ModuleDepartment
from school_admin.model.parent_model import Parent
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.professeur_model import Professeur
from school_admin.model.salle_model import Salle
from school_admin.personal_views.secretaire_view import _archiver_inscription_eleve_parent
from school_admin.utils.formatting_utils import formater_nom, formater_prenom

SITE = "https://aria-edu.com"
CONNEXION = f"{SITE}/connexion/"
LIBELLE_ANNEE = "2026-2027"
ANNEE_DEBUT = 2026
ELEVES_PAR_CLASSE = 8
MDP_PROF = "TaysirP26@"  # max 10 car. (mot_de_passe_provisoire)

PRENOMS_M = [
    "Amadou", "Ibrahim", "Moussa", "Jean", "Paul", "Marc", "David", "Kevin",
    "Samuel", "Joseph", "Daniel", "Pierre",
]
PRENOMS_F = [
    "Fatou", "Amina", "Mariama", "Sophie", "Claire", "Julie", "Sarah", "Aïcha",
    "Nadia", "Laura", "Esther", "Chantal",
]
NOMS = [
    "Njoya", "Bello", "Tchaté", "Mbarga", "Owona", "Essomba", "Fouda", "Atangana",
    "Ngono", "Mekongo", "Abega", "Biya", "Onana", "Etoa", "Kamga",
]
LIEUX = ["Yaoundé", "Douala", "Bafoussam", "Garoua", "Bamenda"]

PHONE = {"n": 690200000}


def next_phone() -> str:
    PHONE["n"] += 1
    return f"6{PHONE['n']}"[-9:]


def unique_matiere_code(base: str, etab: Etablissement) -> str:
    prefix = (etab.code_etablissement or "ETB")[:5].upper().replace("-", "")
    code = f"{prefix}{base}"[:10]
    candidate = code
    n = 1
    while Matiere.objects.filter(code=candidate).exists():
        suffix = str(n)
        candidate = f"{code[: max(1, 10 - len(suffix))]}{suffix}"
        n += 1
    return candidate


def extract_groupe(classe_nom: str) -> str:
    match = re.match(r"^(.+?)\s+([A-Z0-9]+)$", classe_nom)
    if match:
        return match.group(1).strip()
    return classe_nom


def activer_modules(etab: Etablissement) -> None:
    fields = {
        "module_gestion_eleves": True,
        "module_notes_evaluations": True,
        "module_emploi_temps": True,
        "module_gestion_personnel": True,
        "module_comptabilite": True,
        "module_censeurs": True,
        "module_communication": True,
        "module_surveillance": True,
        "module_orientation": True,
        "module_formation": True,
        "module_bibliotheque": True,
        "module_activites": True,
        "statut_reglementation": "en_regle",
        "statut_paiement": "paye",
        "conditions_acceptees": True,
        "actif": True,
    }
    for k, v in fields.items():
        setattr(etab, k, v)
    etab.save(update_fields=list(fields.keys()))


def creer_etablissement(cfg: dict) -> tuple[Etablissement, str, bool]:
    existing = Etablissement.objects.filter(nom__iexact=cfg["nom"]).first()
    if existing:
        activer_modules(existing)
        return existing, "(déjà existant — mot de passe inchangé)", False

    code = EtablissementController.generate_etablissement_code(cfg["type"])
    etab = Etablissement(
        code_etablissement=code,
        nom=cfg["nom"],
        adresse=cfg["adresse"],
        pays="Cameroun",
        ville="Yaoundé",
        email=cfg["email_etab"],
        telephone=cfg["tel"],
        type_etablissement=cfg["type"],
        devise_monnaie="XOF",
        directeur_prenom=cfg["dir_prenom"],
        directeur_nom=cfg["dir_nom"],
        directeur_email=cfg["email_dir"],
        directeur_telephone=cfg["tel_dir"],
        username=cfg["email_dir"],
        type_facturation="mensuel",
        montant_par_eleve=Decimal("3000.00"),
        type_etablissement_comptabilite="prive",
        montant_frais_inscription=Decimal(str(cfg["inscription"])),
        montant_mensualite=Decimal(str(cfg["mensualite"])),
        statut_reglementation="en_regle",
        statut_paiement="paye",
        conditions_acceptees=True,
        actif=True,
    )
    etab.set_password(cfg["mdp"])
    etab.save()
    activer_modules(etab)
    return etab, cfg["mdp"], True


def ensure_annee(etab: Etablissement) -> AnneeScolaire:
    annee, _ = AnneeScolaire.objects.get_or_create(
        etablissement=etab,
        libelle=LIBELLE_ANNEE,
        defaults={
            "annee_debut": ANNEE_DEBUT,
            "annee_fin": ANNEE_DEBUT + 1,
            "date_debut": date(ANNEE_DEBUT, 9, 1),
            "date_fin": date(ANNEE_DEBUT + 1, 6, 30),
            "est_active": True,
            "est_ouverte": True,
        },
    )
    AnneeScolaire.objects.filter(etablissement=etab).exclude(pk=annee.pk).update(est_active=False)
    if not annee.est_active or not annee.est_ouverte:
        annee.est_active = True
        annee.est_ouverte = True
        annee.save(update_fields=["est_active", "est_ouverte"])
    return annee


def ensure_periodes_trimestres(etab: Etablissement, annee: AnneeScolaire) -> None:
    periodes = [
        ("1er Trimestre", date(2026, 9, 1), date(2026, 12, 15), True),
        ("2e Trimestre", date(2027, 1, 5), date(2027, 3, 31), False),
        ("3e Trimestre", date(2027, 4, 6), date(2027, 6, 30), False),
    ]
    for nom, d1, d2, active in periodes:
        PeriodeScolaire.objects.get_or_create(
            etablissement=etab,
            nom_periode=nom,
            annee_scolaire=annee.libelle,
            defaults={
                "type_periode": "trimestre",
                "date_debut": d1,
                "date_fin": d2,
                "annee_scolaire_fk": annee,
                "est_active": active,
                "niveau_lmd": "",
            },
        )


def ensure_periodes_lmd(etab: Etablissement, annee: AnneeScolaire) -> dict:
    mapping = {
        "L1": [("Semestre 1", date(2026, 9, 1), date(2027, 1, 31), True),
               ("Semestre 2", date(2027, 2, 1), date(2027, 6, 30), False)],
        "L2": [("Semestre 3", date(2026, 9, 1), date(2027, 1, 31), True),
               ("Semestre 4", date(2027, 2, 1), date(2027, 6, 30), False)],
        "L3": [("Semestre 5", date(2026, 9, 1), date(2027, 1, 31), True),
               ("Semestre 6", date(2027, 2, 1), date(2027, 6, 30), False)],
    }
    out = {}
    for niveau, items in mapping.items():
        out[niveau] = []
        for nom, d1, d2, active in items:
            p, _ = PeriodeScolaire.objects.get_or_create(
                etablissement=etab,
                nom_periode=nom,
                niveau_lmd=niveau,
                annee_scolaire=annee.libelle,
                defaults={
                    "type_periode": "semestre",
                    "date_debut": d1,
                    "date_fin": d2,
                    "annee_scolaire_fk": annee,
                    "est_active": active,
                },
            )
            out[niveau].append(p)
    return out


def ensure_classe(etab, nom, niveau, **extra) -> Classe:
    existing = Classe.objects.filter(etablissement=etab, nom=nom, actif=True).first()
    if existing:
        return existing
    code = ClasseController.generate_code_classe(nom, niveau, etab, extra.get("niveau_lmd"))
    return Classe.objects.create(
        nom=nom,
        niveau=niveau,
        code_classe=code,
        capacite_max=40,
        etablissement=etab,
        actif=True,
        **extra,
    )


def ensure_salles(etab: Etablissement, noms: list[tuple[str, str, str]]) -> None:
    for nom, numero, typ in noms:
        Salle.objects.get_or_create(
            etablissement=etab,
            numero=numero,
            defaults={"nom": nom, "type_salle": typ, "capacite_max": 40, "etat": "disponible", "actif": True},
        )


def ensure_matiere(etab, nom, base_code, **kwargs) -> Matiere:
    qs = Matiere.objects.filter(etablissement=etab, nom=nom)
    if kwargs.get("department"):
        qs = qs.filter(department=kwargs["department"])
    if kwargs.get("module"):
        qs = qs.filter(module=kwargs["module"])
    existing = qs.first()
    if existing:
        return existing
    return Matiere.objects.create(
        nom=nom,
        code=unique_matiere_code(base_code, etab),
        etablissement=etab,
        type_matiere=kwargs.get("type_matiere", "obligatoire"),
        niveau=kwargs.get("niveau", "tous"),
        coefficient=Decimal(str(kwargs.get("coefficient", 1))),
        credits=Decimal(str(kwargs.get("credits", 0))),
        department=kwargs.get("department"),
        module=kwargs.get("module"),
        niveau_lmd_key=kwargs.get("niveau_lmd_key", ""),
        actif=True,
    )


def creer_prof(etab, nom, prenom, email, matiere, niveau, tel=None) -> tuple[Professeur, str]:
    existing = Professeur.objects.filter(etablissement=etab, email=email).first()
    if existing:
        return existing, existing.mot_de_passe_provisoire or MDP_PROF
    matricule = ProfesseurController.generate_matricule_professeur(etab)
    prof = Professeur(
        nom=nom,
        prenom=prenom,
        sexe="F" if prenom in PRENOMS_F else "M",
        email=email,
        telephone=tel or next_phone(),
        matiere_principale=matiere,
        niveau_enseignement=niveau,
        numero_employe=matricule,
        username=matricule,
        etablissement=etab,
        mot_de_passe_provisoire=MDP_PROF,
        actif=True,
        conditions_acceptees=True,
        date_embauche=date(2024, 9, 1),
        prix_volume_horaire=Decimal("3500.00"),
    )
    prof.set_password(MDP_PROF)
    prof.save()
    return prof, MDP_PROF


def affecter(prof, classe, matiere, annee, principal=False) -> None:
    from django.core.exceptions import ValidationError

    exists = AffectationProfesseur.objects.filter(
        professeur=prof, classe=classe, matiere=matiere, annee_scolaire=annee
    ).exists()
    if not exists:
        affectation = AffectationProfesseur(
            professeur=prof,
            classe=classe,
            matiere=matiere,
            annee_scolaire=annee,
            statut="principal" if principal else "classique",
            actif=True,
        )
        try:
            affectation.save()
        except ValidationError:
            return
    prof.classes.add(classe)


def annee_naissance_niveau(nom_classe: str, type_etab: str) -> int:
    table_pri = {"SIL": 2019, "CP": 2018, "CE1": 2017, "CE2": 2016, "CM1": 2015, "CM2": 2014}
    table_col = {
        "6ème": 2014, "5ème": 2013, "4ème": 2012, "3ème": 2011,
        "2nde": 2010, "1ère": 2009, "Terminale": 2008,
    }
    table_sup = {"L1": 2007, "L2": 2006, "L3": 2005}
    for key, year in {**table_pri, **table_col, **table_sup}.items():
        if nom_classe.startswith(key) or key in nom_classe:
            return year
    if type_etab == "primary":
        return 2016
    if type_etab == "superieur":
        return 2006
    return 2011


def creer_eleves(etab, classe, annee, n, report) -> None:
    existing = Eleve.objects.filter(classe=classe, actif=True).count()
    to_create = max(0, n - existing)
    seq = Eleve.objects.filter(etablissement=etab).count()
    for i in range(to_create):
        seq += 1
        index = existing + i
        sexe = "M" if index % 2 == 0 else "F"
        prenom = formater_prenom((PRENOMS_M if sexe == "M" else PRENOMS_F)[index % 12])
        nom = formater_nom(NOMS[(index + seq) % len(NOMS)])
        matricule = Eleve.generer_matricule_eleve(etab)
        mdp = Eleve.generer_mot_de_passe()
        annee_n = annee_naissance_niveau(classe.nom, etab.type_etablissement)
        naissance = date(annee_n, (index % 12) + 1, (index % 27) + 1)
        parent_tel = next_phone()
        eleve = Eleve(
            username=matricule,
            matricule_eleve=matricule,
            numero_eleve=matricule,
            nom=nom,
            prenom=prenom,
            date_naissance=naissance,
            lieu_naissance=random.choice(LIEUX),
            sexe=sexe,
            nationalite="Camerounaise",
            etablissement=etab,
            classe=classe,
            date_inscription=date(2026, 9, 2),
            statut="nouvelle",
            parent_nom=f"Parent {nom}",
            parent_prenom="Tuteur" if sexe == "M" else "Tutrice",
            parent_telephone=parent_tel,
            parent_lien="pere" if sexe == "M" else "mere",
            mot_de_passe_provisoire=mdp,
            mot_de_passe_eleve_modifie=False,
            is_active=True,
            actif=True,
        )
        eleve.set_password(mdp)
        eleve.save()

        matricule_p = Parent.generer_matricule_parent(etab)
        mdp_p = Parent.generer_mot_de_passe() if hasattr(Parent, "generer_mot_de_passe") else mdp
        parent = Parent(
            matricule_parental=matricule_p,
            type_parent="pere" if sexe == "M" else "mere",
            nom=eleve.parent_nom,
            prenom=eleve.parent_prenom,
            telephone=parent_tel,
            email="",
            adresse="Yaoundé",
            profession="Commerçant",
            etablissement=etab,
            mot_de_passe_provisoire=mdp_p,
            mot_de_passe_modifie=False,
            username=matricule_p,
            is_active=True,
        )
        parent.set_password(mdp_p)
        parent.save()
        LienFamilial.objects.create(
            parent=parent,
            eleve=eleve,
            type_lien=eleve.parent_lien,
            statut="valide",
            est_inscripteur=True,
            actif=True,
        )
        _archiver_inscription_eleve_parent(
            eleve=eleve,
            parent=parent,
            etablissement=etab,
            annee_scolaire=annee,
            date_inscription=eleve.date_inscription,
        )
        if len(report["eleves_exemples"]) < 4:
            report["eleves_exemples"].append(
                {
                    "eleve": eleve.nom_complet,
                    "classe": classe.nom,
                    "matricule": matricule,
                    "mdp": mdp,
                    "parent": matricule_p,
                    "mdp_parent": mdp_p,
                }
            )


# ---------------------------------------------------------------------------
# Primaire
# ---------------------------------------------------------------------------
def seed_primaire(etab, annee, report) -> None:
    ensure_periodes_trimestres(etab, annee)
    ensure_salles(etab, [
        ("Salle SIL", "P01", "classe"),
        ("Salle CP", "P02", "classe"),
        ("Salle CE1", "P03", "classe"),
        ("Salle CE2", "P04", "classe"),
        ("Salle CM1", "P05", "classe"),
        ("Salle CM2", "P06", "classe"),
        ("Cour / EPS", "P10", "salle_sport"),
    ])
    noms = ["SIL A", "CP A", "CE1 A", "CE2 A", "CM1 A", "CM2 A"]
    classes = [ensure_classe(etab, n, "primaire") for n in noms]

    matieres_def = [
        ("Français", "FRA", 3),
        ("Mathématiques", "MAT", 3),
        ("Anglais", "ANG", 2),
        ("ECM", "ECM", 1),
        ("Sciences", "SCI", 2),
        ("EPS", "EPS", 1),
        ("Arts plastiques", "ART", 1),
    ]
    matieres = {}
    for nom, code, coef in matieres_def:
        m = ensure_matiere(etab, nom, code, niveau="primaire", coefficient=coef)
        m.classes.set(classes)
        matieres[nom] = m
        for cl in classes:
            CoefficientMatiereGroupe.objects.update_or_create(
                matiere=m, etablissement=etab, nom_groupe=extract_groupe(cl.nom),
                defaults={"coefficient": Decimal(str(coef))},
            )

    profs_data = [
        ("Bello", "Fatima", "fatima.bello.taysir@taysir-demo.cm", "Français", 0),
        ("Owona", "Paul", "paul.owona.taysir@taysir-demo.cm", "Français", 1),
        ("Njoya", "Amina", "amina.njoya.taysir@taysir-demo.cm", "Français", 2),
        ("Mbarga", "Jean", "jean.mbarga.taysir@taysir-demo.cm", "Français", 3),
        ("Essomba", "Claire", "claire.essomba.taysir@taysir-demo.cm", "Français", 4),
        ("Fouda", "Marc", "marc.fouda.taysir@taysir-demo.cm", "Français", 5),
        ("Atangana", "Sophie", "sophie.atangana.taysir@taysir-demo.cm", "Mathématiques", None),
        ("Ngono", "David", "david.ngono.taysir@taysir-demo.cm", "EPS", None),
    ]
    for nom, prenom, email, mat_nom, idx_classe in profs_data:
        prof, mdp = creer_prof(etab, nom, prenom, email, matieres[mat_nom], "primaire")
        report["profs"].append({"nom": f"{prenom} {nom}", "matricule": prof.numero_employe, "mdp": mdp, "matiere": mat_nom})
        if idx_classe is not None:
            cl = classes[idx_classe]
            secondaires = [matieres[n] for n in ("Anglais", "ECM", "Sciences", "Arts plastiques")]
            prof.matieres_secondaires.set(secondaires)
            affecter(prof, cl, matieres["Français"], annee, principal=True)
            for mnom in ("Anglais", "ECM", "Sciences", "Arts plastiques"):
                affecter(prof, cl, matieres[mnom], annee)
        elif mat_nom == "Mathématiques":
            for cl in classes:
                affecter(prof, cl, matieres["Mathématiques"], annee)
        elif mat_nom == "EPS":
            for cl in classes:
                affecter(prof, cl, matieres["EPS"], annee)

    for cl in classes:
        creer_eleves(etab, cl, annee, ELEVES_PAR_CLASSE, report)
    report["classes"] = [c.nom for c in classes]
    report["n_matieres"] = len(matieres)


# ---------------------------------------------------------------------------
# Collège + lycée
# ---------------------------------------------------------------------------
MATIERES_COL = [
    {"nom": "Français", "code": "FRA", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 3, "5ème": 3, "4ème": 3, "3ème": 3, "2nde": 2, "1ère": 2, "Terminale": 2}},
    {"nom": "Mathématiques", "code": "MAT", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 3, "5ème": 3, "4ème": 3, "3ème": 3, "2nde": 3, "1ère": 3, "Terminale": 3}},
    {"nom": "Histoire-Géographie", "code": "HIG", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 2, "5ème": 2, "4ème": 2, "3ème": 2, "2nde": 2, "1ère": 2, "Terminale": 2}},
    {"nom": "Anglais LV1", "code": "ANG", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 2, "5ème": 2, "4ème": 2, "3ème": 2, "2nde": 2, "1ère": 2, "Terminale": 2}},
    {"nom": "SVT", "code": "SVT", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 2, "5ème": 2, "4ème": 2, "3ème": 2, "2nde": 2, "1ère": 2, "Terminale": 2}},
    {"nom": "Physique-Chimie", "code": "PHY", "type": "obligatoire", "niveau": "tous",
     "groupes": {"6ème": 1.5, "5ème": 2, "4ème": 2, "3ème": 2, "2nde": 2, "1ère": 2, "Terminale": 2}},
    {"nom": "EPS", "code": "EPS", "type": "sport", "niveau": "tous",
     "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1, "2nde": 1, "1ère": 1, "Terminale": 1}},
    {"nom": "Arts plastiques", "code": "ART", "type": "art", "niveau": "college",
     "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1}},
    {"nom": "Technologie", "code": "TEC", "type": "technique", "niveau": "college",
     "groupes": {"6ème": 1, "5ème": 1, "4ème": 1, "3ème": 1}},
    {"nom": "Philosophie", "code": "PHI", "type": "obligatoire", "niveau": "lycee",
     "groupes": {"1ère": 2, "Terminale": 2}},
    {"nom": "SES", "code": "SES", "type": "obligatoire", "niveau": "lycee",
     "groupes": {"2nde": 1.5, "1ère": 2, "Terminale": 2}},
    {"nom": "Espagnol LV2", "code": "ESP", "type": "facultative", "niveau": "lycee",
     "groupes": {"2nde": 1.5, "1ère": 1.5, "Terminale": 1.5}},
]


def seed_college(etab, annee, report) -> None:
    ensure_periodes_trimestres(etab, annee)
    ensure_salles(etab, [
        ("Salle 6ème", "C01", "classe"), ("Salle 5ème", "C02", "classe"),
        ("Salle 4ème", "C03", "classe"), ("Salle 3ème", "C04", "classe"),
        ("Salle 2nde", "L01", "classe"), ("Salle 1ère C", "L02", "classe"),
        ("Salle Tle C", "L03", "classe"), ("Labo SVT", "LAB1", "laboratoire"),
        ("Labo PC", "LAB2", "laboratoire"), ("Info", "INF1", "salle_informatique"),
    ])
    specs = [
        ("6ème A", "college"), ("5ème A", "college"), ("4ème A", "college"), ("3ème A", "college"),
        ("2nde A", "lycee"), ("1ère C", "lycee"), ("1ère D", "lycee"),
        ("Terminale C", "lycee"), ("Terminale D", "lycee"),
    ]
    classes = [ensure_classe(etab, nom, niv) for nom, niv in specs]
    by_groupe = {}
    for cl in classes:
        by_groupe.setdefault(extract_groupe(cl.nom), []).append(cl)

    matieres = {}
    for data in MATIERES_COL:
        m = ensure_matiere(
            etab, data["nom"], data["code"],
            type_matiere=data["type"], niveau=data["niveau"],
            coefficient=list(data["groupes"].values())[0],
        )
        linked = []
        for g, coef in data["groupes"].items():
            linked.extend(by_groupe.get(g, []))
            CoefficientMatiereGroupe.objects.update_or_create(
                matiere=m, etablissement=etab, nom_groupe=g,
                defaults={"coefficient": Decimal(str(coef))},
            )
        m.classes.set(linked)
        matieres[data["nom"]] = m

    profs = [
        ("Dupont", "Marie", "marie.dupont.edutaysir@taysir-demo.cm", "Français", "college"),
        ("Martin", "Jean", "jean.martin.edutaysir@taysir-demo.cm", "Mathématiques", "college"),
        ("Bernard", "Sophie", "sophie.bernard.edutaysir@taysir-demo.cm", "Histoire-Géographie", "college"),
        ("Petit", "Thomas", "thomas.petit.edutaysir@taysir-demo.cm", "Anglais LV1", "college"),
        ("Robert", "Claire", "claire.robert.edutaysir@taysir-demo.cm", "SVT", "college"),
        ("Richard", "Pierre", "pierre.richard.edutaysir@taysir-demo.cm", "Physique-Chimie", "college"),
        ("Durand", "Lucas", "lucas.durand.edutaysir@taysir-demo.cm", "EPS", "college"),
        ("Moreau", "Nathalie", "nathalie.moreau.edutaysir@taysir-demo.cm", "Arts plastiques", "college"),
        ("Simon", "Paul", "paul.simon.edutaysir@taysir-demo.cm", "Technologie", "college"),
        ("Laurent", "Isabelle", "isabelle.laurent.edutaysir@taysir-demo.cm", "Philosophie", "lycee"),
        ("Camara", "Alain", "alain.camara.edutaysir@taysir-demo.cm", "SES", "lycee"),
        ("Traore", "Léa", "lea.traore.edutaysir@taysir-demo.cm", "Espagnol LV2", "lycee"),
    ]
    for nom, prenom, email, mat_nom, niv in profs:
        prof, mdp = creer_prof(etab, nom, prenom, email, matieres[mat_nom], niv)
        report["profs"].append({"nom": f"{prenom} {nom}", "matricule": prof.numero_employe, "mdp": mdp, "matiere": mat_nom})
        for cl in matieres[mat_nom].classes.filter(etablissement=etab, actif=True):
            principal = mat_nom == "Français" and cl.nom == "6ème A"
            affecter(prof, cl, matieres[mat_nom], annee, principal=principal)

    for cl in classes:
        creer_eleves(etab, cl, annee, ELEVES_PAR_CLASSE, report)
    report["classes"] = [c.nom for c in classes]
    report["n_matieres"] = len(matieres)


# ---------------------------------------------------------------------------
# Supérieur
# ---------------------------------------------------------------------------
def seed_superieur(etab, annee, report) -> None:
    periodes = ensure_periodes_lmd(etab, annee)
    cycle, _ = AcademicCycle.objects.get_or_create(
        etablissement=etab, code="L",
        defaults={"nom": "Licence", "ordre": 1},
    )
    levels = {}
    for i, code in enumerate(["L1", "L2", "L3"], start=1):
        levels[code], _ = AcademicLevel.objects.get_or_create(
            cycle=cycle, code=code,
            defaults={"nom": f"Licence {code[-1]}", "ordre": i},
        )

    deps = {}
    for ordre, (nom, sigle, domaine, mention) in enumerate([
        ("Droit", "DRT", "Sciences juridiques", "Droit privé et public"),
        ("Gestion", "GES", "Sciences de gestion", "Management et finance"),
    ], start=1):
        deps[sigle], _ = Department.objects.get_or_create(
            etablissement=etab, nom=nom,
            defaults={"sigle": sigle, "domaine": domaine, "mention": mention, "ordre": ordre},
        )

    ensure_salles(etab, [
        ("Amphi A", "AMPHA", "amphitheatre"),
        ("Salle DRT L1", "S101", "classe"),
        ("Salle DRT L2", "S102", "classe"),
        ("Salle GES L1", "S201", "classe"),
        ("Salle GES L2", "S202", "classe"),
        ("Salle info", "INF01", "salle_informatique"),
    ])

    classes = {}
    for sigle, dep in deps.items():
        for niv in ("L1", "L2", "L3"):
            nom = f"{sigle} {niv} A"
            classes[(sigle, niv)] = ensure_classe(
                etab, nom, "superieur",
                academic_level=levels[niv],
                department=dep,
                niveau_lmd=niv,
            )

    # Modules + matières par filière / niveau
    catalogue = {
        ("DRT", "L1"): [
            ("Fondements du droit", "M-DRT-L1-1", [
                ("Introduction au droit", "IDR", 3),
                ("Droit constitutionnel", "DCO", 3),
            ]),
            ("Méthodologie", "M-DRT-L1-2", [
                ("Méthodologie juridique", "MJD", 2),
                ("Histoire des institutions", "HIS", 2),
            ]),
        ],
        ("DRT", "L2"): [
            ("Droit privé", "M-DRT-L2-1", [
                ("Droit civil", "DCI", 4),
                ("Droit pénal", "DPE", 3),
            ]),
        ],
        ("DRT", "L3"): [
            ("Droit des affaires", "M-DRT-L3-1", [
                ("Droit commercial", "DCM", 4),
                ("Procédure civile", "PRC", 3),
            ]),
        ],
        ("GES", "L1"): [
            ("Bases de gestion", "M-GES-L1-1", [
                ("Introduction à la gestion", "IGE", 3),
                ("Comptabilité générale", "CGE", 3),
            ]),
            ("Outils", "M-GES-L1-2", [
                ("Mathématiques financières", "MAF", 2),
                ("Informatique de gestion", "INF", 2),
            ]),
        ],
        ("GES", "L2"): [
            ("Pilotage", "M-GES-L2-1", [
                ("Marketing", "MKT", 3),
                ("Gestion financière", "GFI", 4),
            ]),
        ],
        ("GES", "L3"): [
            ("Stratégie", "M-GES-L3-1", [
                ("Stratégie d'entreprise", "STR", 4),
                ("Contrôle de gestion", "CDG", 3),
            ]),
        ],
    }

    matieres = {}
    for (sigle, niv), modules in catalogue.items():
        dep = deps[sigle]
        classe = classes[(sigle, niv)]
        sem1 = periodes[niv][0]
        for ordre, (mod_nom, mod_code, mats) in enumerate(modules, start=1):
            module, _ = Module.objects.get_or_create(
                etablissement=etab, code=mod_code,
                defaults={"nom": mod_nom, "department": dep, "niveau_lmd": niv, "ordre": ordre, "actif": True},
            )
            ModuleDepartment.objects.get_or_create(module=module, department=dep)
            credits_mod = sum(c for _, _, c in mats)
            ModuleClasse.objects.get_or_create(
                module=module, classe=classe,
                defaults={"credits": Decimal(str(credits_mod)), "numero_ue": f"UE{niv[-1]}.{ordre}", "periode": sem1},
            )
            for mat_nom, mat_code, cred in mats:
                m = ensure_matiere(
                    etab, mat_nom, mat_code,
                    niveau="superieur", department=dep, module=module,
                    niveau_lmd_key=niv, credits=cred, coefficient=1,
                )
                m.classes.add(classe)
                matieres[mat_nom] = m

    profs = [
        ("Kouam", "Hélène", "helene.kouam.isdg@taysir-demo.cm", "Introduction au droit"),
        ("Manga", "Serge", "serge.manga.isdg@taysir-demo.cm", "Droit constitutionnel"),
        ("Eboa", "Patricia", "patricia.eboa.isdg@taysir-demo.cm", "Droit civil"),
        ("Nana", "Francis", "francis.nana.isdg@taysir-demo.cm", "Droit commercial"),
        ("Talla", "Mélanie", "melanie.talla.isdg@taysir-demo.cm", "Introduction à la gestion"),
        ("Fokou", "Richard", "richard.fokou.isdg@taysir-demo.cm", "Comptabilité générale"),
        ("Ngassa", "Inès", "ines.ngassa.isdg@taysir-demo.cm", "Marketing"),
        ("Bekolo", "Yves", "yves.bekolo.isdg@taysir-demo.cm", "Stratégie d'entreprise"),
    ]
    for nom, prenom, email, mat_nom in profs:
        if mat_nom not in matieres:
            continue
        prof, mdp = creer_prof(etab, nom, prenom, email, matieres[mat_nom], "superieur")
        report["profs"].append({"nom": f"{prenom} {nom}", "matricule": prof.numero_employe, "mdp": mdp, "matiere": mat_nom})
        for cl in matieres[mat_nom].classes.filter(etablissement=etab, actif=True):
            affecter(prof, cl, matieres[mat_nom], annee, principal=(mat_nom == "Introduction au droit" and "L1" in cl.nom and "DRT" in cl.nom))

    for cl in classes.values():
        creer_eleves(etab, cl, annee, ELEVES_PAR_CLASSE, report)
    report["classes"] = [c.nom for c in classes.values()]
    report["n_matieres"] = len(matieres)
    report["filieres"] = ["Droit (DRT)", "Gestion (GES)"]


def render_report(blocks: list[dict], path: Path) -> str:
    lines = [
        "ÉCOLES DE DÉMONSTRATION MARKETING TAYSIR",
        "Plateforme : https://aria-edu.com",
        "Connexion : https://aria-edu.com/connexion/",
        "Aucun email n'a été envoyé (comptes créés directement).",
        "Année scolaire active : 2026-2027 (ouverte).",
        "",
    ]
    for b in blocks:
        etab = b["etab"]
        lines += [
            "=" * 72,
            f"{b['titre']}",
            "=" * 72,
            f"Nom              : {etab.nom}",
            f"Type             : {etab.get_type_etablissement_display()}",
            f"Code             : {etab.code_etablissement}",
            f"Ville            : {etab.ville}, {etab.pays}",
            f"Adresse          : {etab.adresse}",
            f"Devise           : {etab.devise_monnaie}",
            f"Frais inscription: {etab.montant_frais_inscription} {etab.devise_monnaie}",
            f"Mensualité       : {etab.montant_mensualite} {etab.devise_monnaie}",
            "",
            "--- Directeur (espace établissement) ---",
            f"URL              : {CONNEXION}",
            f"Identifiant      : {etab.username}",
            f"Mot de passe     : {b['mdp_dir']}",
            f"Directeur        : {etab.directeur_prenom} {etab.directeur_nom}",
            "",
            f"Session          : {LIBELLE_ANNEE}",
            f"Classes          : {', '.join(b['classes'])}",
            f"Nb matières      : {b['n_matieres']}",
            f"Nb professeurs   : {len(b['profs'])}",
            f"Nb élèves        : {Eleve.objects.filter(etablissement=etab, actif=True).count()} ({ELEVES_PAR_CLASSE} / classe)",
        ]
        if b.get("filieres"):
            lines.append(f"Filières         : {', '.join(b['filieres'])}")
        lines += ["", "--- Professeurs (identifiant = matricule) ---"]
        for p in b["profs"]:
            lines.append(f"  {p['nom']:<24} {p['matiere']:<28} {p['matricule']:<12} mdp={p['mdp']}")
        lines += ["", "--- Exemples élèves / parents ---"]
        for e in b["eleves_exemples"]:
            lines.append(
                f"  {e['eleve']} ({e['classe']})  élève {e['matricule']} / {e['mdp']}"
                f"  | parent {e['parent']} / {e['mdp_parent']}"
            )
        lines.append("")
    text = "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def main():
    configs = [
        {
            "key": "superieur",
            "titre": "1. INSTITUT SUPÉRIEUR DE DROIT ET DE GESTION (supérieur)",
            "nom": "Institut Supérieur de Droit et de Gestion",
            "type": "superieur",
            "adresse": "Boulevard du 20 Mai, Yaoundé",
            "email_etab": "contact.isdg@taysir-demo.cm",
            "email_dir": "directeur.isdg@taysir-demo.cm",
            "dir_prenom": "Amina",
            "dir_nom": "Njoya",
            "tel": "690111001",
            "tel_dir": "690111002",
            "mdp": "IsdgTaysir26@",
            "inscription": 150000,
            "mensualite": 75000,
            "seeder": seed_superieur,
        },
        {
            "key": "college",
            "titre": "2. EDUTAYSIR (collège + lycée)",
            "nom": "Edutaysir",
            "type": "collège_lycée",
            "adresse": "Quartier Bastos, Yaoundé",
            "email_etab": "contact.edutaysir@taysir-demo.cm",
            "email_dir": "directeur.edutaysir@taysir-demo.cm",
            "dir_prenom": "Ibrahim",
            "dir_nom": "Tchaté",
            "tel": "690222001",
            "tel_dir": "690222002",
            "mdp": "EduTaysir26@",
            "inscription": 80000,
            "mensualite": 45000,
            "seeder": seed_college,
        },
        {
            "key": "primaire",
            "titre": "3. TAYSIR ACADÉMIE (primaire)",
            "nom": "Taysir Academie",
            "type": "primary",
            "adresse": "Quartier Nlongkak, Yaoundé",
            "email_etab": "contact.taysir-academie@taysir-demo.cm",
            "email_dir": "directeur.taysir-academie@taysir-demo.cm",
            "dir_prenom": "Fatima",
            "dir_nom": "Bello",
            "tel": "690333001",
            "tel_dir": "690333002",
            "mdp": "PrimTaysir26@",
            "inscription": 40000,
            "mensualite": 25000,
            "seeder": seed_primaire,
        },
    ]

    blocks = []
    for cfg in configs:
        print(f"\n>>> {cfg['nom']}")
        with transaction.atomic():
            etab, mdp_dir, created = creer_etablissement(cfg)
            print(f"    établissement {'créé' if created else 'réutilisé'} id={etab.id} code={etab.code_etablissement}")
            annee = ensure_annee(etab)
            report = {"etab": etab, "mdp_dir": mdp_dir if created else cfg["mdp"] if created else cfg["mdp"],
                      "titre": cfg["titre"], "profs": [], "eleves_exemples": [], "classes": [], "n_matieres": 0}
            if not created:
                report["mdp_dir"] = f"{cfg['mdp']}  (si le compte existait déjà, ce mot de passe a été réappliqué)"
                etab.set_password(cfg["mdp"])
                etab.save(update_fields=["password"])
                report["mdp_dir"] = cfg["mdp"]
            cfg["seeder"](etab, annee, report)
            etab.recalculer_facturation()
        blocks.append(report)
        print(f"    classes={len(report['classes'])} profs={len(report['profs'])} exemples_eleves={len(report['eleves_exemples'])}")

    out_vps = Path("/home/nick/aria/goo_school/tmp/identifiants_ecoles_taysir.txt")
    out_local = ROOT / "tmp" / "identifiants_ecoles_taysir.txt"
    target = out_vps if out_vps.parent.exists() or str(ROOT) == "/home/nick/aria/goo_school" else out_local
    if not target.parent.exists():
        target = out_local
    text = render_report(blocks, target)
    # Toujours aussi écrire à côté du script si chemins différents
    if target != out_local:
        out_local.parent.mkdir(parents=True, exist_ok=True)
        out_local.write_text(text, encoding="utf-8")
    print("\nFichier identifiants :", target)
    print(text)


if __name__ == "__main__":
    main()
