"""
Moteur unique des examens : quelle note d'examen compte, comment elle se combine avec le
contrôle continu, et (supérieur) comment les UE et le semestre sont validés.

Règles appliquées (configurables par établissement via ReglesExamen) :
- seules les sessions « comptant au bulletin », non annulées, sont prises en compte ;
  un examen blanc est exclu par défaut ;
- seules les notes soumises ou publiées comptent (un brouillon ne va pas au bulletin) ;
- plusieurs compositions dans la même période : moyenne des compositions ;
- absence justifiée : examen neutralisé ; absence non justifiée : 0/20 (ou neutralisée selon la règle) ;
- rattrapage : meilleure des deux notes, ou remplacement (règle de l'établissement) ;
- moyenne de matière = contrôle continu × poids classe + examen × poids examen ; la note d'examen
  n'est comptée qu'une fois (le contrôle continu enregistré par l'enseignant ne la contient plus) ;
- supérieur (LMD, référentiel CAMES) : UE acquise si sa moyenne ≥ seuil ; compensation entre UE
  dans le semestre si la moyenne du semestre ≥ seuil et qu'aucune note éliminatoire n'est atteinte.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

D0 = Decimal('0')
D20 = Decimal('20')


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def regles(etablissement):
    from school_admin.model.session_examen_model import ReglesExamen

    return ReglesExamen.pour(etablissement)


# --------------------------------------------------------------------------- notes d'examen
def note_comptee(note):
    """Une note d'examen est prise en compte si elle est soumise ou publiée (jamais un simple brouillon)."""
    return bool(note.soumis or note.statut_publication != 'brouillon' or note.note_publiee is not None)


def valeur_sur_20(note):
    """Valeur sur 20 retenue : la dernière publiée si la note a été modifiée depuis, sinon la note courante."""
    if note.absent:
        return None
    brute = note.note
    if note.statut_publication == 'modifiee' and note.note_publiee is not None and not note.soumis:
        brute = note.note_publiee
    if brute is None:
        return None
    bareme = Decimal(str(note.bareme or 20)) or D20
    return _q(Decimal(str(brute)) / bareme * D20)


def _agreger(notes, absence_zero):
    """Moyenne d'un groupe de notes (compositions d'une période) ; renvoie (valeur, statut)."""
    valeurs, absent_injustifie, absent_justifie = [], False, False
    for n in notes:
        if n.absent:
            if n.absence_justifiee:
                absent_justifie = True
            elif absence_zero:
                absent_injustifie = True
                valeurs.append(D0)
            else:
                absent_justifie = True
            continue
        v = valeur_sur_20(n)
        if v is not None:
            valeurs.append(v)
    if valeurs:
        moyenne = _q(sum(valeurs) / len(valeurs))
        present = any(not n.absent and valeur_sur_20(n) is not None for n in notes)
        return moyenne, ('note' if present else 'absent')
    if absent_justifie:
        return None, 'absent_justifie'
    return None, 'manquante'


def resultat_examen(eleve, classe, matiere, periode, annee=None, etablissement=None, regle=None):
    """Note d'examen effective d'un élève dans une matière pour une période."""
    from school_admin.model.note_examen_model import NoteExamen

    etablissement = etablissement or classe.etablissement
    regle = regle or regles(etablissement)
    qs = (NoteExamen.objects.filter(eleve=eleve, classe=classe, matiere=matiere, actif=True,
                                    session_examen__periode=periode, session_examen__compte_bulletin=True,
                                    session_examen__est_annule=False, session_examen__actif=True)
          .select_related('session_examen'))
    if annee is not None:
        qs = qs.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
    notes = list(qs)
    non_publiees = [n for n in notes if not note_comptee(n)]
    comptees = [n for n in notes if note_comptee(n)]
    absence_zero = regle.absence_injustifiee == 'zero'
    normales = [n for n in comptees if n.session_examen.type_session != 'rattrapage']
    rattrapages = [n for n in comptees if n.session_examen.type_session == 'rattrapage']
    normale, statut = _agreger(normales, absence_zero)
    # Une absence au rattrapage ne fait pas perdre la note de 1re session.
    ratt_presentes = [n for n in rattrapages if not n.absent]
    rattrapage, _s = _agreger(ratt_presentes, absence_zero) if ratt_presentes else (None, 'manquante')
    valeur = normale
    if rattrapage is not None:
        if regle.regle_rattrapage == 'remplace' or normale is None:
            valeur = rattrapage
        else:
            valeur = max(normale, rattrapage)
        statut = 'note'
    return {'valeur': valeur, 'statut': statut, 'normale': normale, 'rattrapage': rattrapage,
            'non_publiees': len(non_publiees), 'nb_sessions': len({n.session_examen_id for n in comptees})}


def moyenne_matiere(moyenne_cc, examen, poids_classe, poids_examen, superieur=False):
    """
    Combine contrôle continu et examen (poids en fraction, ex. 0.4 / 0.6). Renvoie un Decimal ou None.
    Sans examen comptable (absent justifié, non noté) : contrôle continu seul ; sans contrôle continu : examen seul.
    """
    ex = examen.get('valeur') if isinstance(examen, dict) else examen
    cc = Decimal(str(moyenne_cc)) if moyenne_cc is not None else None
    pc, pe = Decimal(str(poids_classe)), Decimal(str(poids_examen))
    if superieur and ex is None:
        # LMD : l'épreuve terminale est obligatoire ; sans elle l'EC n'a pas de moyenne (à rattraper).
        return None
    if cc is None and ex is None:
        return None
    if ex is None:
        return _q(cc)
    if cc is None:
        return _q(ex)
    if pc + pe <= 0:
        return _q((cc + ex) / 2)
    return _q((cc * pc + ex * pe) / (pc + pe))


# --------------------------------------------------------------------------- LMD
def validation_lmd(lignes, regle):
    """
    lignes : [{'matiere', 'moyenne' (Decimal|None), 'coefficient', 'credits'}]
    Renvoie la moyenne du semestre, le détail par UE, les crédits acquis et la décision.
    """
    seuil = Decimal(str(regle.seuil_validation))
    elim = Decimal(str(regle.note_eliminatoire)) if regle.note_eliminatoire is not None else None
    ues = OrderedDict()
    for ln in lignes:
        m = ln['matiere']
        cle = ('ue', m.module_id) if m.module_id else ('ec', m.id)
        ues.setdefault(cle, {'titre': getattr(m.module, 'nom', None) if m.module_id else m.nom, 'lignes': []})
        ues[cle]['lignes'].append(ln)

    incomplet = any(ln.get('moyenne') is None for ln in lignes)
    eliminatoire = bool(elim is not None and any(ln.get('moyenne') is not None and ln['moyenne'] < elim for ln in lignes))
    numer = denom = D0
    resultat_ues = []
    for ue in ues.values():
        ls = [ln for ln in ue['lignes'] if ln.get('moyenne') is not None]
        coef = sum((Decimal(str(ln.get('coefficient') or 1)) for ln in ls), D0)
        credits = sum((Decimal(str(ln.get('credits') or 0)) for ln in ue['lignes']), D0)
        moy = _q(sum((ln['moyenne'] * Decimal(str(ln.get('coefficient') or 1)) for ln in ls), D0) / coef) if coef else None
        ue_elim = bool(elim is not None and any(ln['moyenne'] < elim for ln in ls))
        complete = len(ls) == len(ue['lignes'])
        acquise = bool(moy is not None and complete and moy >= seuil and not ue_elim)
        resultat_ues.append({'titre': ue['titre'], 'moyenne': moy, 'credits': credits, 'acquise': acquise,
                             'mode': 'acquise' if acquise else 'non_acquise', 'eliminatoire': ue_elim})
        if moy is not None:
            poids = credits if credits > 0 else (coef or Decimal('1'))
            numer += moy * poids
            denom += poids
    moyenne_semestre = _q(numer / denom) if denom else None
    compense = bool(regle.compensation_semestrielle and moyenne_semestre is not None and moyenne_semestre >= seuil
                    and not eliminatoire and not incomplet)
    if compense:
        for ue in resultat_ues:
            if not ue['acquise']:
                ue['acquise'], ue['mode'] = True, 'compensee'
    total = sum((ue['credits'] for ue in resultat_ues), D0)
    acquis = sum((ue['credits'] for ue in resultat_ues if ue['acquise']), D0)
    if incomplet and not all(ue['acquise'] for ue in resultat_ues):
        decision = 'Incomplet'
    elif all(ue['acquise'] for ue in resultat_ues):
        decision = 'Admis par compensation' if any(ue['mode'] == 'compensee' for ue in resultat_ues) else 'Admis'
    else:
        decision = 'Ajourné'
    return {'moyenne_semestre': moyenne_semestre, 'ues': resultat_ues, 'credits_total': total,
            'credits_acquis': acquis, 'decision': decision, 'eliminatoire': eliminatoire, 'incomplet': incomplet}


def eleves_eligibles_rattrapage(session, classe, matiere, eleves):
    """Supérieur : seuls les étudiants n'ayant pas validé la matière en 1re session passent le rattrapage."""
    from school_admin.model.moyenne_periode_model import MoyennePeriode

    seuil = Decimal(str(regles(session.etablissement).seuil_validation))
    moyennes = {m.eleve_id: m.moyenne_matiere for m in MoyennePeriode.objects.filter(
        classe=classe, matiere=matiere, periode=session.periode, est_moyenne_generale=False)}
    if not moyennes:
        return set(e.id for e in eleves)  # moyennes pas encore calculées : on ne bloque personne
    return {e.id for e in eleves if moyennes.get(e.id) is None or Decimal(str(moyennes[e.id])) < seuil}


# --------------------------------------------------------------------------- saisie enseignant
def matieres_enseignant(professeur, classe, annee=None):
    """
    Matières que l'enseignant peut noter dans cette classe : celles de ses affectations
    (secondaire / supérieur : une affectation par matière ; primaire : matières de l'affectation).
    Repli pour les données anciennes sans affectation : classe rattachée au professeur
    (matière principale + secondaires). Liste vide = enseignant non affecté à la classe.
    """
    from school_admin.model.affectation_model import AffectationProfesseur
    from school_admin.model.affectation_professeur_primaire_model import AffectationProfesseurPrimaire
    from school_admin.model.matiere_model import Matiere

    ids = set()
    aff = AffectationProfesseur.objects.filter(professeur=professeur, classe=classe, actif=True)
    aff_p = AffectationProfesseurPrimaire.objects.filter(professeur=professeur, classe=classe, actif=True)
    if annee is not None:
        aff = aff.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
        aff_p = aff_p.filter(Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True))
    ids.update(aff.values_list('matiere_id', flat=True))
    for a in aff_p.prefetch_related('matieres'):
        ids.update(m.id for m in a.matieres.all())
    if not ids and professeur.classes.filter(pk=classe.pk).exists():
        if professeur.matiere_principale_id:
            ids.add(professeur.matiere_principale_id)
        ids.update(professeur.matieres_secondaires.values_list('id', flat=True))
    return list(Matiere.objects.filter(id__in=ids).order_by('nom'))


def lire_note_saisie(brut):
    """'' -> None ; 'ABS' / 'abs' -> 'ABS' ; '12,5' -> Decimal('12.5') ; sinon ValueError."""
    brut = (brut or '').strip().replace(',', '.')
    if not brut:
        return None
    if brut.upper() in ('ABS', 'A', 'ABSENT'):
        return 'ABS'
    from decimal import InvalidOperation
    try:
        return Decimal(brut)
    except InvalidOperation:
        raise ValueError(brut)


def enregistrer_saisie(session, classe, matiere, professeur, eleves, saisies, bareme, soumettre=False,
                       eligibles=None):
    """
    Enregistre les notes d'examen d'une classe (tout ou rien).
    saisies : {eleve_id: {'note': str, 'absent': bool, 'justifiee': bool, 'commentaire': str}}
    Renvoie (nb_enregistrees, erreurs). Aucune écriture s'il y a une erreur.
    """
    from django.db import transaction
    from django.utils import timezone
    from school_admin.model.note_examen_model import NoteExamen

    erreurs = []
    try:
        bareme = Decimal(str(bareme).replace(',', '.'))
    except Exception:
        bareme = D0
    if bareme <= 0 or bareme > 100:
        return 0, ["Le barème doit être compris entre 1 et 100."]
    if session.est_annule:
        return 0, ["Cette session est annulée : la saisie est fermée."]

    existantes = {n.eleve_id: n for n in NoteExamen.objects.filter(
        session_examen=session, matiere=matiere, eleve__in=eleves)}
    lignes = []
    for eleve in eleves:
        if eligibles is not None and eleve.id not in eligibles:
            continue
        s = saisies.get(eleve.id, {})
        existante = existantes.get(eleve.id)
        if existante and existante.soumis:
            continue
        try:
            valeur = lire_note_saisie(s.get('note'))
        except ValueError:
            erreurs.append(f"{eleve.nom_complet} : « {s.get('note')} » n'est pas une note valide.")
            continue
        absent = bool(s.get('absent')) or valeur == 'ABS'
        if not absent and valeur is not None and not (D0 <= valeur <= bareme):
            erreurs.append(f"{eleve.nom_complet} : la note doit être comprise entre 0 et {bareme:g}.")
            continue
        if soumettre and not absent and valeur is None:
            erreurs.append(f"{eleve.nom_complet} : note manquante (saisir une note ou cocher Absent).")
            continue
        lignes.append((eleve, existante, None if absent else valeur, absent, bool(s.get('justifiee')) and absent,
                       (s.get('commentaire') or '').strip()))
    if erreurs:
        return 0, erreurs

    nb = 0
    with transaction.atomic():
        for eleve, n, valeur, absent, justifiee, commentaire in lignes:
            if n is None:
                if valeur is None and not absent:
                    continue  # rien saisi
                n = NoteExamen(eleve=eleve, session_examen=session, matiere=matiere)
            n.professeur, n.classe, n.bareme = professeur, classe, bareme
            n.note, n.absent, n.absence_justifiee = valeur, absent, justifiee
            n.annee_scolaire_id = n.annee_scolaire_id or session.annee_scolaire_id
            if commentaire:
                n.commentaire = commentaire
            elif absent:
                n.commentaire = "Absence justifiée" if justifiee else "Absent à l'examen"
            if soumettre:
                n.soumis, n.date_soumission = True, timezone.now()
            n.save()
            nb += 1
    return nb, []
