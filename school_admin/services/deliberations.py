"""
Délibérations LMD : calcul des décisions du jury, points de jury, capitalisation des UE,
passage conditionnel (dettes), verrouillage des notes après clôture et procès-verbal.

Règles (ReglesExamen de l'établissement) :
- semestre : UE acquise si moyenne ≥ seuil ; compensation semestrielle si la moyenne du semestre
  (+ points de jury) ≥ seuil, sans note éliminatoire ni épreuve manquante ;
- année : UE acquises dans chaque semestre ; compensation annuelle (option) si la moyenne de l'année
  (+ points de jury) ≥ seuil ; tous les crédits → Admis ; au moins X % des crédits → Admis avec dettes
  (passage conditionnel) ; sinon Redouble ;
- une UE capitalisée une année précédente reste acquise (l'étudiant ne la repasse pas).
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from school_admin.model.deliberation_model import DecisionJury, Deliberation, UECapitalisee
from school_admin.services import examens as moteur

D0 = Decimal('0')
MENTIONS = [(Decimal('16'), 'Très bien'), (Decimal('14'), 'Bien'), (Decimal('12'), 'Assez bien'),
            (Decimal('10'), 'Passable')]
LIBELLES = dict(DecisionJury.DECISION_CHOICES)
DECISION_SEMESTRE = {'Admis': DecisionJury.ADMIS, 'Admis par compensation': DecisionJury.ADMIS_COMPENSATION,
                     'Ajourné': DecisionJury.AJOURNE, 'Incomplet': DecisionJury.INCOMPLET}


class DeliberationErreur(Exception):
    pass


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def fmt(valeur):
    v = Decimal(str(valeur or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP).normalize()
    return format(v, 'f').replace('.', ',')


# --------------------------------------------------------------------------- périmètre
def periodes_annee(classe, annee):
    from school_admin.model.periode_model import PeriodeScolaire

    qs = PeriodeScolaire.objects.filter(etablissement_id=classe.etablissement_id, annee_scolaire_fk=annee)
    if classe.niveau_lmd:
        qs = qs.filter(niveau_lmd=classe.niveau_lmd)
    return list(qs.order_by('date_debut'))


def periodes_de(deliberation):
    if deliberation.periode_id:
        return [deliberation.periode]
    return periodes_annee(deliberation.classe, deliberation.annee_scolaire)


def etudiants(classe, annee):
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    ids = list(InscriptionEleve.objects.filter(classe=classe, annee_scolaire=annee)
               .values_list('eleve_id', flat=True))
    qs = Eleve.objects.filter(id__in=ids) if ids else Eleve.objects.filter(classe=classe)
    return list(qs.filter(actif=True).order_by('nom', 'prenom'))


# --------------------------------------------------------------------------- lignes de notes
def _capitalisations(eleve, exclure_deliberation=None, annee=None):
    """UE capitalisées les années précédentes (celles de l'année en cours sont recalculées normalement)."""
    qs = UECapitalisee.objects.filter(eleve=eleve).select_related('module')
    if exclure_deliberation is not None:
        qs = qs.exclude(deliberation=exclure_deliberation)
    if annee is not None:
        qs = qs.exclude(annee_scolaire=annee)
    return {c.module_id: c for c in qs}


def lignes_eleve(eleve, classe, periodes, annee, exclure_deliberation=None):
    """Lignes EC (MoyennePeriode) du ou des semestres, avec les UE déjà capitalisées marquées."""
    from school_admin.model.module_model import ModuleClasse
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    caps = _capitalisations(eleve, exclure_deliberation, annee)
    par_periode = OrderedDict((p.id, []) for p in periodes)
    rows = (MoyennePeriode.objects.filter(eleve=eleve, periode__in=periodes, est_moyenne_generale=False,
                                          matiere__isnull=False)
            .select_related('matiere', 'matiere__module'))
    if annee is not None:
        from django.db.models import Q
        rows = rows.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
    from school_admin.services.maquette import module_ids_exclus
    exclus = module_ids_exclus(eleve, classe, annee)
    vus = set()
    for r in rows:
        m = r.matiere
        if m.module_id and m.module_id in exclus:
            continue  # UE d'un autre parcours ou option non choisie
        cap = caps.get(m.module_id) if m.module_id else None
        par_periode[r.periode_id].append({
            'matiere': m,
            'moyenne': None if r.moyenne_matiere is None else Decimal(str(r.moyenne_matiere)),
            'coefficient': r.coefficient or m.coefficient or 1,
            'credits': r.credits if r.credits is not None else (m.credits or 0),
            'capitalisee': bool(cap),
        })
        if m.module_id:
            vus.add(m.module_id)
    # UE de la maquette déjà capitalisées mais sans note cette année (l'étudiant ne les repasse pas)
    for mc in ModuleClasse.objects.filter(classe=classe, periode__in=periodes).select_related('module'):
        cap = caps.get(mc.module_id)
        if cap and mc.module_id not in vus:
            fictive = SimpleNamespace(id=f'cap-{mc.module_id}', module_id=mc.module_id, module=mc.module,
                                      nom=mc.module.nom)
            par_periode[mc.periode_id].append({'matiere': fictive, 'moyenne': cap.moyenne, 'coefficient': 1,
                                               'credits': cap.credits or mc.credits, 'capitalisee': True})
    return par_periode


# --------------------------------------------------------------------------- calcul d'une décision
def mention(moyenne, admis):
    if not admis or moyenne is None:
        return ''
    for seuil, libelle in MENTIONS:
        if Decimal(str(moyenne)) >= seuil:
            return libelle
    return ''


def _detail(ues):
    return [{'titre': u['titre'], 'moyenne': None if u['moyenne'] is None else str(u['moyenne']),
             'credits': str(u['credits']), 'acquise': bool(u['acquise']), 'mode': u['mode'],
             'module_id': u['cle'][1] if u['cle'] and u['cle'][0] == 'ue' else None} for u in ues]


def calculer(deliberation, eleve, points_jury=D0, regle=None):
    """Résultat du jury pour un étudiant (sans écriture en base)."""
    regle = regle or moteur.regles(deliberation.etablissement)
    points = Decimal(str(points_jury or 0))
    periodes = periodes_de(deliberation)
    lignes = lignes_eleve(eleve, deliberation.classe, periodes, deliberation.annee_scolaire,
                          exclure_deliberation=deliberation)
    if deliberation.periode_id:
        v = moteur.validation_lmd(lignes[deliberation.periode_id], regle, bonus=points)
        decision = DECISION_SEMESTRE.get(v['decision'], DecisionJury.AJOURNE)
        ues, moyenne, moyenne_jury = v['ues'], v['moyenne_semestre'], v['moyenne_jury']
        acquis, total = v['credits_acquis'], v['credits_total']
    else:
        ues, total, acquis = [], D0, D0
        toutes = []
        incomplet = False
        for pid, ls in lignes.items():
            vs = moteur.validation_lmd(ls, regle)
            ues.extend(vs['ues'])
            incomplet = incomplet or vs['incomplet']
            toutes.extend(ls)
        va = moteur.validation_lmd(toutes, regle, bonus=points, compensation=False)
        moyenne, moyenne_jury = va['moyenne_semestre'], va['moyenne_jury']
        if (regle.compensation_annuelle and moyenne_jury is not None
                and moyenne_jury >= Decimal(str(regle.seuil_validation))
                and not va['eliminatoire'] and not incomplet):
            for u in ues:
                if not u['acquise']:
                    u['acquise'], u['mode'] = True, 'compensee'
        total = sum((u['credits'] for u in ues), D0)
        acquis = sum((u['credits'] for u in ues if u['acquise']), D0)
        pct = (acquis / total * 100) if total else D0
        if total and acquis >= total:
            decision = (DecisionJury.ADMIS_COMPENSATION if any(u['mode'] == 'compensee' for u in ues)
                        else DecisionJury.ADMIS)
        elif total and regle.pourcentage_passage_conditionnel < 100 and pct >= regle.pourcentage_passage_conditionnel:
            decision = DecisionJury.ADMIS_CONDITIONNEL
        elif not toutes:
            decision = DecisionJury.INCOMPLET
        else:
            decision = DecisionJury.REDOUBLE
    admis = decision in (DecisionJury.ADMIS, DecisionJury.ADMIS_COMPENSATION, DecisionJury.ADMIS_CONDITIONNEL)
    return {
        'moyenne': moyenne, 'moyenne_jury': moyenne_jury, 'points_jury': points,
        'credits_acquis': acquis, 'credits_total': total, 'decision': decision,
        'decision_libelle': LIBELLES[decision], 'mention': mention(moyenne_jury, admis),
        'ues': _detail(ues), 'dettes': [u['titre'] for u in ues if not u['acquise']],
    }


# --------------------------------------------------------------------------- délibération
def creer(etablissement, classe, annee, periode=None, session=Deliberation.SESSION_NORMALE):
    if classe.etablissement_id != etablissement.id:
        raise DeliberationErreur("Classe invalide.")
    existante = Deliberation.objects.filter(classe=classe, annee_scolaire=annee, periode=periode,
                                            session=session).first()
    if existante:
        return existante, False
    d = Deliberation.objects.create(etablissement=etablissement, classe=classe, annee_scolaire=annee,
                                    periode=periode, session=session, date_deliberation=timezone.localdate())
    preparer(d)
    return d, True


def preparer(deliberation):
    """(Re)calcule toutes les décisions en conservant les points et motifs déjà saisis."""
    if deliberation.est_cloturee:
        raise DeliberationErreur("La délibération est clôturée : rouvrez-la pour la modifier.")
    regle = moteur.regles(deliberation.etablissement)
    existantes = {d.eleve_id: d for d in deliberation.decisions.all()}
    with transaction.atomic():
        for eleve in etudiants(deliberation.classe, deliberation.annee_scolaire):
            dj = existantes.get(eleve.id) or DecisionJury(deliberation=deliberation, eleve=eleve)
            r = calculer(deliberation, eleve, dj.points_jury, regle)
            _appliquer(dj, r)
            dj.save()
    return deliberation


def _appliquer(dj, r):
    dj.moyenne, dj.moyenne_jury = r['moyenne'], r['moyenne_jury']
    dj.credits_acquis, dj.credits_total = r['credits_acquis'], r['credits_total']
    dj.decision, dj.mention, dj.detail_ues = r['decision'], r['mention'], r['ues']


def enregistrer_points(deliberation, saisies):
    """saisies : {eleve_id: (points, motif)}. Renvoie la liste des erreurs (rien n'est écrit s'il y en a)."""
    if deliberation.est_cloturee:
        return ["La délibération est clôturée : rouvrez-la pour modifier les points de jury."]
    regle = moteur.regles(deliberation.etablissement)
    maxi = Decimal(str(regle.points_jury_max))
    decisions = {d.eleve_id: d for d in deliberation.decisions.select_related('eleve')}
    erreurs, a_ecrire = [], []
    for eleve_id, (brut, motif) in saisies.items():
        dj = decisions.get(eleve_id)
        if dj is None:
            continue
        try:
            points = Decimal(str(brut or '0').replace(',', '.'))
        except Exception:
            erreurs.append(f"{dj.eleve.nom_complet} : « {brut} » n'est pas un nombre.")
            continue
        if points < 0 or points > maxi:
            erreurs.append(f"{dj.eleve.nom_complet} : les points de jury vont de 0 à {fmt(maxi)}.")
            continue
        if points > 0 and not (motif or '').strip():
            erreurs.append(f"{dj.eleve.nom_complet} : indiquez le motif des points de jury (traçabilité du PV).")
            continue
        a_ecrire.append((dj, points, (motif or '').strip()[:255]))
    if erreurs:
        return erreurs
    with transaction.atomic():
        for dj, points, motif in a_ecrire:
            dj.points_jury, dj.motif_jury = points, motif
            _appliquer(dj, calculer(deliberation, dj.eleve, points, regle))
            dj.save()
    return []


def cloturer(deliberation, par=''):
    """Clôture : décisions figées, UE acquises capitalisées, décisions reportées au bulletin, notes verrouillées."""
    if deliberation.est_cloturee:
        return deliberation
    preparer(deliberation)
    from school_admin.model.module_model import Module
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    with transaction.atomic():
        for dj in deliberation.decisions.select_related('eleve'):
            for ue in dj.detail_ues:
                if not (ue.get('acquise') and ue.get('module_id')) or ue.get('mode') == 'capitalisee':
                    continue
                UECapitalisee.objects.get_or_create(
                    eleve=dj.eleve, module=Module(pk=ue['module_id']),
                    defaults={'annee_scolaire': deliberation.annee_scolaire, 'periode': deliberation.periode,
                              'moyenne': Decimal(ue['moyenne']) if ue.get('moyenne') else None,
                              'credits': Decimal(ue['credits']), 'mode': ue['mode'],
                              'deliberation': deliberation})
            if deliberation.periode_id:
                texte = f"{dj.get_decision_display()} — {fmt(dj.credits_acquis)}/{fmt(dj.credits_total)} crédits"
                if dj.points_jury:
                    texte += f" (jury +{fmt(dj.points_jury)})"
                MoyennePeriode.objects.filter(eleve=dj.eleve, periode=deliberation.periode,
                                              est_moyenne_generale=True).update(decision_conseil=texte)
        deliberation.statut = Deliberation.STATUT_CLOTUREE
        deliberation.cloturee_le = timezone.now()
        deliberation.cloturee_par = (par or '')[:150]
        deliberation.save()
    return deliberation


def rouvrir(deliberation):
    """Rouvre une délibération : les capitalisations qu'elle a créées sont retirées."""
    with transaction.atomic():
        deliberation.capitalisations.all().delete()
        deliberation.statut = Deliberation.STATUT_BROUILLON
        deliberation.cloturee_le = None
        deliberation.save()
    return deliberation


def periode_verrouillee(classe, periode):
    """Délibération clôturée pour ce semestre (ou pour l'année) : les notes ne bougent plus."""
    if classe is None or periode is None:
        return None
    qs = Deliberation.objects.filter(classe=classe, statut=Deliberation.STATUT_CLOTUREE)
    d = qs.filter(periode=periode).first()
    if d is None and periode.annee_scolaire_fk_id:
        d = qs.filter(periode__isnull=True, annee_scolaire_id=periode.annee_scolaire_fk_id).first()
    return d


def message_verrou(deliberation):
    return (f"Les notes de {deliberation.classe.nom} ({deliberation.libelle_portee}) sont verrouillées : "
            f"la délibération est clôturée. Rouvrez-la pour toute correction.")


def statistiques(deliberation):
    decisions = list(deliberation.decisions.all())
    n = len(decisions)
    par = OrderedDict((code, 0) for code, _ in DecisionJury.DECISION_CHOICES)
    for d in decisions:
        par[d.decision] += 1
    admis = sum(1 for d in decisions if d.est_admis)
    moyennes = [d.moyenne_jury for d in decisions if d.moyenne_jury is not None]
    return {
        'effectif': n, 'admis': admis, 'taux_admis': round(100 * admis / n) if n else 0,
        'par_decision': [{'libelle': LIBELLES[c], 'nombre': v, 'code': c, 'pct': round(100 * v / n, 1) if n else 0}
                         for c, v in par.items() if v],
        'moyenne_promo': _q(sum(moyennes) / len(moyennes)) if moyennes else None,
        'avec_points': sum(1 for d in decisions if d.points_jury),
    }
