"""Recettes complémentaires. La scolarité reste dans PaiementEleve, en lecture seule."""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from school_admin.model.comptabilite_eleve_model import PaiementEleve
from school_admin.model.comptabilite_generale_model import EcritureComptable
from school_admin.model.finances_model import RecetteEtablissement, RemboursementOperation
from school_admin.services.comptabilite_generale import extourner, pont_recette, pont_remboursement_operation
from school_admin.services.finances.operations import (
    _acteur,
    _exiger_periode_ouverte,
    attacher_piece,
    journaliser,
)

NATURES = tuple(code for code, _label in RecetteEtablissement.NATURE_CHOICES)
DESTINATIONS = tuple(code for code, _label in RecetteEtablissement.DESTINATION_CHOICES)


def paiements_scolarite(etablissement, annee_scolaire, limite=40):
    """Lecture seule. N'écrit aucune RecetteEtablissement."""
    return list(
        PaiementEleve.objects.filter(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
        ).select_related('eleve').order_by('-date_paiement')[:limite]
    )


def _compte_ouvert(etablissement, compte_tresorerie):
    if compte_tresorerie is None or compte_tresorerie.etablissement_id != etablissement.id:
        raise ValueError("Ce compte de trésorerie n'appartient pas à cette école.")
    if compte_tresorerie.statut != 'ouvert' or not compte_tresorerie.actif:
        raise ValueError("Ce compte de trésorerie est fermé.")
    return compte_tresorerie


def enregistrer_recette(
    etablissement,
    nature,
    categorie,
    compte_tresorerie,
    date_recette,
    montant,
    libelle='',
    origine='',
    reference='',
    destination='',
    annee_scolaire=None,
    user=None,
    fichier=None,
):
    """Encaissement direct. Aucun paiement élève n'est créé ni recopié."""
    if nature not in NATURES:
        raise ValueError("La nature doit être activité, subvention ou divers.")
    if categorie is None or categorie.etablissement_id != etablissement.id or categorie.type_categorie != 'recette':
        raise ValueError("Cette catégorie n'est pas une recette de cette école.")
    if not categorie.actif:
        raise ValueError("Cette catégorie est inactive.")
    _compte_ouvert(etablissement, compte_tresorerie)
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ValueError("Le montant doit être positif.")
    if nature == 'subvention':
        if destination not in DESTINATIONS:
            raise ValueError("Une subvention indique sa destination : fonctionnement, équipement, projet ou autre.")
    else:
        destination = ''
    _exiger_periode_ouverte(etablissement, date_recette)
    with transaction.atomic():
        recette = RecetteEtablissement.objects.create(
            etablissement=etablissement,
            annee_scolaire=annee_scolaire,
            date_recette=date_recette,
            nature=nature,
            destination=destination,
            categorie=categorie,
            compte_tresorerie=compte_tresorerie,
            libelle=(libelle or '')[:200],
            origine=(origine or '')[:160],
            reference=(reference or '')[:80],
            montant=montant,
            statut='validee',
        )
        if fichier is not None:
            attacher_piece(etablissement, recette, fichier, user=user)
        ecriture = pont_recette(recette, annee_scolaire=annee_scolaire, user=user)
        journaliser(
            etablissement,
            recette,
            'validation',
            user=user,
            apres={
                'montant': str(montant),
                'nature': nature,
                'destination': destination,
                'statut': 'validee',
            },
        )
    return recette, ecriture


def annuler_recette(recette, motif, user=None):
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if recette.statut == 'annulee':
        raise ValueError("Cette recette est déjà annulée.")
    if recette.statut != 'validee':
        raise ValueError("Seule une recette validée peut être annulée.")
    if recette.montant_rembourse() > 0:
        raise ValueError("Annulez d'abord les remboursements encore validés.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(recette.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=recette.etablissement,
            source='recette',
            source_id=recette.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        type_acteur, id_acteur = _acteur(user)
        recette.statut = 'annulee'
        recette.motif_annulation = texte
        recette.date_annulation = timezone.now()
        recette.annule_content_type = type_acteur
        recette.annule_object_id = id_acteur
        recette.save(update_fields=[
            'statut',
            'motif_annulation',
            'date_annulation',
            'annule_content_type',
            'annule_object_id',
        ])
        journaliser(
            recette.etablissement,
            recette,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'validee'},
            apres={'statut': 'annulee'},
        )
    return recette


def enregistrer_remboursement(recette, date_remboursement, montant, motif, compte_tresorerie=None, user=None):
    """Le montant d'origine reste. Le net est l'origine moins les remboursements validés."""
    if not isinstance(recette, RecetteEtablissement):
        raise ValueError("Un paiement élève ne devient pas une recette, et ne se rembourse pas ici.")
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif du remboursement est obligatoire.")
    if recette.statut != 'validee':
        raise ValueError("Seule une recette validée peut être remboursée.")
    compte = compte_tresorerie or recette.compte_tresorerie
    _compte_ouvert(recette.etablissement, compte)
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ValueError("Le montant doit être positif.")
    _exiger_periode_ouverte(recette.etablissement, date_remboursement)
    with transaction.atomic():
        verrouillee = RecetteEtablissement.objects.select_for_update().get(pk=recette.pk)
        if montant > verrouillee.net():
            raise ValueError("Le remboursement dépasse le net encore disponible.")
        remboursement = RemboursementOperation.objects.create(
            etablissement=verrouillee.etablissement,
            content_type=ContentType.objects.get_for_model(verrouillee),
            object_id=verrouillee.pk,
            date_remboursement=date_remboursement,
            montant=montant,
            compte_tresorerie=compte,
            motif=texte[:200],
            statut='validee',
        )
        ecriture = pont_remboursement_operation(
            remboursement,
            annee_scolaire=verrouillee.annee_scolaire,
            user=user,
        )
        journaliser(
            verrouillee.etablissement,
            remboursement,
            'remboursement',
            user=user,
            apres={'montant': str(montant), 'recette': verrouillee.pk},
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
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(remboursement.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=remboursement.etablissement,
            source='remboursement_operation',
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
