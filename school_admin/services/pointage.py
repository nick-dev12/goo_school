"""
Pointage des enseignants et paie au réel.

Principe
  * Chaque cours de l'emploi du temps publié devient, chaque jour, une séance.
  * L'enseignant ouvre sa séance en scannant le QR d'une borne de l'école : ce QR
    change toutes les 30 secondes, il est donc impossible de le scanner depuis chez soi.
  * À la fin du cours, l'enseignant clôt la séance (cahier de texte). Aria vérifie
    l'appel et cherche les anomalies. Séance sans anomalie → validée automatiquement ;
    sinon → « à vérifier » par le censeur ou le surveillant.
  * La paie ne compte que les séances validées (ou remplacées, au profit du remplaçant).
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from school_admin.model.pointage_model import BornePointage, SeanceCours

FENETRE_QR = 30            # secondes de validité d'un QR
OUVERTURE_AVANT = 10       # minutes : on peut ouvrir la séance 10 min avant le début
OUVERTURE_APRES = 15       # minutes : au-delà de 15 min de retard, l'ouverture est refusée
CLOTURE_AUTO_APRES = 30    # minutes après la fin : une séance restée ouverte est close automatiquement
DUREE_MIN_PCT = 50         # une séance close avant la moitié de sa durée est suspecte
SEMAINES_PAR_MOIS = Decimal('4.33')
ZERO = Decimal('0')

LIBELLES_ANOMALIES = {
    'sans_qr': "Ouverte sans scanner le QR de la borne",
    'retard': "Ouverte avec plus de 15 minutes de retard",
    'sans_appel': "Aucun appel enregistré pendant la séance",
    'appel_hors_seance': "Appel fait en dehors de l'horaire de la séance",
    'cahier_vide': "Cahier de texte non rempli",
    'trop_courte': "Close avant la moitié de la durée prévue",
    'chevauchement': "Une autre séance du même enseignant était ouverte au même moment",
    'cloture_auto': "Séance non close par l'enseignant",
}


# --------------------------------------------------------------------------- QR tournant
def _fenetre(instant=None):
    return int((instant if instant is not None else time.time()) // FENETRE_QR)


def code_borne(borne, fenetre=None):
    """Code à 6 chiffres de la borne pour une fenêtre de 30 s (HMAC du secret)."""
    fenetre = _fenetre() if fenetre is None else fenetre
    digest = hmac.new(borne.secret.encode(), str(fenetre).encode(), hashlib.sha256).hexdigest()
    return f"{int(digest[:12], 16) % 1_000_000:06d}"


def contenu_qr(borne, fenetre=None):
    return f"ARIA-POINTAGE:{borne.pk}:{code_borne(borne, fenetre)}"


def secondes_restantes(instant=None):
    instant = instant if instant is not None else time.time()
    return FENETRE_QR - int(instant % FENETRE_QR)


def verifier_code(etablissement, saisie, instant=None):
    """Borne correspondant au QR scanné (ou au code tapé), fenêtre courante ou précédente. Sinon None."""
    saisie = (saisie or '').strip()
    borne_id = None
    code = saisie
    if saisie.startswith('ARIA-POINTAGE:'):
        try:
            _p, borne_id, code = saisie.split(':', 2)
        except ValueError:
            return None
    if not code.isdigit() or len(code) != 6:
        return None
    bornes = BornePointage.objects.filter(etablissement=etablissement, actif=True)
    if borne_id:
        bornes = bornes.filter(pk=borne_id)
    f = _fenetre(instant)
    for borne in bornes:
        for fenetre in (f, f - 1):
            if hmac.compare_digest(code_borne(borne, fenetre), code):
                return borne
    return None


# --------------------------------------------------------------------------- mise en service
def date_activation(etablissement):
    """Le pointage commence le jour de création de la première borne. Avant : ancienne méthode."""
    premiere = BornePointage.objects.filter(etablissement=etablissement).order_by('date_creation').first()
    return timezone.localtime(premiere.date_creation).date() if premiere else None


def preparer_periode(etablissement, du, au, annee_scolaire=None):
    """Crée les séances de la période (à partir de la mise en service) puis met les statuts à jour."""
    activation = date_activation(etablissement)
    if activation is None:
        return None
    debut = max(du, activation)
    fin = min(au, timezone.localdate() + timedelta(days=7))
    if debut <= fin:
        generer_seances(etablissement, debut, fin, annee_scolaire)
    actualiser(etablissement)
    return activation


# --------------------------------------------------------------------------- génération
def creneaux_publies(etablissement, annee_scolaire=None, professeur=None):
    from school_admin.model.emploi_du_temps_model import CreneauEmploiDuTemps

    qs = CreneauEmploiDuTemps.objects.filter(
        emploi_du_temps__classe__etablissement=etablissement,
        professeur__isnull=False,
        emploi_du_temps__est_actif=True,
        emploi_du_temps__statut_publication='publie',
    ).exclude(type_cours='pause')
    if professeur is not None:
        qs = qs.filter(professeur=professeur)
    if annee_scolaire is not None:
        qs = qs.filter(Q(emploi_du_temps__annee_scolaire_fk=annee_scolaire)
                       | Q(emploi_du_temps__annee_scolaire_fk__isnull=True,
                           emploi_du_temps__annee_scolaire=annee_scolaire.libelle))
    return qs.select_related('professeur', 'matiere', 'emploi_du_temps__classe', 'periode_etablissement')


JOURS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')


def generer_seances(etablissement, du, au, annee_scolaire=None):
    """Crée les séances manquantes entre deux dates à partir de l'EDT publié. Idempotent."""
    creneaux = [c for c in creneaux_publies(etablissement, annee_scolaire)
                if not (c.periode_etablissement and getattr(c.periode_etablissement, 'est_pause', False))]
    if not creneaux:
        return 0
    existants = set(SeanceCours.objects.filter(etablissement=etablissement, date__gte=du, date__lte=au)
                    .values_list('creneau_id', 'date'))
    a_creer = []
    jour = du
    while jour <= au:
        nom = JOURS[jour.weekday()]
        for c in creneaux:
            if c.jour != nom or (c.id, jour) in existants:
                continue
            debut = c.heure_debut or (c.periode_etablissement.heure_debut if c.periode_etablissement else None)
            fin = c.heure_fin or (c.periode_etablissement.heure_fin if c.periode_etablissement else None)
            classe = getattr(c.emploi_du_temps, 'classe', None)
            if not debut or not fin or classe is None:
                continue
            a_creer.append(SeanceCours(
                etablissement=etablissement, annee_scolaire=annee_scolaire, professeur=c.professeur,
                classe=classe, matiere=c.matiere, creneau=c, date=jour, heure_debut=debut, heure_fin=fin,
            ))
        jour += timedelta(days=1)
    SeanceCours.objects.bulk_create(a_creer, ignore_conflicts=True)
    return len(a_creer)


def _dt(jour, heure):
    return timezone.make_aware(datetime.combine(jour, heure), timezone.get_current_timezone())


def actualiser(etablissement, maintenant=None):
    """Séances jamais ouvertes → non faites ; séances restées ouvertes → closes automatiquement."""
    maintenant = maintenant or timezone.now()
    local = timezone.localtime(maintenant)
    today = local.date()
    for s in SeanceCours.objects.filter(etablissement=etablissement, statut='prevue', date__lte=today):
        if _dt(s.date, s.heure_fin) < maintenant:
            s.statut = 'absente'
            s.save(update_fields=['statut'])
    for s in SeanceCours.objects.filter(etablissement=etablissement, statut='en_cours', date__lte=today):
        if _dt(s.date, s.heure_fin) + timedelta(minutes=CLOTURE_AUTO_APRES) < maintenant:
            terminer(s, s.cahier_texte, maintenant=_dt(s.date, s.heure_fin), auto=True)


# --------------------------------------------------------------------------- côté enseignant
def fenetre_ouverture(seance):
    debut = _dt(seance.date, seance.heure_debut)
    return debut - timedelta(minutes=OUVERTURE_AVANT), debut + timedelta(minutes=OUVERTURE_APRES)


def peut_ouvrir(seance, maintenant=None):
    maintenant = maintenant or timezone.now()
    ouverture, limite = fenetre_ouverture(seance)
    fin = _dt(seance.date, seance.heure_fin)
    return seance.statut == 'prevue' and ouverture <= maintenant <= fin, maintenant > limite


def commencer(seance, professeur, saisie_qr='', sans_qr_motif='', maintenant=None):
    maintenant = maintenant or timezone.now()
    if seance.professeur_id != professeur.id:
        raise ValueError("Cette séance n'est pas la vôtre.")
    ok, en_retard = peut_ouvrir(seance, maintenant)
    if seance.statut != 'prevue':
        raise ValueError("Cette séance a déjà été ouverte ou n'est plus modifiable.")
    if not ok:
        ouverture, _l = fenetre_ouverture(seance)
        raise ValueError(f"La séance s'ouvre à partir de {timezone.localtime(ouverture):%H:%M}, "
                         f"jusqu'à la fin du cours ({seance.heure_fin:%H:%M}).")
    borne = None
    if saisie_qr:
        borne = verifier_code(seance.etablissement, saisie_qr)
        if borne is None:
            raise ValueError("QR invalide ou expiré. Scannez le QR affiché sur la borne à l'instant.")
    elif not (sans_qr_motif or '').strip():
        raise ValueError("Scannez le QR de la borne, ou indiquez pourquoi vous ne pouvez pas le faire.")
    anomalies = []
    if borne is None:
        anomalies.append('sans_qr')
    if en_retard:
        anomalies.append('retard')
    autre = SeanceCours.objects.filter(professeur=professeur, statut='en_cours', date=seance.date).exclude(pk=seance.pk)
    if autre.exists():
        anomalies.append('chevauchement')
    seance.statut = 'en_cours'
    seance.debut_reel = maintenant
    seance.preuve_qr = borne is not None
    seance.borne = borne
    seance.motif_sans_qr = (sans_qr_motif or '').strip()[:200]
    seance.anomalies = anomalies
    seance.save(update_fields=['statut', 'debut_reel', 'preuve_qr', 'borne', 'motif_sans_qr', 'anomalies'])
    if borne:
        BornePointage.objects.filter(pk=borne.pk).update(derniere_activite=maintenant)
    return seance


def _appel(seance, fin):
    """Élèves notés à l'appel par cet enseignant, pour cette classe, ce jour-là."""
    from school_admin.model.presence_model import Presence

    qs = Presence.objects.filter(professeur=seance.professeur, classe=seance.classe, date=seance.date)
    total = qs.count()
    if not total:
        return 0, False
    debut = timezone.localtime(seance.debut_reel or _dt(seance.date, seance.heure_debut))
    fin = timezone.localtime(fin)
    marge = timedelta(minutes=5)
    dans = qs.filter(heure_enregistrement__gte=(debut - marge).time(),
                     heure_enregistrement__lte=(fin + marge).time()).count()
    return total, dans > 0


def terminer(seance, cahier_texte='', maintenant=None, auto=False):
    """Clôt la séance, contrôle l'appel et décide : validée automatiquement ou à vérifier."""
    maintenant = maintenant or timezone.now()
    if seance.statut != 'en_cours':
        raise ValueError("Cette séance n'est pas en cours.")
    anomalies = [a for a in (seance.anomalies or []) if a in LIBELLES_ANOMALIES]
    nb, dans_seance = _appel(seance, maintenant)
    if not nb:
        anomalies.append('sans_appel')
    elif not dans_seance:
        anomalies.append('appel_hors_seance')
    cahier = (cahier_texte or '').strip()
    if not cahier:
        anomalies.append('cahier_vide')
    if seance.debut_reel:
        duree_reelle = (maintenant - seance.debut_reel).total_seconds() / 60
        if duree_reelle < seance.duree_minutes * DUREE_MIN_PCT / 100:
            anomalies.append('trop_courte')
    if auto:
        anomalies.append('cloture_auto')
    anomalies = list(dict.fromkeys(anomalies))
    confiance = 100
    poids = {'sans_qr': 45, 'retard': 10, 'sans_appel': 35, 'appel_hors_seance': 20, 'cahier_vide': 10,
             'trop_courte': 25, 'chevauchement': 40, 'cloture_auto': 10}
    for a in anomalies:
        confiance -= poids.get(a, 10)
    seance.fin_reelle = maintenant
    seance.cahier_texte = cahier
    seance.appel_fait = nb > 0
    seance.nb_eleves_appel = nb
    seance.anomalies = anomalies
    seance.confiance = max(confiance, 0)
    if not anomalies:
        seance.statut = 'validee'
        seance.validation_auto = True
        seance.valide_par = 'Validation automatique'
        seance.valide_le = maintenant
    else:
        seance.statut = 'a_verifier'
    seance.save()
    if cahier:
        from school_admin.services.cahier_texte import entree_depuis_seance

        entree_depuis_seance(seance)
    return seance


def contester(seance, professeur, motif):
    if seance.professeur_id != professeur.id:
        raise ValueError("Cette séance n'est pas la vôtre.")
    if seance.statut != 'absente' or seance.paie_id:
        raise ValueError("Seule une séance marquée « non faite » et non payée peut être contestée.")
    motif = (motif or '').strip()
    if len(motif) < 10:
        raise ValueError("Expliquez en quelques mots pourquoi le cours a bien eu lieu.")
    seance.statut = 'contestee'
    seance.motif_contestation = motif[:2000]
    seance.save(update_fields=['statut', 'motif_contestation'])
    return seance


# --------------------------------------------------------------------------- côté direction
def _acteur(user):
    nom = getattr(user, 'nom_complet', '') or f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}".strip()
    if not nom:
        nom = getattr(user, 'nom', '') or str(user)
    fonction = getattr(user, 'get_fonction_display', None)
    return f"{nom} ({fonction()})" if callable(fonction) else f"{nom} (direction)"


def decider(seance, user, decision, commentaire='', remplacant=None):
    """Décision humaine : valider, refuser (non faite), justifier l'absence ou affecter un remplaçant."""
    if seance.paie_id:
        raise ValueError("Cette séance a déjà été payée : elle ne peut plus changer.")
    maintenant = timezone.now()
    if decision == 'valider':
        if seance.statut not in ('a_verifier', 'contestee', 'absente', 'en_cours'):
            raise ValueError("Seule une séance à vérifier, contestée ou non faite peut être validée.")
        seance.statut = 'validee'
    elif decision == 'refuser':
        seance.statut = 'absente'
        seance.absence_justifiee = False
    elif decision == 'justifier':
        seance.statut = 'absente'
        seance.absence_justifiee = True
    elif decision == 'remplacer':
        if remplacant is None or remplacant.id == seance.professeur_id:
            raise ValueError("Choisissez l'enseignant qui a assuré le cours.")
        seance.statut = 'remplacee'
        seance.remplacant = remplacant
    elif decision == 'annuler':
        seance.statut = 'annulee'
    else:
        raise ValueError("Décision inconnue.")
    seance.validation_auto = False
    seance.valide_par = _acteur(user)[:120]
    seance.valide_le = maintenant
    seance.commentaire_validation = (commentaire or '').strip()[:255]
    seance.save()
    return seance


# --------------------------------------------------------------------------- paie
def _q(x, quantum='0.01'):
    return Decimal(x).quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


@dataclass
class CalculPaie:
    professeur: object
    type_contrat: str
    du: date
    au: date
    minutes_prevues: int = 0
    minutes_validees: int = 0
    minutes_remplacements: int = 0
    minutes_absentes: int = 0
    minutes_absentes_justifiees: int = 0
    minutes_a_verifier: int = 0
    nb_seances_payees: int = 0
    taux_horaire: Decimal | None = None
    salaire_base: Decimal = ZERO
    heures_sup: Decimal = ZERO
    montant_heures_sup: Decimal = ZERO
    retenue_absences: Decimal = ZERO
    brut: Decimal | None = None
    seances_payees: list = field(default_factory=list)
    minutes_avant_pointage: int = 0
    minutes_a_venir: int = 0
    activation: date | None = None

    @property
    def minutes_payables(self):
        return self.minutes_validees + self.minutes_remplacements + self.minutes_avant_pointage

    @property
    def heures_validees(self):
        return _q(Decimal(self.minutes_payables) / 60)

    @property
    def heures_prevues(self):
        return _q(Decimal(self.minutes_prevues) / 60)

    @property
    def taux_realisation(self):
        if not self.minutes_prevues:
            return None
        return round(self.minutes_payables / self.minutes_prevues * 100)


def _minutes_avant_pointage(professeur, du, au, annee_scolaire=None):
    """Ancienne méthode, pour les jours antérieurs au pointage : EDT − absences saisies + remplacements."""
    from django.db.models import Sum

    from school_admin.model.caisse_etablissement_model import AbsenceEnseignant
    from school_admin.utils.volume_horaire import minutes_planifiees_periode, occurrences_jours

    if du > au:
        return 0, 0
    creneaux = list(creneaux_publies(professeur.etablissement, annee_scolaire, professeur=professeur))
    prevues = minutes_planifiees_periode(creneaux, occurrences_jours(du, au))
    absences = AbsenceEnseignant.objects.filter(professeur=professeur, date__gte=du, date__lte=au)
    rempl = AbsenceEnseignant.objects.filter(remplacant=professeur, date__gte=du, date__lte=au)
    minutes_abs = absences.aggregate(s=Sum('minutes'))['s'] or 0
    minutes_rempl = rempl.aggregate(s=Sum('minutes'))['s'] or 0
    return prevues, max(prevues - minutes_abs, 0) + minutes_rempl


def calculer_paie(professeur, du, au, annee_scolaire=None, activation=None):
    """Paie de la période : séances validées depuis la mise en service, ancienne méthode avant."""
    c = CalculPaie(professeur=professeur, type_contrat=professeur.type_contrat or 'vacataire', du=du, au=au,
                   activation=activation)
    if activation is None or activation > du:
        fin_ancien = au if activation is None else min(au, activation - timedelta(days=1))
        prevues, payables = _minutes_avant_pointage(professeur, du, fin_ancien, annee_scolaire)
        c.minutes_prevues += prevues
        c.minutes_avant_pointage = payables
        du_seances = activation if activation else au + timedelta(days=1)
    else:
        du_seances = du
    seances = list(SeanceCours.objects.filter(professeur=professeur, date__gte=du_seances, date__lte=au)
                   .exclude(statut='annulee'))
    remplacements = list(SeanceCours.objects.filter(remplacant=professeur, statut='remplacee',
                                                    date__gte=du_seances, date__lte=au))
    for s in seances:
        if s.statut == 'prevue':
            c.minutes_a_venir += s.duree_minutes
            continue
        c.minutes_prevues += s.duree_minutes
        if s.statut == 'validee':
            c.minutes_validees += s.duree_minutes
            if not s.paie_id:
                c.seances_payees.append(s)
        elif s.statut == 'absente':
            if s.absence_justifiee:
                c.minutes_absentes_justifiees += s.duree_minutes
            else:
                c.minutes_absentes += s.duree_minutes
        elif s.statut in ('a_verifier', 'contestee', 'en_cours'):
            c.minutes_a_verifier += s.duree_minutes
        elif s.statut == 'remplacee':
            c.minutes_absentes_justifiees += s.duree_minutes
    for s in remplacements:
        c.minutes_remplacements += s.duree_minutes
        if not s.paie_id:
            c.seances_payees.append(s)
    c.nb_seances_payees = len(c.seances_payees)
    taux = professeur.prix_volume_horaire
    if c.type_contrat == 'permanent':
        salaire = professeur.salaire_mensuel
        if salaire is None:
            return c
        c.salaire_base = _q(salaire)
        if taux is None and professeur.heures_contrat_semaine:
            taux = salaire / (Decimal(professeur.heures_contrat_semaine) * SEMAINES_PAR_MOIS)
        c.taux_horaire = _q(taux) if taux is not None else None
        if c.taux_horaire is not None:
            c.retenue_absences = _q(Decimal(c.minutes_absentes) / 60 * c.taux_horaire)
            if professeur.heures_contrat_semaine:
                contrat_minutes = int(Decimal(professeur.heures_contrat_semaine) * 60
                                      * Decimal((au - du).days + 1) / 7)
                sup = max(c.minutes_payables - contrat_minutes, 0)
                c.heures_sup = _q(Decimal(sup) / 60)
                c.montant_heures_sup = _q(c.heures_sup * c.taux_horaire)
        c.brut = max(c.salaire_base - c.retenue_absences + c.montant_heures_sup, ZERO)
    else:
        if taux is None:
            return c
        c.taux_horaire = _q(taux)
        c.brut = _q(c.heures_validees * c.taux_horaire)
    return c


def enregistrer_paie(calcul, etablissement, annee_scolaire=None, retenue_pct=ZERO, compte_tresorerie=None, user=None):
    """Crée la paie de la période, rattache les séances et passe l'écriture comptable."""
    from school_admin.model.caisse_etablissement_model import PaieProfesseurPeriode
    from school_admin.services.caisse import net_apres_retenue

    if calcul.brut is None:
        raise ValueError("Renseignez d'abord le tarif horaire ou le salaire sur la fiche de l'enseignant.")
    if calcul.minutes_a_verifier:
        raise ValueError("Des séances sont encore à vérifier sur cette période : traitez-les avant de payer.")
    if PaieProfesseurPeriode.objects.filter(professeur=calcul.professeur, date_debut=calcul.du,
                                            date_fin=calcul.au).exists():
        raise ValueError("Cette période est déjà payée.")
    with transaction.atomic():
        paie = PaieProfesseurPeriode.objects.create(
            etablissement=etablissement, professeur=calcul.professeur, annee_scolaire=annee_scolaire,
            date_debut=calcul.du, date_fin=calcul.au, heures=calcul.heures_validees,
            montant_brut=calcul.brut, retenue_pct=retenue_pct,
            montant_net=net_apres_retenue(calcul.brut, retenue_pct),
            type_contrat=calcul.type_contrat, nb_seances=calcul.nb_seances_payees,
            salaire_base=calcul.salaire_base, heures_sup=calcul.heures_sup,
            montant_heures_sup=calcul.montant_heures_sup, retenue_absences=calcul.retenue_absences,
            compte_tresorerie=compte_tresorerie,
            enregistre_par=user if user.__class__.__name__ == 'CompteUser' else None,
        )
        SeanceCours.objects.filter(pk__in=[s.pk for s in calcul.seances_payees]).update(paie=paie)
        from school_admin.services.comptabilite_generale import pont_paie

        pont_paie(paie, annee_scolaire=annee_scolaire, user=user)
    return paie


# --------------------------------------------------------------------------- tableaux de bord
def resume_jour(etablissement, jour):
    qs = SeanceCours.objects.filter(etablissement=etablissement, date=jour)
    out = {k: 0 for k, _l in SeanceCours.STATUT_CHOICES}
    for statut in qs.values_list('statut', flat=True):
        out[statut] = out.get(statut, 0) + 1
    out['total'] = sum(v for k, v in out.items())
    return out


def libelles_anomalies(seance):
    return [LIBELLES_ANOMALIES.get(a, a) for a in (seance.anomalies or [])]
