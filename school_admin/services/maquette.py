"""
Maquette pédagogique du supérieur (LMD).

- synthèse d'une classe par semestre : UE (type, optionnelle, parcours), EC (crédits, volumes CM/TD/TP/TPE),
  totaux et contrôles (30 crédits par semestre, options incomplètes, volumes manquants…) ;
- UE réellement suivies par un étudiant : tronc commun + son parcours + ses UE optionnelles ;
- heures planifiées dans l'emploi du temps comparées à la maquette ;
- inscription pédagogique (parcours, options) et répartition dans les groupes de TD / TP.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction

D0 = Decimal('0')
CREDITS_SEMESTRE = Decimal('30')


def _f(valeur):
    """12.00 -> « 12 », 7.5 -> « 7,5 »."""
    v = Decimal(str(valeur or 0)).normalize()
    return format(v, 'f').replace('.', ',')


def _semaines(periode):
    if not (periode and periode.date_debut and periode.date_fin):
        return 0
    return max(1, round(((periode.date_fin - periode.date_debut).days + 1) / 7))


def heures_planifiees(classe, periode):
    """Heures par matière et par type (cours/td/tp) programmées dans l'emploi du temps actif, sur le semestre."""
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
    from django.db.models import Q

    qs = CreneauEmploiDuTemps.objects.filter(emploi_du_temps__classe=classe, emploi_du_temps__est_actif=True,
                                             matiere__isnull=False)
    if periode is not None:
        qs = qs.filter(Q(periode_scolaire=periode) | Q(periode_scolaire__isnull=True))
    semaines = _semaines(periode)
    # Heures vues par UN étudiant : les créneaux d'un groupe (TD G1, TD G2…) ne s'additionnent pas entre groupes.
    par_groupe = {}
    for c in qs:
        if not (c.heure_debut and c.heure_fin):
            continue
        duree = (datetime.combine(datetime.today(), c.heure_fin) - datetime.combine(datetime.today(), c.heure_debut))
        heures = Decimal(str(duree / timedelta(hours=1))) * semaines
        cle = {'td': 'td', 'tp': 'tp'}.get(c.type_cours, 'cm')
        k = (c.matiere_id, cle, c.groupe_id)
        par_groupe[k] = par_groupe.get(k, D0) + heures
    res = {}
    for (matiere_id, cle, groupe_id), heures in par_groupe.items():
        d = res.setdefault(matiere_id, {'cm': D0, 'td': D0, 'tp': D0})
        if groupe_id is None:
            d[cle] += heures
    for (matiere_id, cle, groupe_id), heures in par_groupe.items():
        if groupe_id is not None:
            commun = par_groupe.get((matiere_id, cle, None), D0)
            res[matiere_id][cle] = max(res[matiere_id][cle], commun + heures)
    return res


def maquette_classe(classe, periodes):
    """
    Renvoie [{'periode', 'ues': [...], 'totaux': {...}, 'controles': [...]}] pour chaque semestre.
    """
    from school_admin.model.module_model import ModuleClasse
    from school_admin.model.matiere_model import Matiere

    semestres = []
    for periode in periodes:
        mcs = list(ModuleClasse.objects.filter(classe=classe, periode=periode)
                   .select_related('module', 'parcours').order_by('module__ordre', 'numero_ue', 'module__nom'))
        planif = heures_planifiees(classe, periode)
        ues, controles = [], []
        tot = {'credits': D0, 'cm': 0, 'td': 0, 'tp': 0, 'tpe': 0, 'ec': 0, 'credits_obligatoires': D0}
        groupes = OrderedDict()
        for mc in mcs:
            ecs = list(Matiere.objects.filter(module=mc.module, actif=True)
                       .filter(classes=classe).distinct().order_by('nom')) or \
                list(Matiere.objects.filter(module=mc.module, actif=True).order_by('nom'))
            somme_ec = sum((Decimal(str(m.credits or 0)) for m in ecs), D0)
            lignes = []
            for m in ecs:
                p = planif.get(m.id, {})
                prevu = m.volume_cm + m.volume_td + m.volume_tp
                planifie = sum(p.values(), D0) if p else D0
                lignes.append({'matiere': m, 'planifie': p, 'prevu': prevu,
                               'planifie_total': planifie,
                               'ecart': (planifie - prevu) if prevu else None})
                tot['ec'] += 1
                if not (m.volume_cm or m.volume_td or m.volume_tp):
                    controles.append(f"{m.nom} : volume horaire (CM / TD / TP) non renseigné.")
            if ecs and somme_ec and Decimal(str(mc.credits or 0)) and somme_ec != Decimal(str(mc.credits)):
                controles.append(f"{mc.module.nom} : {_f(mc.credits)} crédits pour l'UE mais {_f(somme_ec)} pour ses EC.")
            if not ecs:
                controles.append(f"{mc.module.nom} : aucun EC (matière) dans cette UE.")
            ue = {'mc': mc, 'ecs': lignes,
                  'cm': sum(m.volume_cm for m in ecs), 'td': sum(m.volume_td for m in ecs),
                  'tp': sum(m.volume_tp for m in ecs), 'tpe': sum(m.volume_tpe for m in ecs)}
            ues.append(ue)
            for k in ('cm', 'td', 'tp', 'tpe'):
                tot[k] += ue[k]
            if mc.optionnelle:
                groupes.setdefault(mc.groupe_options or 'Options', []).append(mc)
            elif not mc.parcours_id:
                tot['credits_obligatoires'] += Decimal(str(mc.credits or 0))
        # crédits d'un étudiant type : tronc commun + options choisies (+ parcours le cas échéant)
        credits_options = D0
        for nom, liste in groupes.items():
            n = liste[0].choix_requis or 1
            if len(liste) <= n:
                controles.append(f"Groupe d'options « {nom} » : {len(liste)} UE pour {n} à choisir — aucun choix réel.")
            credits_options += sum(sorted((Decimal(str(x.credits or 0)) for x in liste), reverse=True)[:n], D0)
        parcours_credits = {}
        for mc in mcs:
            if mc.parcours_id and not mc.optionnelle:
                parcours_credits.setdefault(mc.parcours, D0)
                parcours_credits[mc.parcours] += Decimal(str(mc.credits or 0))
        tot['credits'] = tot['credits_obligatoires'] + credits_options
        if parcours_credits:
            for parc, cr in parcours_credits.items():
                total_parc = tot['credits'] + cr
                if total_parc != CREDITS_SEMESTRE:
                    controles.append(f"Parcours « {parc.nom} » : {_f(total_parc)} crédits sur le semestre (30 attendus).")
            tot['credits'] += max(parcours_credits.values())
        elif mcs and tot['credits'] != CREDITS_SEMESTRE:
            controles.append(f"{_f(tot['credits'])} crédits par étudiant sur le semestre : 30 attendus en LMD.")
        if not mcs:
            controles.append("Aucune UE rattachée à ce semestre : la maquette est à construire.")
        tot['presentiel'] = tot['cm'] + tot['td'] + tot['tp']
        tot['charge'] = tot['presentiel'] + tot['tpe']
        semestres.append({'periode': periode, 'ues': ues, 'totaux': tot, 'controles': controles,
                          'groupes_options': groupes, 'semaines': _semaines(periode)})
    return semestres


# --------------------------------------------------------------------------- étudiant
def inscription(eleve, annee):
    from school_admin.model.maquette_model import InscriptionPedagogique

    if annee is None:
        return None
    return (InscriptionPedagogique.objects.filter(eleve=eleve, annee_scolaire=annee)
            .prefetch_related('ues_optionnelles').first())


def module_ids_exclus(eleve, classe, annee):
    """UE de la classe que l'étudiant ne suit pas : autre parcours, options non choisies."""
    from django.db.models import Q
    from school_admin.model.module_model import ModuleClasse

    mcs = list(ModuleClasse.objects.filter(classe=classe).filter(Q(parcours__isnull=False) | Q(optionnelle=True)))
    if not mcs:
        return set()
    ins = inscription(eleve, annee)
    parcours_id = ins.parcours_id if ins else None
    choisies = set(ins.ues_optionnelles.values_list('id', flat=True)) if ins else set()
    exclus = set()
    for mc in mcs:
        if mc.parcours_id and mc.parcours_id != parcours_id:
            exclus.add(mc.module_id)
        elif mc.optionnelle and mc.id not in choisies:
            exclus.add(mc.module_id)
    return exclus


def matiere_suivie(eleve, matiere, classe, annee, cache=None):
    """False si l'EC appartient à une UE que l'étudiant ne suit pas."""
    if not getattr(matiere, 'module_id', None):
        return True
    cle = (eleve.id, classe.id, getattr(annee, 'id', None))
    if cache is not None and cle in cache:
        exclus = cache[cle]
    else:
        exclus = module_ids_exclus(eleve, classe, annee)
        if cache is not None:
            cache[cle] = exclus
    return matiere.module_id not in exclus


def enregistrer_inscriptions(classe, annee, saisies):
    """
    saisies : {eleve_id: {'parcours': id|None, 'options': [module_classe_id, ...]}}
    Vérifie le nombre d'UE choisies par groupe d'options. Renvoie la liste des erreurs (tout ou rien).
    """
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.maquette_model import InscriptionPedagogique, Parcours
    from school_admin.model.module_model import ModuleClasse

    parcours_ok = set(Parcours.objects.filter(classe=classe).values_list('id', flat=True))
    options = {mc.id: mc for mc in ModuleClasse.objects.filter(classe=classe, optionnelle=True)}
    groupes = {}
    for mc in options.values():
        groupes.setdefault((mc.periode_id, mc.groupe_options or 'Options'), []).append(mc)
    eleves = {e.id: e for e in Eleve.objects.filter(id__in=saisies.keys())}
    erreurs, a_ecrire = [], []
    for eleve_id, s in saisies.items():
        e = eleves.get(eleve_id)
        if e is None:
            continue
        parcours = s.get('parcours')
        if parcours and int(parcours) not in parcours_ok:
            erreurs.append(f"{e.nom_complet} : parcours invalide.")
            continue
        choix = [int(x) for x in s.get('options') or [] if str(x).isdigit() and int(x) in options]
        for (per, nom), liste in groupes.items():
            n = liste[0].choix_requis or 1
            pris = [c for c in choix if options[c] in liste]
            if pris and len(pris) != n:
                erreurs.append(f"{e.nom_complet} : {len(pris)} UE choisie(s) dans « {nom} » ({n} attendue(s)).")
        a_ecrire.append((e, int(parcours) if parcours else None, choix))
    if erreurs:
        return erreurs
    with transaction.atomic():
        for e, parcours_id, choix in a_ecrire:
            ins, _ = InscriptionPedagogique.objects.update_or_create(
                eleve=e, annee_scolaire=annee, defaults={'classe': classe, 'parcours_id': parcours_id})
            ins.ues_optionnelles.set(choix)
    return []


def repartir_groupes(classe, eleves, type_groupe='td'):
    """Répartit équitablement les étudiants (ordre alphabétique) dans les groupes du type donné."""
    from school_admin.model.maquette_model import GroupeEnseignement

    groupes = list(GroupeEnseignement.objects.filter(classe=classe, type_groupe=type_groupe).order_by('nom'))
    if not groupes:
        return 0
    with transaction.atomic():
        for g in groupes:
            g.etudiants.clear()
        for i, e in enumerate(sorted(eleves, key=lambda x: (x.nom, x.prenom))):
            groupes[i % len(groupes)].etudiants.add(e)
    return len(groupes)


def creneaux_etudiant(creneaux, eleve, classe, annee, aujourd_hui=None):
    """
    Emploi du temps d'un étudiant du supérieur : semestre en cours (ou créneaux « toute l'année »),
    son groupe de TD / TP (ou classe entière), et uniquement les UE qu'il suit (parcours, options).
    """
    from django.utils import timezone
    from school_admin.model.maquette_model import GroupeEnseignement

    aujourd_hui = aujourd_hui or timezone.localdate()
    mes_groupes = set(GroupeEnseignement.objects.filter(classe=classe, etudiants=eleve).values_list('id', flat=True))
    exclus = module_ids_exclus(eleve, classe, annee)
    semestres = [c.periode_scolaire for c in creneaux if getattr(c, 'periode_scolaire_id', None)]
    en_cours = next((p for p in semestres if p.date_debut <= aujourd_hui <= p.date_fin), None)
    resultat = []
    for c in creneaux:
        if getattr(c, 'periode_scolaire_id', None) and en_cours and c.periode_scolaire_id != en_cours.id:
            continue
        if getattr(c, 'groupe_id', None) and c.groupe_id not in mes_groupes:
            continue
        if c.matiere_id and getattr(c.matiere, 'module_id', None) in exclus:
            continue
        resultat.append(c)
    return resultat
