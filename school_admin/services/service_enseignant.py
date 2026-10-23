"""
Service des enseignants du supérieur en heures équivalent TD (éq. TD).

Heures prévues à partir des emplois du temps actifs : CM / TD / TP par semaine × nombre de semaines
du semestre du créneau (ou semaines de l'année pour un créneau « toute l'année »). Un CM mutualisé
(même enseignant, même matière, même horaire dans plusieurs classes) n'est compté qu'une fois.
Équivalence : CM × coef_cm + TD × coef_td + TP × coef_tp (1,5 / 1 / 0,67 par défaut).
Service dû selon le grade ; au-delà, heures complémentaires payées au taux de l'établissement
(les vacataires sont payés pour toutes leurs heures, à leur tarif horaire s'il est défini).
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

D0 = Decimal('0')


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _semaines(periode):
    if not (periode and periode.date_debut and periode.date_fin):
        return 0
    return max(1, round(((periode.date_fin - periode.date_debut).days + 1) / 7))


def detail_enseignant(professeur, annee, regles=None):
    """Lignes par EC / classe / type, avec heures réelles et éq. TD."""
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps
    from school_admin.model.service_enseignant_model import ReglesService

    regles = regles or ReglesService.pour(professeur.etablissement)
    coef = {'cm': Decimal(str(regles.coef_cm)), 'td': Decimal(str(regles.coef_td)), 'tp': Decimal(str(regles.coef_tp))}
    qs = (CreneauEmploiDuTemps.objects.filter(professeur=professeur, emploi_du_temps__est_actif=True)
          .select_related('matiere', 'emploi_du_temps__classe', 'periode_scolaire', 'groupe'))
    if annee is not None:
        qs = qs.filter(emploi_du_temps__annee_scolaire_fk=annee)
    vus, lignes = set(), OrderedDict()
    for c in qs:
        if not (c.heure_debut and c.heure_fin) or c.type_cours not in ('cours', 'td', 'tp'):
            continue
        cle_type = {'cours': 'cm', 'td': 'td', 'tp': 'tp'}[c.type_cours]
        signature = (c.jour, c.heure_debut, c.heure_fin, c.matiere_id, c.periode_scolaire_id, cle_type,
                     c.groupe_id if cle_type != 'cm' else None)
        mutualise = signature in vus
        vus.add(signature)
        semaines = _semaines(c.periode_scolaire) if c.periode_scolaire_id else regles.semaines_annee
        duree = Decimal(str((datetime.combine(datetime.today(), c.heure_fin)
                             - datetime.combine(datetime.today(), c.heure_debut)) / timedelta(hours=1)))
        heures = D0 if mutualise else duree * semaines
        cle = (c.matiere_id, cle_type)
        ligne = lignes.setdefault(cle, {
            'matiere': c.matiere.nom if c.matiere else 'Sans matière', 'type': cle_type, 'classes': [],
            'heures': D0, 'eqtd': D0, 'semestres': set(), 'mutualise': False,
        })
        classe = c.emploi_du_temps.classe.nom + (f" ({c.groupe.nom})" if c.groupe_id else '')
        if classe not in ligne['classes']:
            ligne['classes'].append(classe)
        ligne['heures'] += heures
        ligne['eqtd'] += heures * coef[cle_type]
        ligne['mutualise'] = ligne['mutualise'] or mutualise
        ligne['semestres'].add(c.periode_scolaire.nom_periode if c.periode_scolaire_id else "Toute l'année")
    resultat = []
    for l in lignes.values():
        l['heures'], l['eqtd'] = _q(l['heures']), _q(l['eqtd'])
        l['semestres'] = ', '.join(sorted(l['semestres']))
        resultat.append(l)
    return resultat


def bilan_enseignant(professeur, annee, regles=None):
    from school_admin.model.service_enseignant_model import ReglesService

    regles = regles or ReglesService.pour(professeur.etablissement)
    lignes = detail_enseignant(professeur, annee, regles)
    par_type = {'cm': D0, 'td': D0, 'tp': D0}
    eqtd = D0
    for l in lignes:
        par_type[l['type']] += l['heures']
        eqtd += l['eqtd']
    du = regles.service_du(professeur)
    vacataire = professeur.type_contrat == 'vacataire' or professeur.grade_universitaire == 'vacataire'
    complementaires = eqtd if vacataire else max(D0, eqtd - du)
    taux = Decimal(str(professeur.prix_volume_horaire or 0)) if vacataire and professeur.prix_volume_horaire \
        else Decimal(str(regles.taux_heure_complementaire or 0))
    statut = 'vacataire' if vacataire else ('sous_service' if eqtd < du else ('equilibre' if eqtd == du else 'complementaires'))
    return {
        'professeur': professeur, 'lignes': lignes, 'cm': _q(par_type['cm']), 'td': _q(par_type['td']),
        'tp': _q(par_type['tp']), 'eqtd': _q(eqtd), 'du': _q(du), 'complementaires': _q(complementaires),
        'taux': _q(taux), 'montant': _q(complementaires * taux), 'statut': statut, 'vacataire': vacataire,
        'pct_service': int(min(200, (eqtd / du * 100))) if du else (100 if eqtd else 0),
        'ecart': _q(eqtd - du),
    }


def synthese(etablissement, annee):
    from school_admin.model.professeur_model import Professeur
    from school_admin.model.service_enseignant_model import ReglesService

    regles = ReglesService.pour(etablissement)
    bilans = [bilan_enseignant(p, annee, regles)
              for p in Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom')]
    alertes = []
    sans_grade = [b for b in bilans if not b['professeur'].grade_universitaire and not b['vacataire']]
    if sans_grade:
        alertes.append(f"{len(sans_grade)} enseignant(s) sans grade : service dû par défaut appliqué.")
    sous = [b for b in bilans if b['statut'] == 'sous_service' and b['eqtd'] > 0]
    if sous:
        alertes.append(f"{len(sous)} enseignant(s) en sous-service par rapport à leur service statutaire.")
    sans_cours = [b for b in bilans if b['eqtd'] == 0]
    if sans_cours:
        alertes.append(f"{len(sans_cours)} enseignant(s) sans aucun cours planifié dans les emplois du temps.")
    return {
        'regles': regles, 'bilans': bilans, 'alertes': alertes,
        'total_eqtd': _q(sum((b['eqtd'] for b in bilans), D0)),
        'total_complementaires': _q(sum((b['complementaires'] for b in bilans), D0)),
        'total_montant': _q(sum((b['montant'] for b in bilans), D0)),
    }
