"""Prêts : la réception n'est pas un produit. Seuls intérêts et frais sont des charges."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable
from school_admin.model.finances_model import EcheancePret, PretEtablissement, RemboursementPret
from school_admin.services.comptabilite_generale import (
    ensure_plan_comptable,
    extourner,
    pont_pret,
    pont_remboursement_pret,
)
from school_admin.services.finances.operations import (
    _acteur,
    _exiger_periode_ouverte,
    attacher_piece,
    journaliser,
)


def _decimal(valeur):
    if valeur is None or valeur == '':
        return Decimal('0')
    return Decimal(str(valeur))


def _compte_ouvert(etablissement, compte_tresorerie):
    if compte_tresorerie is None or compte_tresorerie.etablissement_id != etablissement.id:
        raise ValueError("Ce compte de trésorerie n'appartient pas à cette école.")
    if compte_tresorerie.statut != 'ouvert' or not compte_tresorerie.actif:
        raise ValueError("Ce compte de trésorerie est fermé.")
    return compte_tresorerie


def enregistrer_pret(
    etablissement,
    compte_tresorerie,
    date_reception,
    montant,
    reference,
    objet,
    taux=0,
    duree_mois=None,
    annee_scolaire=None,
    user=None,
    fichier=None,
):
    reference = (reference or '').strip()
    objet = (objet or '').strip()
    if not reference:
        raise ValueError("La référence du prêt est obligatoire.")
    if not objet:
        raise ValueError("L'objet du prêt est obligatoire.")
    if PretEtablissement.objects.filter(etablissement=etablissement, reference=reference).exists():
        raise ValueError("Cette référence de prêt existe déjà.")
    _compte_ouvert(etablissement, compte_tresorerie)
    montant = _decimal(montant)
    taux = _decimal(taux)
    if montant <= 0:
        raise ValueError("Le montant doit être positif.")
    if taux < 0 or taux > 100:
        raise ValueError("Le taux est un pourcentage entre 0 et 100.")
    if duree_mois not in (None, ''):
        duree_mois = int(duree_mois)
        if duree_mois <= 0:
            raise ValueError("La durée doit être positive.")
    else:
        duree_mois = None
    _exiger_periode_ouverte(etablissement, date_reception)
    ensure_plan_comptable(etablissement)
    with transaction.atomic():
        pret = PretEtablissement.objects.create(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            compte_tresorerie=compte_tresorerie,
            reference=reference[:80],
            date_reception=date_reception,
            montant=montant,
            taux=taux,
            duree_mois=duree_mois,
            objet=objet[:200],
            statut='en_cours',
        )
        if fichier is not None:
            attacher_piece(etablissement, pret, fichier, user=user)
        ecriture = pont_pret(pret, annee_scolaire=annee_scolaire, user=user)
        journaliser(
            etablissement,
            pret,
            'creation',
            user=user,
            apres={'montant': str(montant), 'reference': pret.reference, 'statut': 'en_cours'},
        )
    return pret, ecriture


def ajouter_echeance(pret, date_echeance, capital_prevu=0, interets_prevus=0, frais_prevus=0):
    """Prévision seulement. Aucune écriture."""
    if pret.statut == 'annulee':
        raise ValueError("Ce prêt est annulé.")
    capital_prevu = _decimal(capital_prevu)
    interets_prevus = _decimal(interets_prevus)
    frais_prevus = _decimal(frais_prevus)
    if capital_prevu < 0 or interets_prevus < 0 or frais_prevus < 0:
        raise ValueError("Les montants prévus ne peuvent pas être négatifs.")
    if capital_prevu + interets_prevus + frais_prevus <= 0:
        raise ValueError("L'échéance doit avoir un montant.")
    _exiger_periode_ouverte(pret.etablissement, date_echeance)
    dernier = pret.echeances.order_by('-numero').first()
    numero = (dernier.numero + 1) if dernier else 1
    return EcheancePret.objects.create(
        pret=pret,
        etablissement=pret.etablissement,
        numero=numero,
        date_echeance=date_echeance,
        capital_prevu=capital_prevu,
        interets_prevus=interets_prevus,
        frais_prevus=frais_prevus,
    )


def enregistrer_remboursement(
    pret,
    date_remboursement,
    capital=0,
    interets=0,
    frais=0,
    motif='',
    compte_tresorerie=None,
    echeance=None,
    user=None,
):
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif du remboursement est obligatoire.")
    if pret.statut != 'en_cours':
        raise ValueError("Seul un prêt en cours peut être remboursé.")
    compte = compte_tresorerie or pret.compte_tresorerie
    _compte_ouvert(pret.etablissement, compte)
    if echeance is not None and echeance.pret_id != pret.id:
        raise ValueError("Cette échéance n'appartient pas à ce prêt.")
    capital = _decimal(capital)
    interets = _decimal(interets)
    frais = _decimal(frais)
    if capital < 0 or interets < 0 or frais < 0:
        raise ValueError("Les montants ne peuvent pas être négatifs.")
    if capital + interets + frais <= 0:
        raise ValueError("Le remboursement doit avoir un montant.")
    _exiger_periode_ouverte(pret.etablissement, date_remboursement)
    ensure_plan_comptable(pret.etablissement)
    with transaction.atomic():
        verrouille = PretEtablissement.objects.select_for_update().get(pk=pret.pk)
        if capital > verrouille.capital_restant():
            raise ValueError("Le capital remboursé dépasse le capital restant.")
        remboursement = RemboursementPret.objects.create(
            pret=verrouille,
            echeance=echeance,
            etablissement=verrouille.etablissement,
            date_remboursement=date_remboursement,
            capital=capital,
            interets=interets,
            frais=frais,
            compte_tresorerie=compte,
            motif=texte[:200],
            statut='validee',
        )
        if verrouille.capital_restant() == 0:
            verrouille.statut = 'solde'
            verrouille.save(update_fields=['statut'])
        ecriture = pont_remboursement_pret(
            remboursement,
            annee_scolaire=verrouille.annee_scolaire,
            user=user,
        )
        journaliser(
            verrouille.etablissement,
            remboursement,
            'remboursement',
            user=user,
            apres={
                'capital': str(capital),
                'interets': str(interets),
                'frais': str(frais),
                'pret': verrouille.pk,
            },
        )
    return remboursement, ecriture


def annuler_remboursement(remboursement, motif, user=None):
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if remboursement.statut == 'annulee':
        raise ValueError("Ce remboursement est déjà annulé.")
    if remboursement.statut != 'validee':
        raise ValueError("Seul un remboursement validé peut être annulé.")
    if remboursement.pret.statut == 'annulee':
        raise ValueError("Le prêt est annulé.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(remboursement.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=remboursement.etablissement,
            source='remboursement_pret',
            source_id=remboursement.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        type_acteur, id_acteur = _acteur(user)
        remboursement.statut = 'annulee'
        remboursement.motif_annulation = texte
        remboursement.date_annulation = timezone.now()
        remboursement.annule_content_type = type_acteur
        remboursement.annule_object_id = id_acteur
        remboursement.save(update_fields=[
            'statut',
            'motif_annulation',
            'date_annulation',
            'annule_content_type',
            'annule_object_id',
        ])
        pret = PretEtablissement.objects.select_for_update().get(pk=remboursement.pret_id)
        if pret.statut == 'solde' and pret.capital_restant() > 0:
            pret.statut = 'en_cours'
            pret.save(update_fields=['statut'])
        journaliser(
            remboursement.etablissement,
            remboursement,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'validee'},
            apres={'statut': 'annulee'},
        )
    return remboursement


def annuler_pret(pret, motif, user=None):
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if pret.statut == 'annulee':
        raise ValueError("Ce prêt est déjà annulé.")
    if pret.capital_rembourse() > 0:
        raise ValueError("Annulez d'abord les remboursements encore validés.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(pret.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=pret.etablissement,
            source='pret',
            source_id=pret.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        type_acteur, id_acteur = _acteur(user)
        pret.statut = 'annulee'
        pret.motif_annulation = texte
        pret.date_annulation = timezone.now()
        pret.annule_content_type = type_acteur
        pret.annule_object_id = id_acteur
        pret.save(update_fields=[
            'statut',
            'motif_annulation',
            'date_annulation',
            'annule_content_type',
            'annule_object_id',
        ])
        journaliser(
            pret.etablissement,
            pret,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'en_cours'},
            apres={'statut': 'annulee'},
        )
    return pret
