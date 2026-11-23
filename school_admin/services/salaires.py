"""
Salaires et paiements du mois — toutes les personnes payées par l'établissement.

Une seule source par donnée :
- enseignants : contrat de leur fiche (vacataire au prix de l'heure, ou salaire mensuel) et séances de
  l'emploi du temps pointées (services/pointage) — absences non justifiées non payées, remplacements payés
  au remplaçant ; le versement crée la paie de la période (PaieProfesseurPeriode) et son écriture comptable ;
- personnel administratif : salaire de base de son dossier, ou prix de l'heure × heures saisies au paiement
  (le personnel n'est pas pointé) ; le versement est une sortie de caisse « Salaire ».
Les agents payés par l'État (prise_en_charge = 'etat') n'entrent pas dans cette paie.
C'est le seul endroit où l'on paie : « Volume horaire » sert à contrôler les séances.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

D0 = Decimal('0')
MOIS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre',
           'novembre', 'décembre']


def _q(x):
    return Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def fmt(montant):
    return f"{Decimal(montant or 0):,.0f}".replace(',', ' ')


def fmt_h(heures):
    d = Decimal(heures or 0).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP).normalize()
    return f"{d:f}".replace('.', ',') + ' h'


def libelle_mois(jour):
    return f"{MOIS_FR[jour.month - 1]} {jour.year}"


def premier_du_mois(jour):
    return date(jour.year, jour.month, 1)


@dataclass
class LignePaie:
    type: str                   # 'enseignant' ou 'personnel'
    personne: object
    nom: str
    role: str
    initiales: str
    mode: str                   # 'fixe' (salaire mensuel) ou 'heure'
    montant: Decimal | None     # montant dû du mois ; None si à saisir (personnel à l'heure) ou impossible
    statut: str                 # 'paye', 'a_payer', 'a_saisir', 'a_renseigner', 'a_verifier', 'rien'
    explication: list = field(default_factory=list)   # lignes de calcul lisibles
    bloque: str = ''            # raison pour laquelle on ne peut pas payer
    lien_bloque: str = ''       # où régler le blocage
    taux: Decimal | None = None
    paye_le: date | None = None
    montant_paye: Decimal | None = None


def _periode(annee_scolaire, mois):
    from school_admin.utils.volume_horaire import resoudre_periode

    return resoudre_periode('mois', reference=mois, annee_scolaire=annee_scolaire)


def _calcul_enseignant(prof, du, au, annee_scolaire, activation):
    from school_admin.services import pointage as pt

    return pt.calculer_paie(prof, du, au, annee_scolaire, activation)


def _explication_enseignant(prof, c):
    lignes = []
    h = lambda minutes: fmt_h(Decimal(minutes) / 60)  # noqa: E731
    if c.type_contrat == 'permanent':
        if c.salaire_base:
            lignes.append(f"Salaire mensuel : {fmt(c.salaire_base)}")
        if c.minutes_absentes:
            lignes.append(f"− {h(c.minutes_absentes)} d’absence non justifiée : −{fmt(c.retenue_absences)}")
        if c.montant_heures_sup:
            lignes.append(f"+ {fmt_h(c.heures_sup)} au-delà du contrat : +{fmt(c.montant_heures_sup)}")
        if c.minutes_prevues:
            lignes.append(f"Cours faits : {fmt_h(c.heures_validees)} sur {fmt_h(c.heures_prevues)} prévues")
    else:
        if c.taux_horaire is not None:
            lignes.append(f"{fmt_h(c.heures_validees)} faites × {fmt(c.taux_horaire)} / h")
        else:
            lignes.append(f"{fmt_h(c.heures_validees)} faites")
        if c.minutes_prevues:
            lignes.append(f"sur {fmt_h(c.heures_prevues)} prévues dans l’emploi du temps")
        if c.minutes_absentes:
            lignes.append(f"{h(c.minutes_absentes)} d’absence non justifiée : non payée(s)")
    if c.minutes_remplacements:
        lignes.append(f"dont {h(c.minutes_remplacements)} de remplacement")
    if c.minutes_absentes_justifiees:
        lignes.append(f"{h(c.minutes_absentes_justifiees)} d’absence justifiée")
    if c.minutes_a_venir:
        lignes.append(f"{h(c.minutes_a_venir)} encore à venir ce mois")
    return lignes


def paie_du_mois(etablissement, annee_scolaire, mois, url_resolver=None):
    """Lignes de paie du mois (date du 1er) et totaux."""
    from school_admin.model.caisse_etablissement_model import PaiePersonnelMois, PaieProfesseurPeriode
    from school_admin.model.personnel_administratif_model import PersonnelAdministratif
    from school_admin.model.professeur_model import Professeur
    from school_admin.services import pointage as pt

    url = url_resolver or (lambda *a, **k: '')
    mois = premier_du_mois(mois)
    periode = _periode(annee_scolaire, mois)
    du, au = periode.date_debut, periode.date_fin
    lignes = []

    profs = list(Professeur.objects.filter(etablissement=etablissement, actif=True).order_by('nom', 'prenom'))
    payables = [p for p in profs if p.prise_en_charge != 'etat']
    activation = pt.preparer_periode(etablissement, du, au, annee_scolaire) if payables else None
    payes = {}
    for paie in PaieProfesseurPeriode.objects.filter(etablissement=etablissement, professeur__in=payables,
                                                     date_debut__lte=au, date_fin__gte=du):
        payes.setdefault(paie.professeur_id, paie)
    for p in payables:
        c = _calcul_enseignant(p, du, au, annee_scolaire, activation)
        permanent = c.type_contrat == 'permanent'
        paie = payes.get(p.id)
        lien_contrat = url('directeur:detail_volume_horaire', p.id) + f"?periode=mois&mois={mois:%Y-%m}"
        ligne = LignePaie(
            type='enseignant', personne=p, nom=p.nom_complet, initiales=(p.prenom[:1] + p.nom[:1]).upper(),
            role=('Enseignant · salaire mensuel' if permanent else 'Enseignant · payé à l’heure'),
            mode='fixe' if permanent else 'heure', montant=c.brut, statut='a_payer',
            explication=_explication_enseignant(p, c), taux=c.taux_horaire,
        )
        if c.minutes_avant_pointage or (activation is None and c.minutes_prevues):
            # Avant la mise en service du pointage : emploi du temps moins les absences saisies.
            ligne.explication.append("Pointage pas encore en service : heures de l’emploi du temps, "
                                     "moins les absences saisies")
            if au >= date.today():
                ligne.explication.append(f"Mois pas encore terminé : heures prévues comptées jusqu’au {au:%d/%m}")
        if paie:
            ligne.statut, ligne.paye_le, ligne.montant_paye = 'paye', paie.date_paiement.date(), paie.montant_net
        elif c.brut is None:
            ligne.statut = 'a_renseigner'
            ligne.bloque = "Salaire mensuel à indiquer sur sa fiche" if permanent else "Prix de l’heure à indiquer sur sa fiche"
            ligne.lien_bloque = lien_contrat
        elif c.minutes_a_verifier:
            ligne.statut = 'a_verifier'
            ligne.bloque = f"{fmt_h(Decimal(c.minutes_a_verifier) / 60)} de séances à vérifier avant de payer"
            ligne.lien_bloque = lien_contrat
        elif not c.brut:
            ligne.statut = 'rien'
            ligne.bloque = "Aucune heure faite ce mois"
        lignes.append(ligne)

    personnels = list(PersonnelAdministratif.objects.filter(etablissement=etablissement, actif=True)
                      .select_related('dossier_complementaire').order_by('nom', 'prenom'))
    payes_perso = {pp.personnel_id: pp for pp in PaiePersonnelMois.objects.filter(etablissement=etablissement, mois=mois)}
    for pers in personnels:
        if pers.prise_en_charge == 'etat':
            continue
        dossier = getattr(pers, 'dossier_complementaire', None)
        salaire = getattr(dossier, 'salaire_base', None) if dossier else None
        taux = pers.prix_volume_horaire
        ligne = LignePaie(
            type='personnel', personne=pers, nom=pers.nom_complet, initiales=(pers.prenom[:1] + pers.nom[:1]).upper(),
            role=pers.get_fonction_display(), mode='fixe' if salaire or not taux else 'heure',
            montant=salaire if salaire else None, statut='a_payer', taux=taux,
        )
        if salaire:
            ligne.explication = [f"Salaire mensuel : {fmt(salaire)}"]
        elif taux:
            ligne.explication = [f"Payé à l’heure : {fmt(taux)} / h", "Les heures du mois se saisissent au paiement"]
        paie = payes_perso.get(pers.id)
        if paie:
            ligne.statut, ligne.paye_le, ligne.montant_paye = 'paye', paie.date_paiement, paie.montant
        elif not salaire and not taux:
            ligne.statut = 'a_renseigner'
            ligne.bloque = "Salaire de base ou prix de l’heure à indiquer dans son dossier"
            ligne.lien_bloque = url('personnel:detail_personnel', pers.id) + '?onglet=dossier'
        elif not salaire:
            ligne.statut = 'a_saisir'
        lignes.append(ligne)

    etat = (sum(1 for p in profs if p.prise_en_charge == 'etat')
            + sum(1 for p in personnels if p.prise_en_charge == 'etat'))
    pretes = [l for l in lignes if l.statut == 'a_payer' and l.montant]
    return {
        'mois': mois, 'libelle_mois': libelle_mois(mois), 'du': du, 'au': au, 'lignes': lignes, 'agents_etat': etat,
        'reste_a_verser': sum((l.montant for l in pretes), D0),
        'deja_verse': sum((l.montant_paye or D0) for l in lignes if l.statut == 'paye'),
        'pretes': pretes, 'total_pretes': sum((l.montant for l in pretes), D0),
        'compteurs': {
            'enseignant': sum(1 for l in lignes if l.type == 'enseignant'),
            'personnel': sum(1 for l in lignes if l.type == 'personnel'),
            'a_payer': sum(1 for l in lignes if l.statut in ('a_payer', 'a_saisir', 'a_verifier')),
            'paye': sum(1 for l in lignes if l.statut == 'paye'),
            'a_renseigner': sum(1 for l in lignes if l.statut == 'a_renseigner'),
        },
    }


# --------------------------------------------------------------------------- paiements
def payer_enseignant(etablissement, professeur, mois, annee_scolaire=None, retenue_pct=D0, compte_tresorerie=None,
                     user=None):
    """Paie du mois d'un enseignant : séances validées (pointage) au tarif de son contrat."""
    from school_admin.services import pointage as pt

    if professeur.etablissement_id != etablissement.id:
        raise ValueError("Enseignant introuvable.")
    if professeur.prise_en_charge == 'etat':
        raise ValueError(f"{professeur.nom_complet} est payé par l’État : pas de salaire versé par l’école.")
    periode = _periode(annee_scolaire, premier_du_mois(mois))
    activation = pt.preparer_periode(etablissement, periode.date_debut, periode.date_fin, annee_scolaire)
    calcul = pt.calculer_paie(professeur, periode.date_debut, periode.date_fin, annee_scolaire, activation)
    if not calcul.brut:
        raise ValueError(f"Rien à payer à {professeur.nom_complet} pour ce mois."
                         if calcul.brut is not None else "Renseignez d’abord le tarif sur la fiche de l’enseignant.")
    retenue = min(max(Decimal(str(retenue_pct or 0)), D0), Decimal('100'))
    return pt.enregistrer_paie(calcul, etablissement, annee_scolaire, retenue, compte_tresorerie=compte_tresorerie,
                               user=user)


def payer_personnel(etablissement, personnel, mois, montant=None, jour=None, annee_scolaire=None, user=None,
                    heures=None, compte_tresorerie=None):
    """Salaire du mois d'un membre du personnel : sortie de caisse « Salaire » + trace du mois payé.

    Payé à l'heure (sans salaire de base) : montant = heures saisies × prix de l'heure de sa fiche.
    """
    from school_admin.model.caisse_etablissement_model import PaiePersonnelMois
    from school_admin.services.finances.operations import enregistrer_sortie

    if personnel.etablissement_id != etablissement.id:
        raise ValueError("Membre du personnel introuvable.")
    if personnel.prise_en_charge == 'etat':
        raise ValueError(f"{personnel.nom_complet} est payé par l’État : pas de salaire versé par l’école.")
    precision = ''
    if heures not in (None, ''):
        heures = Decimal(str(heures).replace(',', '.'))
        if heures <= 0 or not personnel.prix_volume_horaire:
            raise ValueError("Indiquez un nombre d’heures, et le prix de l’heure sur sa fiche.")
        montant = _q(heures * Decimal(str(personnel.prix_volume_horaire)))
        precision = f" ({fmt_h(heures)} × {fmt(personnel.prix_volume_horaire)})"
    montant = Decimal(str(montant or 0))
    if montant <= 0:
        raise ValueError("Indiquez un montant supérieur à 0.")
    mois = premier_du_mois(mois)
    if PaiePersonnelMois.objects.filter(personnel=personnel, mois=mois).exists():
        raise ValueError(f"Le salaire de {libelle_mois(mois)} de {personnel.nom_complet} est déjà versé.")
    jour = jour or date.today()
    with transaction.atomic():
        depense, _ecriture = enregistrer_sortie(
            etablissement, jour, 'salaire', montant,
            libelle=f"Salaire {mois:%m/%Y} — {personnel.nom_complet}{precision}"[:160],
            annee_scolaire=annee_scolaire, user=user, compte_tresorerie=compte_tresorerie,
        )
        return PaiePersonnelMois.objects.create(
            etablissement=etablissement, personnel=personnel, mois=mois, montant=montant, depense=depense,
            date_paiement=jour,
            enregistre_par=user if user is not None and user.__class__.__name__ == 'CompteUser' else None,
        )


def payer_tout(etablissement, annee_scolaire, mois, retenue_pct=D0, compte_tresorerie=None, user=None):
    """Paie en une fois toutes les personnes dont le montant du mois est prêt. Renvoie (payés, ignorés)."""
    paie = paie_du_mois(etablissement, annee_scolaire, mois)
    payes, ignores = [], []
    for l in paie['lignes']:
        if l.statut == 'paye':
            continue
        if not (l.statut == 'a_payer' and l.montant):
            ignores.append((l.nom, l.bloque or ("Heures du mois à saisir" if l.statut == 'a_saisir' else "Rien à payer")))
            continue
        try:
            if l.type == 'enseignant':
                payer_enseignant(etablissement, l.personne, mois, annee_scolaire, retenue_pct, compte_tresorerie, user)
            else:
                payer_personnel(etablissement, l.personne, mois, l.montant, annee_scolaire=annee_scolaire, user=user,
                                compte_tresorerie=compte_tresorerie)
        except ValueError as exc:
            ignores.append((l.nom, str(exc)))
        else:
            payes.append((l.nom, l.montant))
    return payes, ignores


# --------------------------------------------------------------------------- historique
def historique(etablissement, type_personne, personne_id, url_resolver=None):
    """Paiements d'une personne, du plus récent au plus ancien, regroupés par mois."""
    from school_admin.model.caisse_etablissement_model import PaiePersonnelMois, PaieProfesseurPeriode

    url = url_resolver or (lambda *a, **k: '')
    mois = OrderedDict()
    total = D0
    if type_personne == 'enseignant':
        qs = (PaieProfesseurPeriode.objects.filter(etablissement=etablissement, professeur_id=personne_id)
              .select_related('compte_tresorerie').order_by('-date_debut'))
        for p in qs:
            cle = premier_du_mois(p.date_debut)
            mois.setdefault(cle, []).append({
                'paye_le': p.date_paiement.date().strftime('%d/%m/%Y'), 'montant': fmt(p.montant_net),
                'detail': (f"{fmt_h(p.heures)} · brut {fmt(p.montant_brut)}"
                           + (f" · charges {p.retenue_pct.normalize():f} %" if p.retenue_pct else '')),
                'moyen': p.compte_tresorerie.libelle if p.compte_tresorerie_id else 'Caisse',
                'fiche': url('directeur:fiche_paie_directeur', personne_id) + f"?periode=mois&mois={cle:%Y-%m}",
            })
            total += p.montant_net
    else:
        qs = (PaiePersonnelMois.objects.filter(etablissement=etablissement, personnel_id=personne_id)
              .select_related('depense__compte_tresorerie').order_by('-mois'))
        for p in qs:
            compte = getattr(p.depense, 'compte_tresorerie', None) if p.depense_id else None
            mois.setdefault(p.mois, []).append({
                'paye_le': p.date_paiement.strftime('%d/%m/%Y'), 'montant': fmt(p.montant),
                'detail': (p.depense.libelle if p.depense_id else ''), 'moyen': compte.libelle if compte else 'Caisse',
                'fiche': '',
            })
            total += p.montant
    return {
        'total': fmt(total), 'nb': sum(len(v) for v in mois.values()),
        'mois': [{'mois': libelle_mois(m), 'paiements': v} for m, v in mois.items()],
    }
