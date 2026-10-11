"""Factures fournisseurs et leurs paiements. Le reste vient des lignes, pas de montant_paye."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_generale_model import EcritureComptable, FactureFournisseur
from school_admin.model.finances_model import PaiementCharge
from school_admin.services.comptabilite_generale import extourner, pont_facture, pont_paiement_charge
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.tresorerie import compte_principal


def factures_historique_sans_lignes(etablissement):
    """Ancien montant_paye positif, sans aucune ligne. Lecture seule : on n'invente pas les paiements."""
    return (
        FactureFournisseur.objects.filter(
            etablissement=etablissement,
            montant_paye__gt=0,
        )
        .annotate(
            a_une_ligne=Exists(
                PaiementCharge.objects.filter(facture_id=OuterRef('pk'))
            )
        )
        .filter(a_une_ligne=False)
        .select_related('fournisseur')
        .order_by('date_echeance', 'id')
    )


def refuser_doublon_facture(etablissement, fournisseur, montant, jour):
    """Une sortie immédiate ne double pas une facture encore ouverte."""
    if fournisseur is None or montant is None or jour is None:
        return
    ouverte = FactureFournisseur.objects.filter(
        etablissement=etablissement,
        fournisseur=fournisseur,
        montant=montant,
        date_facture=jour,
        statut__in=('a_payer', 'partiel'),
    ).exists()
    if ouverte:
        raise ValueError(
            "Une facture ouverte existe déjà pour ce fournisseur, ce montant et ce jour. "
            "Réglez la facture au lieu d'enregistrer une seconde sortie."
        )


def _depense_deja_enregistree(etablissement, fournisseur, montant, jour):
    return DepenseEtablissement.objects.filter(
        etablissement=etablissement,
        fournisseur=fournisseur,
        montant=montant,
        date_depense=jour,
        statut='validee',
    ).exists()


def _maj_statut_facture(facture):
    if facture.statut == 'annulee':
        return facture
    regle = facture.montant_regle()
    if regle <= 0:
        statut = 'a_payer'
    elif regle < (facture.montant or Decimal('0')):
        statut = 'partiel'
    else:
        statut = 'payee'
    if facture.statut != statut:
        facture.statut = statut
        facture.save(update_fields=['statut'])
    return facture


def enregistrer_facture(etablissement, fournisseur, numero, libelle, montant, date_facture, date_echeance, categorie, annee_scolaire=None, user=None):
    from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser

    if montant is None or montant <= 0:
        raise ValueError("Le montant de la facture doit être supérieur à 0.")
    if not (numero or '').strip():
        raise ValueError("Le numéro de facture est obligatoire.")
    if categorie is None or categorie.etablissement_id != etablissement.id:
        raise ValueError("Choisissez une catégorie de cette école.")
    _exiger_periode_ouverte(etablissement, date_facture)
    if _depense_deja_enregistree(etablissement, fournisseur, montant, date_facture):
        raise ValueError(
            "Une sortie immédiate existe déjà pour ce fournisseur, ce montant et ce jour."
        )
    with transaction.atomic():
        facture = FactureFournisseur.objects.create(
            etablissement=etablissement,
            fournisseur=fournisseur,
            numero=(numero or '').strip()[:40],
            libelle=(libelle or '').strip()[:200],
            date_facture=date_facture,
            date_echeance=date_echeance,
            montant=montant,
            categorie=categorie,
            statut='a_payer',
        )
        ecriture = pont_facture(facture, annee_scolaire=annee_scolaire, user=user)
        journaliser(
            etablissement,
            facture,
            'creation',
            user=user,
            apres={'montant': str(montant), 'numero': facture.numero, 'statut': 'a_payer'},
        )
    return facture, ecriture


def enregistrer_paiement(facture, date_paiement, montant, compte_tresorerie=None, annee_scolaire=None, user=None):
    from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser

    if facture.statut == 'annulee':
        raise ValueError("Cette facture est annulée.")
    if montant is None or montant <= 0:
        raise ValueError("Le montant du paiement doit être supérieur à 0.")
    reste = facture.reste_a_payer()
    if montant > reste:
        raise ValueError("Ce paiement dépasse le reste à payer.")
    _exiger_periode_ouverte(facture.etablissement, date_paiement)
    if compte_tresorerie is None:
        compte_tresorerie = compte_principal(facture.etablissement, 'caisse')
    elif compte_tresorerie.etablissement_id != facture.etablissement_id:
        raise ValueError("Ce compte de trésorerie n'appartient pas à cette école.")
    with transaction.atomic():
        paiement = PaiementCharge.objects.create(
            etablissement=facture.etablissement,
            facture=facture,
            date_paiement=date_paiement,
            montant=montant,
            compte_tresorerie=compte_tresorerie,
            statut='validee',
        )
        ecriture = pont_paiement_charge(paiement, annee_scolaire=annee_scolaire, user=user)
        _maj_statut_facture(facture)
        journaliser(
            facture.etablissement,
            paiement,
            'validation',
            user=user,
            apres={'montant': str(montant), 'facture': facture.numero},
        )
    return paiement, ecriture


def annuler_paiement(paiement, motif, user=None):
    from django.utils import timezone

    from school_admin.services.finances.operations import _acteur, _exiger_periode_ouverte, journaliser

    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if paiement.statut == 'annulee':
        raise ValueError("Ce paiement est déjà annulé.")
    if paiement.statut != 'validee':
        raise ValueError("Seul un paiement validé peut être annulé.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(paiement.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=paiement.etablissement,
            source='paiement_charge',
            source_id=paiement.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        type_acteur, id_acteur = _acteur(user)
        paiement.statut = 'annulee'
        paiement.motif_annulation = texte
        paiement.date_annulation = timezone.now()
        paiement.annule_content_type = type_acteur
        paiement.annule_object_id = id_acteur
        paiement.save(update_fields=[
            'statut',
            'motif_annulation',
            'date_annulation',
            'annule_content_type',
            'annule_object_id',
        ])
        _maj_statut_facture(paiement.facture)
        journaliser(
            paiement.etablissement,
            paiement,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'validee'},
            apres={'statut': 'annulee'},
        )
    return paiement


def annuler_facture(facture, motif, user=None):
    from django.utils import timezone

    from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser

    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if facture.statut == 'annulee':
        raise ValueError("Cette facture est déjà annulée.")
    if facture.paiements.filter(statut='validee').exists():
        raise ValueError("Annulez d'abord les paiements de cette facture.")
    aujourd_hui = timezone.now().date()
    _exiger_periode_ouverte(facture.etablissement, aujourd_hui)
    with transaction.atomic():
        originale = EcritureComptable.objects.filter(
            etablissement=facture.etablissement,
            source='facture',
            source_id=facture.id,
        ).first()
        if originale is not None:
            extourner(originale, aujourd_hui, texte, user=user)
        facture.statut = 'annulee'
        facture.save(update_fields=['statut'])
        journaliser(
            facture.etablissement,
            facture,
            'annulation',
            user=user,
            motif=texte,
            avant={'statut': 'a_payer'},
            apres={'statut': 'annulee'},
        )
    return facture


def preparer_referentiels(etablissement):
    assurer_categories(etablissement)
    from school_admin.services.finances.tresorerie import assurer_comptes_defaut

    assurer_comptes_defaut(etablissement)
