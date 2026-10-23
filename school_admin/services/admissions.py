"""
Admissions du supérieur : candidatures, dossier, épreuves, classement, listes et inscription.

- note de dossier : moyenne du diplôme précédent (accès en Master…) sinon moyenne du bac ;
- total : dossier seul, épreuves seules (moyenne coefficientée) ou mixte (poids du dossier) ;
- éliminé : absent à une épreuve ou note sous la note éliminatoire de l'épreuve ;
- classement décroissant (ex æquo départagés par la moyenne du bac), au-dessus du seuil :
  liste principale (places), puis liste d'attente, puis non admis ;
- désistement d'un admis : le premier de la liste d'attente est admis automatiquement ;
- inscription d'un admis : dossier d'inscription créé par le circuit de préinscription existant
  (matricule, inscription annuelle, facturation), l'étudiant rejoint la classe d'admission.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from school_admin.model.admission_model import Candidature, Concours, NoteConcours

D0 = Decimal('0')
CLASSABLES = ('recevable', 'admis', 'attente', 'refuse')


class AdmissionErreur(Exception):
    pass


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def numeroter(candidature):
    if candidature.numero:
        return candidature.numero
    c = candidature.concours
    n = Candidature.objects.filter(concours=c).exclude(pk=candidature.pk).count() + 1
    code = (c.etablissement.code_etablissement or 'ADM').split('-')[0][:6]
    candidature.numero = f"{code}-{c.annee_scolaire.annee_debut}-{c.id:03d}-{n:04d}"
    return candidature.numero


def note_dossier(candidature):
    c = candidature
    if c.concours.diplome_requis in ('licence', 'master') and c.moyenne_diplome is not None:
        return _q(c.moyenne_diplome)
    if c.moyenne_bac is not None:
        return _q(c.moyenne_bac)
    if c.moyenne_diplome is not None:
        return _q(c.moyenne_diplome)
    return None


def resultat_epreuves(candidature, epreuves=None):
    """(moyenne /20 ou None, éliminé: bool, motif)."""
    epreuves = list(epreuves if epreuves is not None else candidature.concours.epreuves.all())
    if not epreuves:
        return None, False, ''
    notes = {n.epreuve_id: n for n in candidature.notes.all()}
    num = den = D0
    for e in epreuves:
        n = notes.get(e.id)
        if n is None or (n.note is None and not n.absent):
            return None, False, f"Note manquante : {e.nom}"
        if n.absent:
            return None, True, f"Absent à l'épreuve « {e.nom} »"
        if e.note_eliminatoire is not None and n.note < e.note_eliminatoire:
            return _q(n.note), True, f"Note éliminatoire en {e.nom} ({n.note:g} < {e.note_eliminatoire:g})"
        num += n.note * e.coefficient
        den += e.coefficient
    return (_q(num / den) if den else None), False, ''


def calculer(concours):
    """Calcule totaux, rangs et listes. Renvoie les statistiques."""
    epreuves = list(concours.epreuves.all())
    cands = list(concours.candidatures.filter(statut__in=CLASSABLES + ('inscrit',)).prefetch_related('notes'))
    pd = Decimal(concours.poids_dossier) / 100 if concours.mode == 'mixte' else None
    seuil = Decimal(str(concours.seuil_admission))
    classes, non_classes = [], []
    with transaction.atomic():
        for c in cands:
            c.note_dossier = note_dossier(c)
            ep, elimine, motif = resultat_epreuves(c, epreuves) if concours.mode != 'dossier' else (None, False, '')
            if concours.mode == 'dossier':
                total = c.note_dossier
                motif = '' if total is not None else 'Moyenne du dossier manquante'
            elif concours.mode == 'concours':
                total = ep
            else:
                total = (_q(c.note_dossier * pd + ep * (1 - pd))
                         if c.note_dossier is not None and ep is not None else None)
                if c.note_dossier is None and not motif:
                    motif = 'Moyenne du dossier manquante'
            c.total = total
            if c.statut == 'inscrit':
                classes.append(c)
            elif elimine or total is None or total < seuil:
                c.motif = motif or (f"Total {total:g} sous le seuil de {seuil:g}" if total is not None else c.motif)
                non_classes.append(c)
            else:
                classes.append(c)
        classes.sort(key=lambda c: (-(c.total or D0), -(c.moyenne_bac or D0), c.nom, c.prenom))
        rang_prec, total_prec = 0, None
        places = concours.places
        attente = concours.places_attente
        for i, c in enumerate(classes, start=1):
            c.rang = rang_prec if c.total == total_prec else i
            rang_prec, total_prec = c.rang, c.total
            if c.statut != 'inscrit':
                if i <= places:
                    c.statut, c.motif = 'admis', ''
                elif i <= places + attente:
                    c.statut, c.motif = 'attente', ''
                else:
                    c.statut, c.motif = 'refuse', "Classé au-delà des places et de la liste d'attente"
            c.save()
        for c in non_classes:
            c.rang, c.statut = None, 'refuse'
            c.save()
    return statistiques(concours)


def statistiques(concours):
    qs = concours.candidatures.all()
    par = {code: qs.filter(statut=code).count() for code, _ in Candidature.STATUT_CHOICES}
    totaux = [c.total for c in qs.filter(statut__in=('admis', 'inscrit')) if c.total is not None]
    return {
        'total': qs.count(), 'par_statut': par,
        'admis': par['admis'] + par['inscrit'], 'attente': par['attente'],
        'barre': min(totaux) if totaux else None,
        'taux_remplissage': round(100 * (par['admis'] + par['inscrit']) / concours.places) if concours.places else 0,
    }


def enregistrer_notes(concours, saisies):
    """saisies : {(candidature_id, epreuve_id): 'note' | 'ABS' | ''}. Renvoie les erreurs (tout ou rien)."""
    epreuves = {e.id: e for e in concours.epreuves.all()}
    cands = {c.id: c for c in concours.candidatures.all()}
    erreurs, a_ecrire = [], []
    for (cid, eid), brut in saisies.items():
        if cid not in cands or eid not in epreuves:
            continue
        brut = (brut or '').strip().replace(',', '.')
        if not brut:
            a_ecrire.append((cid, eid, None, False))
            continue
        if brut.upper() == 'ABS':
            a_ecrire.append((cid, eid, None, True))
            continue
        try:
            v = Decimal(brut)
        except Exception:
            erreurs.append(f"{cands[cid].nom_complet} — {epreuves[eid].nom} : « {brut} » n'est pas une note.")
            continue
        if not (D0 <= v <= 20):
            erreurs.append(f"{cands[cid].nom_complet} — {epreuves[eid].nom} : la note va de 0 à 20.")
            continue
        a_ecrire.append((cid, eid, v, False))
    if erreurs:
        return erreurs
    with transaction.atomic():
        for cid, eid, v, absent in a_ecrire:
            NoteConcours.objects.update_or_create(candidature_id=cid, epreuve_id=eid,
                                                  defaults={'note': v, 'absent': absent})
    return []


def desister(candidature):
    """Désistement d'un admis : le premier de la liste d'attente prend la place. Renvoie le promu (ou None)."""
    if candidature.statut not in ('admis', 'attente'):
        raise AdmissionErreur("Seul un candidat admis ou en liste d'attente peut se désister.")
    etait_admis = candidature.statut == 'admis'
    with transaction.atomic():
        candidature.statut, candidature.motif = 'desiste', 'Désistement'
        candidature.save()
        if not etait_admis:
            return None
        suivant = (candidature.concours.candidatures.filter(statut='attente')
                   .order_by('rang', 'nom').first())
        if suivant:
            suivant.statut, suivant.motif = 'admis', "Admis sur liste d'attente (désistement)"
            suivant.save()
        return suivant


def inscrire(candidature, classe=None, validateur=None):
    """Crée le dossier d'inscription de l'étudiant admis (circuit de préinscription existant)."""
    from school_admin.model.preinscription_model import PreinscriptionEleve

    c = candidature
    if c.statut != 'admis':
        raise AdmissionErreur("Seul un candidat admis peut être inscrit.")
    classe = classe or c.concours.classe_cible
    if classe is None:
        raise AdmissionErreur("Choisissez la classe d'inscription.")
    etab = c.concours.etablissement
    from school_admin.model.preinscription_model import LienPreinscription

    with transaction.atomic():
        lien, _ = LienPreinscription.objects.get_or_create(etablissement=etab)
        pre = PreinscriptionEleve.objects.create(
            lien_preinscription=lien, etablissement=etab, nom=c.nom, prenom=c.prenom, date_naissance=c.date_naissance,
            lieu_naissance=c.lieu_naissance, sexe=c.sexe, nationalite=c.nationalite, adresse=c.adresse or '-',
            classe_souhaitee=classe,
            parent_nom=c.contact_nom or c.nom, parent_prenom=c.contact_prenom or c.prenom,
            parent_telephone=c.contact_telephone or c.telephone, parent_adresse=c.adresse or '',
            parent_lien=c.contact_lien or 'autre',
            commentaires_etablissement=f"Admis — {c.concours.intitule} (candidature {c.numero})",
        )
        eleve, _parent = pre.valider(validateur or etab, f"Admission {c.numero}", classe=classe,
                                     statut_inscription='nouvelle', date_inscription=timezone.localdate())
        c.eleve, c.statut = eleve, 'inscrit'
        c.save()
    return eleve
