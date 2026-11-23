"""Crédits d'une matière (EC) dans une classe donnée — règle unique pour le supérieur (LMD).

Une UE (module) porte ses crédits classe par classe (ModuleClasse.credits) : elle peut valoir 4 crédits
en L1 Droit et 3 en L2 Économie. Les crédits saisis sur une matière servent de *poids* à l'intérieur de
son UE : dans chaque classe, les crédits de l'UE sont répartis entre ses matières au prorata de ces poids.

Exemple : UE de 6 crédits avec « Droit civil » (poids 4) et « Méthodologie » (poids 2) → 4 et 2 crédits.
La même UE, mutualisée avec une classe où elle vaut 3 crédits → 2 et 1 crédits dans cette classe.

Les délibérations, les bulletins et la maquette utilisent tous cette fonction : les totaux par classe
tombent toujours juste, quelle que soit la classe.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

D0 = Decimal('0')


def matieres_de_ue(module_id, classe):
    """Matières (EC) actives d'une UE suivies par cette classe, dans un ordre stable."""
    from school_admin.model.matiere_model import Matiere
    return list(Matiere.objects.filter(module_id=module_id, actif=True, etablissement_id=classe.etablissement_id)
                .filter(Q(classes=classe) | Q(classes__isnull=True)).distinct().order_by('pk'))


def repartir(credits_ue, ecs):
    """{pk: crédits} : crédits de l'UE répartis entre ses EC au prorata de leurs poids.

    Le dernier EC reçoit le reste, pour que la somme fasse exactement les crédits de l'UE.
    Sans poids renseignés, la répartition est égale.
    """
    total = Decimal(str(credits_ue or 0))
    if not ecs:
        return {}
    poids = sum((Decimal(str(getattr(m, 'credits', None) or 0)) for m in ecs), D0)
    resultat, restant = {}, total
    for i, m in enumerate(ecs):
        if i == len(ecs) - 1:
            credit = restant
        elif poids:
            credit = total * Decimal(str(getattr(m, 'credits', None) or 0)) / poids
        else:
            credit = total / len(ecs)
        restant -= credit
        resultat[m.pk] = credit
    return resultat


def credits_ec(matiere, classe, cache=None):
    """Crédits de cette matière dans cette classe, ou None si l'UE n'a pas de crédits pour la classe."""
    if not getattr(matiere, 'module_id', None) or classe is None:
        return None
    from school_admin.model.module_model import ModuleClasse
    cle = (matiere.module_id, classe.pk)
    if cache is not None and cle in cache:
        repartition = cache[cle]
    else:
        lien = ModuleClasse.objects.filter(module_id=matiere.module_id, classe=classe).only('credits').first()
        repartition = (repartir(lien.credits, matieres_de_ue(matiere.module_id, classe))
                       if lien and lien.credits and Decimal(str(lien.credits)) > 0 else {})
        if cache is not None:
            cache[cle] = repartition
    return repartition.get(matiere.pk)


def credits_varient_selon_classe(module):
    """Vrai si l'UE n'a pas les mêmes crédits dans toutes ses classes (UE mutualisée)."""
    valeurs = {Decimal(str(c or 0)) for c in module.module_classes.values_list('credits', flat=True)}
    return len(valeurs) > 1


def actualiser_credits_enregistres(module_id):
    """Remet à jour les crédits enregistrés avec les moyennes (MoyennePeriode.credits) des matières d'une UE.

    Appelée quand un réglage change (crédits de l'UE pour une classe, poids d'une matière, rattachement
    d'une matière ou de ses classes) : les relevés, exports et l'assistant qui lisent cette colonne restent
    justes sans relancer le calcul des moyennes. Seule l'année scolaire active est touchée : les années
    passées et les délibérations closes gardent leurs valeurs officielles.
    """
    if not module_id:
        return 0
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    from school_admin.model.matiere_model import Matiere
    from school_admin.model.module_model import Module
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    module = Module.objects.filter(pk=module_id).select_related('etablissement').first()
    if module is None or getattr(module.etablissement, 'type_etablissement', None) != 'superieur':
        return 0
    annee = AnneeScolaire.get_session_active(module.etablissement)
    if annee is None:
        return 0
    matieres = {m.pk: m for m in Matiere.objects.filter(module_id=module_id)}
    if not matieres:
        return 0
    from school_admin.model.classe_model import Classe

    lignes = list(MoyennePeriode.objects.filter(matiere_id__in=matieres, est_moyenne_generale=False,
                                                annee_scolaire=annee, eleve__classe__isnull=False)
                  .values_list('pk', 'matiere_id', 'eleve__classe_id', 'credits'))
    classes = {c.pk: c for c in Classe.objects.filter(pk__in={l[2] for l in lignes})}
    cache, a_changer = {}, {}
    for pk, matiere_id, classe_id, actuel in lignes:
        valeur = credits_ec(matieres[matiere_id], classes[classe_id], cache)
        if valeur is None:
            continue
        valeur = valeur.quantize(Decimal('0.01'))
        if actuel is None or Decimal(str(actuel)) != valeur:
            a_changer.setdefault(valeur, []).append(pk)
    for valeur, pks in a_changer.items():
        MoyennePeriode.objects.filter(pk__in=pks).update(credits=valeur)
    return sum(len(p) for p in a_changer.values())
