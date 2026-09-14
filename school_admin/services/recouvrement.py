"""
Recouvrement Vague 1 : relances SMS/WhatsApp, reçus, remise fratrie, impayés, moratoires.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')
CENTIME = Decimal('0.01')


def _dec(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Decimal) -> Decimal:
    return _dec(value).quantize(CENTIME, rounding=ROUND_HALF_UP)


def devise_etablissement(etablissement) -> str:
    if etablissement and getattr(etablissement, 'devise_monnaie', None):
        devise = etablissement.devise_monnaie.strip()
        if devise:
            return devise
    return 'FCFA'


# ---------------------------------------------------------------------------
# Réduction fratrie
# ---------------------------------------------------------------------------

@dataclass
class RemiseFratrie:
    applicable: bool
    nombre_enfants: int
    pourcentage: Decimal
    montant_brut: Decimal
    montant_remise: Decimal
    montant_net: Decimal


def compter_enfants_famille(eleve, etablissement) -> int:
    """
    Compte les enfants actifs du même établissement liés à la même famille.
    Sources : LienFamilial validé, puis repli sur le téléphone parent.
    """
    from school_admin.model.eleve_model import Eleve
    from school_admin.model.lien_familial_model import LienFamilial

    ids = {eleve.id}
    parent_ids = list(
        LienFamilial.objects.filter(
            eleve=eleve,
            actif=True,
            statut='valide',
        ).values_list('parent_id', flat=True)
    )
    if parent_ids:
        sibling_ids = LienFamilial.objects.filter(
            parent_id__in=parent_ids,
            actif=True,
            statut='valide',
            eleve__etablissement=etablissement,
            eleve__actif=True,
        ).values_list('eleve_id', flat=True)
        ids.update(sibling_ids)

    telephone = (getattr(eleve, 'parent_telephone', None) or '').strip()
    if telephone:
        ids.update(
            Eleve.objects.filter(
                etablissement=etablissement,
                actif=True,
                parent_telephone=telephone,
            ).values_list('id', flat=True)
        )
    return max(len(ids), 1)


def calculer_remise_fratrie(montant_brut, parametres, nombre_enfants: int) -> RemiseFratrie:
    """Calcule la remise sans toucher la base. Testable unitairement."""
    brut = _q(_dec(montant_brut))
    flag = bool(getattr(parametres, 'appliquer_remise_famille_nombreuse', False)) if parametres else False
    pourcentage = _dec(getattr(parametres, 'pourcentage_remise_famille_nombreuse', 0) if parametres else 0)
    minimum = int(getattr(parametres, 'nombre_enfants_minimum_remise', 3) or 3) if parametres else 3

    applicable = flag and pourcentage > ZERO and nombre_enfants >= minimum
    if not applicable:
        return RemiseFratrie(
            applicable=False,
            nombre_enfants=nombre_enfants,
            pourcentage=ZERO,
            montant_brut=brut,
            montant_remise=ZERO,
            montant_net=brut,
        )
    remise = _q(brut * pourcentage / Decimal('100'))
    if remise > brut:
        remise = brut
    return RemiseFratrie(
        applicable=True,
        nombre_enfants=nombre_enfants,
        pourcentage=pourcentage,
        montant_brut=brut,
        montant_remise=remise,
        montant_net=_q(brut - remise),
    )


def appliquer_remise_sur_charge(charge, parametres, nombre_enfants: int) -> RemiseFratrie:
    """
    Applique (ou retire) la remise fratrie sur une charge non payée.
    Ne touche pas une charge déjà partiellement ou totalement payée.
    """
    brut = _dec(getattr(charge, 'montant_brut', None) or charge.montant)
    resultat = calculer_remise_fratrie(brut, parametres, nombre_enfants)
    paye = _dec(getattr(charge, 'montant_paye', ZERO))
    if paye > ZERO:
        return resultat

    update_fields = []
    if getattr(charge, 'montant_brut', None) in (None, ZERO) or charge.montant_brut != resultat.montant_brut:
        charge.montant_brut = resultat.montant_brut
        update_fields.append('montant_brut')
    if charge.montant != resultat.montant_net:
        charge.montant = resultat.montant_net
        update_fields.append('montant')
    if getattr(charge, 'remise_fratrie', None) != resultat.montant_remise:
        charge.remise_fratrie = resultat.montant_remise
        update_fields.append('remise_fratrie')
    if hasattr(charge, 'reste_a_payer'):
        reste = resultat.montant_net - paye
        charge.reste_a_payer = reste if reste > ZERO else ZERO
        update_fields.append('reste_a_payer')
    if update_fields:
        charge.save(update_fields=update_fields)
    return resultat


def synchroniser_remises_fratrie_eleve(eleve, etablissement, annee_scolaire, parametres) -> RemiseFratrie:
    from school_admin.model.comptabilite_eleve_model import FraisInscription, Mensualite

    nombre = compter_enfants_famille(eleve, etablissement)
    temoin = calculer_remise_fratrie(Decimal('100'), parametres, nombre)

    for frais in FraisInscription.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        montant_paye=ZERO,
    ):
        appliquer_remise_sur_charge(frais, parametres, nombre)

    for mensualite in Mensualite.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        montant_paye=ZERO,
    ):
        appliquer_remise_sur_charge(mensualite, parametres, nombre)

    return temoin


def synchroniser_remises_fratrie_etablissement(etablissement, annee_scolaire) -> int:
    """Applique la remise fratrie à tous les élèves inscrits de l'année."""
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    inscriptions = InscriptionEleve.objects.filter(
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        eleve__isnull=False,
        eleve__actif=True,
    ).select_related('eleve', 'classe')
    count = 0
    for inscription in inscriptions:
        parametres = ComptabiliteController._get_parametres_for_classe(
            etablissement, inscription.classe
        ) if inscription.classe else None
        if parametres is None:
            continue
        synchroniser_remises_fratrie_eleve(
            inscription.eleve, etablissement, annee_scolaire, parametres
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Dette élève / parent
# ---------------------------------------------------------------------------

@dataclass
class ChargeDue:
    libelle: str
    montant: Decimal
    montant_paye: Decimal
    reste: Decimal
    date_echeance: Optional[date]
    statut: str
    kind: str
    objet_id: int


@dataclass
class ResumeDette:
    total_du: Decimal = ZERO
    total_paye: Decimal = ZERO
    reste: Decimal = ZERO
    prochaine_echeance: Optional[date] = None
    prochaine_libelle: str = ''
    charges: list = field(default_factory=list)
    statut: str = 'a_jour'


def _charges_ouvertes(eleve, etablissement, annee_scolaire) -> list[ChargeDue]:
    from school_admin.model.comptabilite_eleve_model import (
        FraisAnnexe,
        FraisInscription,
        Mensualite,
    )
    from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire

    charges: list[ChargeDue] = []
    moratoire_actif = Moratoire.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        statut='actif',
    ).first()

    if moratoire_actif:
        for echeance in moratoire_actif.echeances.all().order_by('numero'):
            reste = echeance.get_reste_a_payer()
            charges.append(
                ChargeDue(
                    libelle=f"Moratoire échéance {echeance.numero}",
                    montant=_dec(echeance.montant),
                    montant_paye=_dec(echeance.montant_paye),
                    reste=reste,
                    date_echeance=echeance.date_echeance,
                    statut=echeance.statut,
                    kind='moratoire',
                    objet_id=echeance.id,
                )
            )
        return charges

    for frais in FraisInscription.objects.filter(
        eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
    ):
        reste = frais.get_reste_a_payer()
        charges.append(
            ChargeDue(
                libelle=frais.get_type_frais_display(),
                montant=_dec(frais.montant),
                montant_paye=_dec(frais.montant_paye),
                reste=reste,
                date_echeance=frais.date_echeance,
                statut=frais.statut,
                kind='inscription',
                objet_id=frais.id,
            )
        )
    for mensualite in Mensualite.objects.filter(
        eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
    ).order_by('annee', 'mois'):
        reste = mensualite.get_reste_a_payer()
        charges.append(
            ChargeDue(
                libelle=mensualite.periode or f"Mensualité {mensualite.mois}/{mensualite.annee}",
                montant=_dec(mensualite.montant),
                montant_paye=_dec(mensualite.montant_paye),
                reste=reste,
                date_echeance=mensualite.date_echeance,
                statut=mensualite.statut,
                kind='mensualite',
                objet_id=mensualite.id,
            )
        )
    for frais in FraisAnnexe.objects.filter(
        eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
    ):
        reste = frais.get_reste_a_payer()
        charges.append(
            ChargeDue(
                libelle=frais.libelle,
                montant=_dec(frais.montant),
                montant_paye=_dec(frais.montant_paye),
                reste=reste,
                date_echeance=frais.date_echeance,
                statut=frais.statut,
                kind='annexe',
                objet_id=frais.id,
            )
        )
    return charges


def resume_dette_eleve(eleve, etablissement, annee_scolaire) -> ResumeDette:
    charges = _charges_ouvertes(eleve, etablissement, annee_scolaire)
    total_du = sum((c.montant for c in charges), ZERO)
    total_paye = sum((c.montant_paye for c in charges), ZERO)
    reste = sum((c.reste for c in charges), ZERO)
    ouvertes = [c for c in charges if c.reste > ZERO and c.date_echeance]
    ouvertes.sort(key=lambda c: c.date_echeance)
    prochaine = ouvertes[0] if ouvertes else None
    statut = 'a_jour'
    if reste > ZERO:
        today = timezone.now().date()
        if prochaine and prochaine.date_echeance < today:
            statut = 'impaye' if prochaine.statut == 'impaye' else 'en_retard'
        else:
            statut = 'en_attente'
    return ResumeDette(
        total_du=_q(total_du),
        total_paye=_q(total_paye),
        reste=_q(reste),
        prochaine_echeance=prochaine.date_echeance if prochaine else None,
        prochaine_libelle=prochaine.libelle if prochaine else '',
        charges=charges,
        statut=statut,
    )


def parametres_rappels_pour_eleve(eleve, etablissement, annee_scolaire):
    from school_admin.controllers.comptabilite_controller import ComptabiliteController
    from school_admin.model.inscription_eleve_model import InscriptionEleve
    from school_admin.model.parametres_comptabilite_model import ParametresComptabilite

    inscription = InscriptionEleve.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
    ).select_related('classe').first()
    if inscription and inscription.classe:
        parametres = ComptabiliteController._get_parametres_for_classe(
            etablissement, inscription.classe
        )
        if parametres:
            return parametres, inscription
    try:
        return ParametresComptabilite.objects.get(etablissement=etablissement), inscription
    except ParametresComptabilite.DoesNotExist:
        return None, inscription


# ---------------------------------------------------------------------------
# Reçu officiel
# ---------------------------------------------------------------------------

def formater_numero_recu(annee_debut: int, numero: int) -> str:
    return f"REC-{annee_debut}-{numero:05d}"


def attribuer_numero_recu(paiement) -> str:
    """Attribue un numéro séquentiel unique (établissement + année). Idempotent."""
    if paiement.numero_recu:
        return paiement.numero_recu
    from school_admin.model.recouvrement_model import CompteurRecuPaiement

    annee = paiement.annee_scolaire
    with transaction.atomic():
        compteur, _ = CompteurRecuPaiement.objects.select_for_update().get_or_create(
            etablissement=paiement.etablissement,
            annee_scolaire=annee,
            defaults={'dernier_numero': 0},
        )
        compteur.dernier_numero += 1
        compteur.save(update_fields=['dernier_numero'])
        numero = formater_numero_recu(annee.annee_debut, compteur.dernier_numero)
        paiement.numero_recu = numero
        paiement.save(update_fields=['numero_recu'])
    return numero


# ---------------------------------------------------------------------------
# Relances SMS / WhatsApp
# ---------------------------------------------------------------------------

def telephones_relance(eleve) -> list[str]:
    """Numéros parents (liens familiaux) puis téléphone tuteur sur la fiche élève."""
    from school_admin.model.lien_familial_model import LienFamilial

    numeros = []
    seen = set()
    liens = LienFamilial.objects.filter(
        eleve=eleve, actif=True, statut='valide'
    ).select_related('parent')
    for lien in liens:
        tel = (getattr(lien.parent, 'telephone', None) or '').strip()
        if tel and tel not in seen:
            seen.add(tel)
            numeros.append(tel)
    tel_fiche = (getattr(eleve, 'parent_telephone', None) or '').strip()
    if tel_fiche and tel_fiche not in seen:
        numeros.append(tel_fiche)
    return numeros


def construire_message_relance(eleve, resume: ResumeDette, etablissement) -> str:
    devise = devise_etablissement(etablissement)
    nom_ecole = getattr(etablissement, 'nom', 'l\'établissement')
    nom_eleve = getattr(eleve, 'nom_complet', None) or f"{eleve.nom} {eleve.prenom}"
    reste = _q(resume.reste)
    if resume.prochaine_echeance:
        echeance = resume.prochaine_echeance.strftime('%d/%m/%Y')
        detail = f"Échéance : {echeance}"
        if resume.prochaine_libelle:
            detail = f"{resume.prochaine_libelle} — {detail}"
    else:
        detail = "Aucune échéance à venir."
    return (
        f"{nom_ecole} — Scolarité de {nom_eleve}. "
        f"Vous devez {reste} {devise}. {detail} "
        f"Merci de régulariser auprès de l'administration."
    )


def _envoyer_wasender(telephone: str, message: str) -> tuple[bool, str]:
    """Envoie via Wasender si le client est configuré. Ne lève pas."""
    try:
        from school_admin.services.wasender_api import WasenderApiClient

        client = WasenderApiClient()
        response = client.send_text_message(phone_number=telephone, message=message)
        if response.is_success:
            return True, ''
        return False, str(response.body)
    except Exception as exc:
        logger.warning("Relance Wasender impossible: %s", exc)
        return False, str(exc)


def _notifier_parents_scolarite(eleve, titre: str, message: str, resume: ResumeDette):
    try:
        from school_admin.services.parent_notification_service import ParentNotificationService

        ParentNotificationService._dispatch(
            eleve,
            'scolarite',
            titre,
            message,
            payload={
                'reste': str(resume.reste),
                'echeance': resume.prochaine_echeance.isoformat() if resume.prochaine_echeance else '',
            },
        )
    except Exception:
        logger.exception("Notification in-app scolarité impossible pour l'élève %s", eleve.id)


def _deja_relance_aujourdhui(eleve, annee_scolaire) -> bool:
    from school_admin.model.recouvrement_model import RelanceImpaye

    debut = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return RelanceImpaye.objects.filter(
        eleve=eleve,
        annee_scolaire=annee_scolaire,
        date_envoi__gte=debut,
        statut__in=['envoye', 'partiel'],
    ).exists()


def eleve_eligible_relance_auto(resume: ResumeDette, parametres, aujourdhui: date) -> bool:
    """Rappel avant échéance ou après retard, selon les délais paramétrés."""
    if resume.reste <= ZERO:
        return False
    if not parametres or not getattr(parametres, 'envoyer_rappels_automatiques', False):
        return False
    jours_avant = int(getattr(parametres, 'jours_avant_rappel', 7) or 7)
    jours_apres = int(getattr(parametres, 'jours_apres_retard_rappel', 3) or 3)
    if not resume.prochaine_echeance:
        return False
    delta = (resume.prochaine_echeance - aujourdhui).days
    if 0 <= delta <= jours_avant:
        return True
    if delta < 0 and abs(delta) >= jours_apres:
        return True
    return False


def envoyer_relance_eleve(
    eleve,
    etablissement,
    annee_scolaire,
    *,
    declenche_par: str = 'manuel',
    user=None,
    ignorer_doublon_jour: bool = False,
):
    from school_admin.model.recouvrement_model import RelanceImpaye

    resume = resume_dette_eleve(eleve, etablissement, annee_scolaire)
    if resume.reste <= ZERO:
        return None
    if declenche_par == 'automatique' and not ignorer_doublon_jour and _deja_relance_aujourdhui(eleve, annee_scolaire):
        return None

    message = construire_message_relance(eleve, resume, etablissement)
    numeros = telephones_relance(eleve)
    envois_ok = 0
    erreurs = []
    telephone_utilise = numeros[0] if numeros else ''
    canal = 'in_app'

    for numero in numeros:
        ok, err = _envoyer_wasender(numero, message)
        if ok:
            envois_ok += 1
            canal = 'whatsapp'
            telephone_utilise = numero
        else:
            erreurs.append(f"{numero}: {err}")

    _notifier_parents_scolarite(
        eleve,
        "Scolarité — reste à payer",
        message,
        resume,
    )

    if envois_ok and not erreurs:
        statut = 'envoye'
        canal = 'whatsapp'
    elif envois_ok:
        statut = 'partiel'
        canal = 'whatsapp'
    else:
        statut = 'envoye'
        canal = 'in_app'

    relance = RelanceImpaye.objects.create(
        etablissement=etablissement,
        eleve=eleve,
        annee_scolaire=annee_scolaire,
        telephone=telephone_utilise,
        canal=canal,
        statut=statut,
        declenche_par=declenche_par,
        message=message,
        montant_du=resume.reste,
        date_echeance=resume.prochaine_echeance,
        erreur='\n'.join(erreurs)[:2000],
        enregistre_par=user if getattr(user, 'pk', None) else None,
    )
    return relance


def envoyer_relances_automatiques(aujourdhui: Optional[date] = None) -> dict:
    """Parcourt les établissements dont le flag rappels est actif."""
    from school_admin.model.annee_scolaire_model import AnneeScolaire
    from school_admin.model.etablissement_model import Etablissement
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    aujourdhui = aujourdhui or timezone.now().date()
    stats = {'etablissements': 0, 'envoyees': 0, 'ignorees': 0, 'erreurs': 0}

    for etablissement in Etablissement.objects.filter(actif=True, module_comptabilite=True):
        annee = AnneeScolaire.get_session_active(etablissement)
        if not annee:
            continue
        stats['etablissements'] += 1
        inscriptions = InscriptionEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee,
            eleve__isnull=False,
            eleve__actif=True,
        ).select_related('eleve', 'classe')
        for inscription in inscriptions:
            try:
                parametres, _ = parametres_rappels_pour_eleve(
                    inscription.eleve, etablissement, annee
                )
                resume = resume_dette_eleve(inscription.eleve, etablissement, annee)
                if not eleve_eligible_relance_auto(resume, parametres, aujourdhui):
                    stats['ignorees'] += 1
                    continue
                relance = envoyer_relance_eleve(
                    inscription.eleve,
                    etablissement,
                    annee,
                    declenche_par='automatique',
                )
                if relance:
                    stats['envoyees'] += 1
                else:
                    stats['ignorees'] += 1
            except Exception:
                logger.exception("Relance auto en échec élève %s", inscription.eleve_id)
                stats['erreurs'] += 1
    return stats


# ---------------------------------------------------------------------------
# Tableau impayés
# ---------------------------------------------------------------------------

def collecter_impayes_par_classe(etablissement, annee_scolaire) -> list[dict]:
    from school_admin.model.inscription_eleve_model import InscriptionEleve

    groupes: dict[str, dict] = {}
    inscriptions = InscriptionEleve.objects.filter(
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        eleve__isnull=False,
        eleve__actif=True,
    ).select_related('eleve', 'classe').order_by('classe__nom', 'eleve__nom', 'eleve__prenom')

    for inscription in inscriptions:
        resume = resume_dette_eleve(inscription.eleve, etablissement, annee_scolaire)
        if resume.reste <= ZERO:
            continue
        today = timezone.now().date()
        en_retard = bool(
            resume.prochaine_echeance and resume.prochaine_echeance < today
        )
        if not en_retard and resume.statut == 'en_attente':
            # On liste aussi les restes dus (pas uniquement le retard) pour le recouvrement.
            pass
        classe = inscription.classe
        key = str(classe.id) if classe else 'sans-classe'
        if key not in groupes:
            groupes[key] = {
                'classe': classe,
                'classe_nom': classe.nom if classe else 'Sans classe',
                'classe_id': classe.id if classe else None,
                'eleves': [],
                'total_reste': ZERO,
            }
        groupes[key]['eleves'].append({
            'eleve': inscription.eleve,
            'inscription': inscription,
            'resume': resume,
            'en_retard': en_retard,
        })
        groupes[key]['total_reste'] += resume.reste

    return list(groupes.values())


# ---------------------------------------------------------------------------
# Moratoire
# ---------------------------------------------------------------------------

def moratoire_actif(eleve, etablissement, annee_scolaire):
    from school_admin.model.recouvrement_model import Moratoire

    return Moratoire.objects.filter(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        statut='actif',
    ).prefetch_related('echeances').first()


def creer_moratoire(eleve, etablissement, annee_scolaire, motif: str, echeances: Iterable[dict], user=None):
    """
    echeances: iterable of {'date': date, 'montant': Decimal}
    La somme doit égaler le reste dû (hors moratoire existant).
    """
    from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve
    from school_admin.model.recouvrement_model import EcheanceMoratoire, Moratoire

    if moratoire_actif(eleve, etablissement, annee_scolaire):
        raise ValueError("Un moratoire actif existe déjà pour cet élève.")

    lignes = list(echeances)
    if len(lignes) < 2:
        raise ValueError("Le moratoire doit contenir au moins deux échéances.")

    resume = resume_dette_eleve(eleve, etablissement, annee_scolaire)
    if resume.reste <= ZERO:
        raise ValueError("Aucun reste à payer : moratoire inutile.")

    total_lignes = _q(sum((_dec(l['montant']) for l in lignes), ZERO))
    if total_lignes != _q(resume.reste):
        raise ValueError(
            f"La somme des échéances ({total_lignes}) doit égaler le reste dû ({_q(resume.reste)})."
        )

    comptabilite, _ = ComptabiliteEleve.objects.get_or_create(
        eleve=eleve,
        etablissement=etablissement,
        annee_scolaire=annee_scolaire,
        defaults={'statut_paiement': 'en_retard'},
    )

    with transaction.atomic():
        moratoire = Moratoire.objects.create(
            eleve=eleve,
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            comptabilite_eleve=comptabilite,
            motif=motif.strip(),
            montant_total=total_lignes,
            statut='actif',
            cree_par=user if getattr(user, 'pk', None) else None,
        )
        for index, ligne in enumerate(lignes, start=1):
            EcheanceMoratoire.objects.create(
                moratoire=moratoire,
                numero=index,
                date_echeance=ligne['date'],
                montant=_q(_dec(ligne['montant'])),
            )
    return moratoire


def verifier_rupture_moratoire(moratoire, aujourdhui: Optional[date] = None) -> bool:
    """Rompt le moratoire si une échéance non soldée a dépassé sa date."""
    from school_admin.model.recouvrement_model import Moratoire

    aujourdhui = aujourdhui or timezone.now().date()
    if moratoire.statut != 'actif':
        return False

    rompu = False
    toutes_payees = True
    for echeance in moratoire.echeances.all():
        if echeance.est_totalement_paye():
            continue
        toutes_payees = False
        if echeance.date_echeance < aujourdhui:
            echeance.statut = 'impaye'
            echeance.save(update_fields=['statut'])
            rompu = True
        elif echeance.date_echeance == aujourdhui:
            echeance.statut = 'en_retard'
            echeance.save(update_fields=['statut'])

    if rompu:
        moratoire.statut = 'rompu'
        moratoire.date_rupture = timezone.now()
        moratoire.motif_rupture = "Échéance impayée : rupture automatique du moratoire."
        moratoire.save(update_fields=['statut', 'date_rupture', 'motif_rupture'])
        return True
    if toutes_payees:
        moratoire.statut = 'solde'
        moratoire.save(update_fields=['statut'])
    return False


def verifier_rupture_moratoires(etablissement=None, aujourdhui: Optional[date] = None) -> int:
    from school_admin.model.recouvrement_model import Moratoire

    qs = Moratoire.objects.filter(statut='actif').prefetch_related('echeances')
    if etablissement:
        qs = qs.filter(etablissement=etablissement)
    rompus = 0
    for moratoire in qs:
        if verifier_rupture_moratoire(moratoire, aujourdhui=aujourdhui):
            rompus += 1
    return rompus


def _repartir_sur_charges_origine(eleve, etablissement, annee_scolaire, montant: Decimal, *, user=None, mode_paiement='especes', notes=''):
    """Répercute un versement moratoire sur les charges d'origine (FIFO) + reçus."""
    from school_admin.model.comptabilite_eleve_model import (
        FraisAnnexe,
        FraisInscription,
        Mensualite,
        PaiementEleve,
    )

    restant = _dec(montant)
    files = []
    files.extend(
        list(FraisInscription.objects.filter(
            eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
        ).order_by('date_echeance'))
    )
    files.extend(
        list(Mensualite.objects.filter(
            eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
        ).order_by('annee', 'mois'))
    )
    files.extend(
        list(FraisAnnexe.objects.filter(
            eleve=eleve, etablissement=etablissement, annee_scolaire=annee_scolaire
        ).order_by('date_echeance'))
    )
    enregistre_par = user if getattr(user, 'pk', None) else None
    for charge in files:
        if restant <= ZERO:
            break
        due = charge.get_reste_a_payer()
        if due <= ZERO:
            continue
        verse = due if due <= restant else restant
        charge.ajouter_paiement(verse)
        kwargs = {
            'eleve': eleve,
            'etablissement': etablissement,
            'annee_scolaire': annee_scolaire,
            'montant': verse,
            'mode_paiement': mode_paiement,
            'notes': notes,
            'enregistre_par': enregistre_par,
        }
        if isinstance(charge, FraisInscription):
            kwargs['type_paiement'] = 'frais_inscription'
            kwargs['frais_inscription'] = charge
        elif isinstance(charge, Mensualite):
            kwargs['type_paiement'] = 'mensualite'
            kwargs['mensualite'] = charge
        else:
            kwargs['type_paiement'] = 'frais_annexe'
            kwargs['frais_annexe'] = charge
        PaiementEleve.objects.create(**kwargs)
        restant -= verse
    return restant


def payer_echeance_moratoire(echeance, montant, *, user=None, mode_paiement='especes'):
    moratoire = echeance.moratoire
    if moratoire.statut == 'rompu':
        raise ValueError("Ce moratoire est rompu. Les paiements se font sur les charges d'origine.")
    if moratoire.statut != 'actif':
        raise ValueError("Ce moratoire n'est plus actif.")
    montant = _q(_dec(montant))
    reste = echeance.get_reste_a_payer()
    if montant <= ZERO:
        raise ValueError("Le montant doit être positif.")
    if montant > reste:
        raise ValueError("Le montant dépasse le reste de cette échéance.")

    with transaction.atomic():
        echeance.ajouter_paiement(montant)
        _repartir_sur_charges_origine(
            moratoire.eleve,
            moratoire.etablissement,
            moratoire.annee_scolaire,
            montant,
            user=user,
            mode_paiement=mode_paiement,
            notes=f"Moratoire échéance {echeance.numero}",
        )
        if moratoire.comptabilite_eleve:
            moratoire.comptabilite_eleve.verifier_statut_paiement()
        verifier_rupture_moratoire(moratoire)
    return echeance
