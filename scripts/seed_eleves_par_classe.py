"""
Peuple les classes actives d'un établissement avec N élèves par classe.
Usage : python manage.py shell < scripts/seed_eleves_par_classe.py
"""
from datetime import date, timedelta
import random

from django.db import transaction

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.personal_views.secretaire_view import _archiver_inscription_eleve_parent

ETABLISSEMENT_ID = 3
ELEVES_PAR_CLASSE = 10

PRENOMS_M = [
    'Amadou', 'Ibrahim', 'Moussa', 'Cheikh', 'Ousmane',
    'Jean', 'Paul', 'Marc', 'David', 'Kevin',
]
PRENOMS_F = [
    'Fatou', 'Aissatou', 'Mariama', 'Aminata', 'Khady',
    'Sophie', 'Claire', 'Julie', 'Emma', 'Sarah',
]
NOMS = [
    'Diallo', 'Sow', 'Ba', 'Ndiaye', 'Fall',
    'Sy', 'Gueye', 'Camara', 'Traore', 'Mbaye',
]
LIEUX = ['Dakar', 'Thies', 'Saint-Louis', 'Kaolack', 'Ziguinchor']


def _creer_eleve_avec_parent(etablissement, classe, annee_scolaire, index, seq_global):
    sexe = 'M' if index % 2 == 0 else 'F'
    prenom = (PRENOMS_M if sexe == 'M' else PRENOMS_F)[index % 10]
    nom = NOMS[index % len(NOMS)]
    matricule = Eleve.generer_matricule_eleve(etablissement)
    mot_de_passe = Eleve.generer_mot_de_passe()
    date_naissance = date(2003, 1, 1) + timedelta(days=(seq_global * 37) % 3000)
    parent_tel = f"77{seq_global:07d}"[-9:]

    eleve = Eleve(
        username=matricule,
        matricule_eleve=matricule,
        numero_eleve=matricule,
        nom=nom,
        prenom=prenom,
        date_naissance=date_naissance,
        lieu_naissance=random.choice(LIEUX),
        sexe=sexe,
        nationalite='Sénégalaise',
        etablissement=etablissement,
        classe=classe,
        date_inscription=date.today(),
        statut='nouvelle',
        parent_nom=f'Parent {nom}',
        parent_prenom='Tuteur',
        parent_telephone=parent_tel,
        parent_lien='pere' if sexe == 'M' else 'mere',
        mot_de_passe_provisoire=mot_de_passe,
        mot_de_passe_eleve_modifie=False,
        is_active=True,
        actif=True,
    )
    eleve.set_password(mot_de_passe)
    eleve.save()

    matricule_parent = Parent.generer_matricule_parent(etablissement)
    mot_de_passe_parent = Parent.generer_mot_de_passe() if hasattr(Parent, 'generer_mot_de_passe') else mot_de_passe
    parent = Parent(
        matricule_parental=matricule_parent,
        type_parent='pere' if sexe == 'M' else 'mere',
        nom=eleve.parent_nom,
        prenom=eleve.parent_prenom,
        telephone=parent_tel,
        email='',
        adresse='',
        profession='',
        etablissement=etablissement,
        mot_de_passe_provisoire=mot_de_passe_parent,
        mot_de_passe_modifie=False,
        username=matricule_parent,
        is_active=True,
    )
    parent.set_password(mot_de_passe_parent)
    parent.save()

    LienFamilial.objects.create(
        parent=parent,
        eleve=eleve,
        type_lien=eleve.parent_lien,
        statut='valide',
        est_inscripteur=True,
        actif=True,
    )

    _archiver_inscription_eleve_parent(
        eleve=eleve,
        parent=parent,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        date_inscription=eleve.date_inscription,
    )
    return eleve


def main():
    etablissement = Etablissement.objects.get(id=ETABLISSEMENT_ID)
    annee_scolaire = AnneeScolaire.objects.filter(
        etablissement=etablissement,
        est_active=True,
    ).first()
    if not annee_scolaire:
        raise SystemExit('Aucune année scolaire active.')

    classes = Classe.objects.filter(etablissement=etablissement, actif=True).order_by('id')
    seq_global = Eleve.objects.filter(etablissement=etablissement).count()
    created_total = 0

    with transaction.atomic():
        for classe in classes:
            existing = Eleve.objects.filter(classe=classe, actif=True).count()
            to_create = max(0, ELEVES_PAR_CLASSE - existing)
            for i in range(to_create):
                seq_global += 1
                _creer_eleve_avec_parent(
                    etablissement,
                    classe,
                    annee_scolaire,
                    index=(existing + i),
                    seq_global=seq_global,
                )
                created_total += 1
            print(f'{classe.nom}: +{to_create} élève(s) (total {existing + to_create})')

    print(f'Terminé — {created_total} élève(s) créé(s) pour {classes.count()} classe(s).')


main()
