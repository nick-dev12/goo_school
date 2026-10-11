"""Transferts entre comptes de trésorerie. Les virements anciens ne sont pas rejoués."""
from django.db import transaction
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable, MouvementTresorerie
from school_admin.services.comptabilite_generale import extourner, pont_transfert
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal


def rattacher_virements_historiques(etablissement):
    """Nomme caisse → banque sur les virements déjà écrits. Aucune nouvelle pièce."""
    assurer_comptes_defaut(etablissement)
    caisse = compte_principal(etablissement, 'caisse')
    banque = compte_principal(etablissement, 'banque')
    if caisse is None or banque is None:
        return 0
    return MouvementTresorerie.objects.filter(
        etablissement=etablissement,
        type_mouvement='virement_interne',
        compte_source__isnull=True,
    ).update(compte_source=caisse, compte_destination=banque)


def enregistrer_transfert(etablissement, compte_source, compte_destination, date_mouvement, montant, reference='', motif='', annee_scolaire=None, user=None):
    from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser

    if montant is None or montant <= 0:
        raise ValueError("Le montant du transfert doit être supérieur à 0.")
    if compte_source is None or compte_destination is None:
        raise ValueError("Choisissez le compte de départ et le compte d'arrivée.")
    if compte_source.etablissement_id != etablissement.id or compte_destination.etablissement_id != etablissement.id:
        raise ValueError("Ces comptes n'appartiennent pas à cette école.")
    if compte_source.id == compte_destination.id:
        raise ValueError("Le compte de départ et le compte d'arrivée sont les mêmes.")
    if compte_source.statut != 'ouvert' or compte_destination.statut != 'ouvert':
        raise ValueError("Les deux comptes doivent être ouverts.")
    _exiger_periode_ouverte(etablissement, date_mouvement)
    libelle = (motif or f"Transfert {compte_source.libelle} vers {compte_destination.libelle}")[:200]
    with transaction.atomic():
        mouvement = MouvementTresorerie.objects.create(
            etablissement=etablissement,
            type_mouvement='virement_interne',
            date_mouvement=date_mouvement,
            montant=montant,
            libelle=libelle,
            compte_source=compte_source,
            compte_destination=compte_destination,
            reference=(reference or '')[:80],
            motif=libelle,
            statut='validee',
        )
        ecriture = pont_transfert(mouvement, annee_scolaire=annee_scolaire, user=user)
        journaliser(
            etablissement,
            mouvement,
            'creation',
            user=user,
            apres={
                'montant': str(montant),
                'source': compte_source.libelle,
                'destination': compte_destination.libelle,
            },
        )
    return mouvement, ecriture


def annuler_transfert(mouvement, motif, user=None):
    from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser

    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    mouvement.refresh_from_db()
    if mouvement.statut == 'annulee':
        raise ValueError("Ce transfert est déjà annulé.")
    if mouvement.statut != 'validee':
        raise ValueError("Seul un transfert validé peut être annulé.")
    if mouvement.pointe:
        raise ValueError("Ce transfert est pointé sur un relevé. Retirez d'abord le pointage, avec un motif.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(mouvement.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = mouvement.ecriture
        if originale is None:
            originale = EcritureComptable.objects.filter(
                etablissement=mouvement.etablissement,
                source='transfert',
                source_id=mouvement.id,
            ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        mouvement.statut = 'annulee'
        mouvement.motif_annulation = texte
        mouvement.date_annulation = timezone.now()
        mouvement.save(update_fields=['statut', 'motif_annulation', 'date_annulation'])
        journaliser(
            mouvement.etablissement,
            mouvement,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'validee'},
            apres={'statut': 'annulee'},
        )
    return mouvement
