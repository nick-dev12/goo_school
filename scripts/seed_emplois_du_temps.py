"""
Crée les emplois du temps (EDT) pour toutes les classes de l'établissement collège + lycée.
"""
import os
import sys
from datetime import datetime

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")
django.setup()

from django.db import transaction
from django.utils import timezone

from school_admin.controllers.emploi_du_temps_controller import get_matiere_config
from school_admin.model.affectation_model import AffectationProfesseur
from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps, EmploiDuTemps
from school_admin.model.etablissement_model import Etablissement

ETABLISSEMENT_ID = 1

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]
SLOTS = [
    ("08:00", "09:00"),
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("14:00", "15:00"),
    ("15:00", "16:00"),
    ("16:00", "17:00"),
]

# Heures hebdomadaires par matière (approximation programme collège / lycée)
HEURES_PAR_MATIERE = {
    "Français": 4,
    "Mathématiques": 4,
    "Histoire-Géographie": 3,
    "Anglais LV1": 3,
    "SVT": 2,
    "Physique-Chimie": 2,
    "EPS": 2,
    "Arts plastiques": 1,
    "Technologie": 1,
    "Éducation musicale": 1,
    "Philosophie": 2,
    "SES": 2,
    "Espagnol LV2": 2,
}


def parse_time(value):
    return datetime.strptime(value, "%H:%M").time()


def slot_key(jour, heure_debut):
    return (jour, heure_debut.strftime("%H:%M"))


def heures_matiere(nom_matiere):
    return HEURES_PAR_MATIERE.get(nom_matiere, 2)


def build_affectations_par_classe(annee, etab):
    """Retourne {classe_id: [(matiere, professeur), ...]}"""
    result = {}
    qs = (
        AffectationProfesseur.objects.filter(
            actif=True,
            annee_scolaire=annee,
            classe__etablissement=etab,
        )
        .select_related("classe", "matiere", "professeur")
        .order_by("classe_id", "matiere__nom")
    )
    for aff in qs:
        result.setdefault(aff.classe_id, []).append((aff.matiere, aff.professeur))
    return result


def main():
    etab = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    annee = AnneeScolaire.get_session_active(etab)
    if not annee:
        print("Aucune annee scolaire active.")
        return

    classes = list(
        Classe.objects.filter(etablissement=etab, actif=True).order_by("niveau", "nom")
    )
    affectations_par_classe = build_affectations_par_classe(annee, etab)

    class_busy = {}
    prof_busy = {}
    total_creneaux = 0
    edt_crees = 0

    with transaction.atomic():
        for classe in classes:
            emploi, created = EmploiDuTemps.objects.get_or_create(
                classe=classe,
                annee_scolaire=annee.libelle,
                est_actif=True,
                defaults={
                    "annee_scolaire_fk": annee,
                    "statut_publication": "brouillon",
                    "notes": "Emploi du temps genere automatiquement",
                },
            )
            if not created:
                if emploi.annee_scolaire_fk_id != annee.id:
                    emploi.annee_scolaire_fk = annee
                    emploi.save(update_fields=["annee_scolaire_fk"])
                emploi.creneaux.all().delete()
            else:
                edt_crees += 1

            class_busy.setdefault(classe.id, set())
            entries = affectations_par_classe.get(classe.id, [])
            if not entries:
                continue

            # Placer d'abord les matières avec le plus d'heures
            entries_sorted = sorted(
                entries,
                key=lambda x: heures_matiere(x[0].nom),
                reverse=True,
            )

            for matiere, professeur in entries_sorted:
                nb_heures = heures_matiere(matiere.nom)
                placed = 0
                _, couleur = get_matiere_config(matiere.nom)

                for jour in JOURS:
                    if placed >= nb_heures:
                        break
                    for debut_str, fin_str in SLOTS:
                        if placed >= nb_heures:
                            break
                        debut = parse_time(debut_str)
                        fin = parse_time(fin_str)
                        ck = slot_key(jour, debut)
                        pk = slot_key(jour, debut)

                        if ck in class_busy[classe.id]:
                            continue
                        if pk in prof_busy.get(professeur.id, set()):
                            continue

                        CreneauEmploiDuTemps.objects.create(
                            emploi_du_temps=emploi,
                            jour=jour,
                            heure_debut=debut,
                            heure_fin=fin,
                            matiere=matiere,
                            professeur=professeur,
                            type_cours="sport" if matiere.nom == "EPS" else "cours",
                            couleur=couleur,
                        )
                        class_busy[classe.id].add(ck)
                        prof_busy.setdefault(professeur.id, set()).add(pk)
                        placed += 1
                        total_creneaux += 1

            # Publier l'emploi du temps
            emploi.statut_publication = "publie"
            emploi.date_publication = timezone.now()
            emploi.save(
                update_fields=["statut_publication", "date_publication", "date_modification"]
            )

    print(f"Annee scolaire : {annee.libelle}")
    print(f"Classes traitees : {len(classes)}")
    print(f"Nouveaux EDT : {edt_crees}")
    print(f"Creneaux crees : {total_creneaux}")
    print("\nDetail par classe :")
    for classe in classes:
        emploi = EmploiDuTemps.objects.filter(
            classe=classe, est_actif=True, annee_scolaire_fk=annee
        ).first()
        nb = emploi.creneaux.count() if emploi else 0
        statut = emploi.statut_publication if emploi else "-"
        print(f"  {classe.nom} ({classe.get_niveau_display()}) : {nb} creneaux, statut={statut}")


if __name__ == "__main__":
    main()
