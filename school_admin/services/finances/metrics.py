"""Sept indicateurs financiers. Source unique. kpi_cg n'est pas branché ici."""
from decimal import Decimal

from django.db.models import Sum

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_eleve_model import FraisAnnexe, FraisInscription, Mensualite, PaiementEleve
from school_admin.model.comptabilite_generale_model import FactureFournisseur, LigneEcriture
from school_admin.model.finances_model import (
    CompteTresorerie,
    PaiementCharge,
    PretEtablissement,
    RecetteEtablissement,
    RemboursementOperation,
    RemboursementPret,
)
from django.utils import timezone

from school_admin.services.caisse import bornes_mois
from school_admin.services.comptabilite_generale import (
    ensure_exercice,
    regime_comptable_etablissement,
)
from school_admin.services.recouvrement import devise_etablissement

ZERO = Decimal('0.00')

DEFINITIONS = {
    'disponible': {
        'label': 'Disponible',
        'definition': "Argent présent dans les comptes de trésorerie de l'école à la date de fin.",
        'source': 'CompteTresorerie + LigneEcriture validées (solde_calcule).',
        'formule': 'Somme (débit − crédit) des comptes caisse, banque et mobile money, à date_fin.',
        'periode': 'Stock à date_fin.',
        'inclus': ('Caisse, banque, mobile money actifs.',),
        'exclus': (
            'Solde initial (non ajouté tant que la pièce d’ouverture n’existe pas).',
            'Comptes inactifs.',
            'Créances familles.',
        ),
    },
    'encaisse': {
        'label': 'Encaissé',
        'definition': "Argent réellement reçu pendant la période. Ce n'est pas une créance émise.",
        'source': 'PaiementEleve, RecetteEtablissement validée, RemboursementOperation validé.',
        'formule': 'Scolarité + recettes complémentaires − remboursements de recettes, dans [date_début, date_fin].',
        'periode': 'Flux de la période.',
        'inclus': ('Paiements élèves.', 'Activités, subventions, divers validés.',),
        'exclus': (
            'Créances émises (411 / produits) : elles ne s’additionnent pas à l’encaissé.',
            'Transferts caisse ↔ banque.',
            'Réception d’un prêt.',
            'Recettes annulées.',
        ),
    },
    'paye': {
        'label': 'Payé',
        'definition': "Argent réellement sorti pendant la période, hors remboursement de capital et hors virement.",
        'source': 'DepenseEtablissement, PaiementCharge, RemboursementPret (intérêts et frais).',
        'formule': 'Sorties validées + paiements de factures + intérêts et frais d’emprunt, dans la période.',
        'periode': 'Flux de la période.',
        'inclus': ('Dépenses du jour validées.', 'Paiements de charges validés.', 'Intérêts et frais d’emprunt.',),
        'exclus': (
            'Capital remboursé (baisse de la dette, pas une sortie d’exploitation).',
            'Transferts.',
            'Facture enregistrée non payée.',
            'Opérations annulées.',
        ),
    },
    'resultat': {
        'label': 'Résultat',
        'definition': "Produits moins charges selon le régime : les ponts passent la classe 6 ou 7 à l’émission (engagement) ou à l’encaissement / paiement (trésorerie).",
        'source': 'LigneEcriture validée, comptes de nature charge ou produit, dans la période.',
        'formule': '(crédit − débit des produits) − (débit − crédit des charges).',
        'periode': 'Flux de la période. Le régime est relu sur ParametresComptabilite.',
        'inclus': ('Classes 6 et 7 déjà écrites.', 'Intérêts et frais d’emprunt.',),
        'exclus': (
            'Créances émises + encaissements additionnés : en engagement, le produit est à l’émission ; l’encaissement crédite 411.',
            'Capital d’emprunt.',
            'Transferts.',
            'Destination « équipement » à elle seule.',
        ),
    },
    'creances': {
        'label': 'Créances',
        'definition': "Ce que les familles doivent encore, sur l’année scolaire. Stock, pas un flux.",
        'source': 'FraisInscription, Mensualite, FraisAnnexe (montant − montant_paye).',
        'formule': 'max(dû − payé, 0).',
        'periode': 'Stock à date_fin, filtré par année scolaire si elle est fournie.',
        'inclus': ('Inscription, mensualités, frais annexes.',),
        'exclus': ('Encaissements de la période : on ne les additionne pas au dû.', 'Recettes complémentaires.',),
    },
    'dettes': {
        'label': 'Dettes',
        'definition': "Ce que l’école doit : factures fournisseurs restantes + capital d’emprunt restant.",
        'source': 'FactureFournisseur.reste via PaiementCharge, PretEtablissement.capital_restant.',
        'formule': 'Engagements + capital restant des prêts en cours.',
        'periode': 'Stock à date_fin.',
        'inclus': ('Reste des factures non annulées.', 'Capital restant des prêts en cours.',),
        'exclus': ('Échéances prévues non payées (prévision sans écriture).', 'Factures annulées.', 'Prêts annulés.',),
    },
    'engagements': {
        'label': 'Engagements',
        'definition': "Prévu non payé des charges du mois : reste des factures fournisseurs.",
        'source': 'FactureFournisseur.montant − paiements de charges validés.',
        'formule': 'max(prévu − payé, 0) sur les factures non annulées.',
        'periode': 'Stock à date_fin.',
        'inclus': ('Factures à payer ou partielles, et le reste d’une facture encore ouverte.',),
        'exclus': (
            'Capital d’emprunt (dans Dettes, pas ici).',
            'Dépenses du jour déjà payées.',
            'Ancien champ montant_paye sans ligne PaiementCharge.',
        ),
    },
}


def _dec(valeur):
    if valeur is None:
        return ZERO
    return Decimal(str(valeur))


def _indicateur(identifiant, valeur, etablissement, date_debut, date_fin, annee_scolaire, exercice, regime, extra=None):
    meta = DEFINITIONS[identifiant]
    ligne = {
        'id': identifiant,
        'label': meta['label'],
        'valeur': _dec(valeur),
        'unite': devise_etablissement(etablissement),
        'definition': meta['definition'],
        'source': meta['source'],
        'formule': meta['formule'],
        'periode': meta['periode'],
        'etablissement_id': etablissement.pk,
        'annee_scolaire_id': getattr(annee_scolaire, 'pk', None),
        'exercice_id': getattr(exercice, 'pk', None),
        'regime': regime,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'inclus': meta['inclus'],
        'exclus': meta['exclus'],
    }
    if extra:
        ligne.update(extra)
    return ligne


def _disponible(etablissement, date_fin):
    """Même formule que solde_calcule, en un agrégat, pas un SELECT par compte."""
    compte_ids = list(
        CompteTresorerie.objects.filter(
            etablissement=etablissement, actif=True,
        ).values_list('compte_comptable_id', flat=True)
    )
    if not compte_ids:
        return ZERO
    totaux = LigneEcriture.objects.filter(
        compte_id__in=compte_ids,
        ecriture__etablissement=etablissement,
        ecriture__validee=True,
        ecriture__date_ecriture__lte=date_fin,
    ).exclude(ecriture__source='a_nouveaux').aggregate(debit=Sum('debit'), credit=Sum('credit'))
    return _dec(totaux['debit']) - _dec(totaux['credit'])


def _encaisse(etablissement, date_debut, date_fin):
    scolarite = PaiementEleve.objects.filter(
        etablissement=etablissement,
        date_paiement__date__gte=date_debut,
        date_paiement__date__lte=date_fin,
    ).aggregate(s=Sum('montant'))['s']
    recettes = RecetteEtablissement.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_recette__gte=date_debut,
        date_recette__lte=date_fin,
    ).aggregate(s=Sum('montant'))['s']
    remboursements = RemboursementOperation.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_remboursement__gte=date_debut,
        date_remboursement__lte=date_fin,
    ).aggregate(s=Sum('montant'))['s']
    scolarite = _dec(scolarite)
    recettes = _dec(recettes)
    remboursements = _dec(remboursements)
    return scolarite + recettes - remboursements, {
        'detail': {
            'scolarite': scolarite,
            'recettes': recettes,
            'remboursements': remboursements,
        }
    }


def _paye(etablissement, date_debut, date_fin):
    sorties = DepenseEtablissement.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_depense__gte=date_debut,
        date_depense__lte=date_fin,
    ).aggregate(s=Sum('montant'))['s']
    charges = PaiementCharge.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_paiement__gte=date_debut,
        date_paiement__lte=date_fin,
    ).aggregate(s=Sum('montant'))['s']
    cout_emprunt = RemboursementPret.objects.filter(
        etablissement=etablissement,
        statut='validee',
        date_remboursement__gte=date_debut,
        date_remboursement__lte=date_fin,
    ).aggregate(interets=Sum('interets'), frais=Sum('frais'))
    sorties = _dec(sorties)
    charges = _dec(charges)
    interets = _dec(cout_emprunt['interets'])
    frais = _dec(cout_emprunt['frais'])
    return sorties + charges + interets + frais, {
        'detail': {
            'sorties': sorties,
            'paiements_charges': charges,
            'interets': interets,
            'frais': frais,
        }
    }


def _resultat(etablissement, date_debut, date_fin):
    lignes = LigneEcriture.objects.filter(
        ecriture__etablissement=etablissement,
        ecriture__validee=True,
        ecriture__date_ecriture__gte=date_debut,
        ecriture__date_ecriture__lte=date_fin,
        compte__nature__in=('charge', 'produit'),
    ).values('compte__nature').annotate(debit=Sum('debit'), credit=Sum('credit'))
    charges = ZERO
    produits = ZERO
    for ligne in lignes:
        debit = _dec(ligne['debit'])
        credit = _dec(ligne['credit'])
        if ligne['compte__nature'] == 'charge':
            charges += debit - credit
        else:
            produits += credit - debit
    return produits - charges, {'detail': {'produits': produits, 'charges': charges}}


def _creances(etablissement, annee_scolaire):
    filtres = {'etablissement': etablissement}
    if annee_scolaire is not None:
        filtres['annee_scolaire'] = annee_scolaire
    du = ZERO
    paye = ZERO
    for modele in (FraisInscription, Mensualite, FraisAnnexe):
        totaux = modele.objects.filter(**filtres).aggregate(du=Sum('montant'), paye=Sum('montant_paye'))
        du += _dec(totaux['du'])
        paye += _dec(totaux['paye'])
    reste = du - paye
    if reste < 0:
        reste = ZERO
    return reste, {'detail': {'du': du, 'paye': paye}}


def _engagements(etablissement):
    prevu = FactureFournisseur.objects.filter(etablissement=etablissement).exclude(
        statut='annulee',
    ).aggregate(s=Sum('montant'))['s']
    paye = PaiementCharge.objects.filter(
        etablissement=etablissement,
        statut='validee',
    ).exclude(facture__statut='annulee').aggregate(s=Sum('montant'))['s']
    reste = _dec(prevu) - _dec(paye)
    if reste < 0:
        reste = ZERO
    return reste, {'detail': {'prevu': _dec(prevu), 'paye': _dec(paye)}}


def _capital_restant(etablissement):
    emprunte = PretEtablissement.objects.filter(
        etablissement=etablissement, statut='en_cours',
    ).aggregate(s=Sum('montant'))['s']
    rembourse = RemboursementPret.objects.filter(
        etablissement=etablissement,
        statut='validee',
        pret__statut='en_cours',
    ).aggregate(s=Sum('capital'))['s']
    reste = _dec(emprunte) - _dec(rembourse)
    if reste < 0:
        reste = ZERO
    return reste


def calculer_indicateurs(etablissement, date_debut=None, date_fin=None, annee_scolaire=None):
    """Calcule les sept indicateurs. N'écrit rien. N'appelle pas kpi_cg."""
    if date_debut is None or date_fin is None:
        bornes = bornes_mois(date_fin or date_debut or timezone.now().date())
        date_debut = date_debut or bornes.debut
        date_fin = date_fin or bornes.fin
    if date_debut > date_fin:
        raise ValueError("La date de début doit précéder la date de fin.")
    regime = regime_comptable_etablissement(etablissement)
    exercice = ensure_exercice(etablissement, annee_scolaire)
    encaisse, extra_encaisse = _encaisse(etablissement, date_debut, date_fin)
    paye, extra_paye = _paye(etablissement, date_debut, date_fin)
    resultat, extra_resultat = _resultat(etablissement, date_debut, date_fin)
    creances, extra_creances = _creances(etablissement, annee_scolaire)
    engagements, extra_engagements = _engagements(etablissement)
    capital = _capital_restant(etablissement)
    dettes = engagements + capital
    return {
        'etablissement_id': etablissement.pk,
        'annee_scolaire_id': getattr(annee_scolaire, 'pk', None),
        'exercice_id': exercice.pk if exercice else None,
        'regime': regime,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'indicateurs': {
            'disponible': _indicateur(
                'disponible', _disponible(etablissement, date_fin),
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
            ),
            'encaisse': _indicateur(
                'encaisse', encaisse,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                extra_encaisse,
            ),
            'paye': _indicateur(
                'paye', paye,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                extra_paye,
            ),
            'resultat': _indicateur(
                'resultat', resultat,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                extra_resultat,
            ),
            'creances': _indicateur(
                'creances', creances,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                extra_creances,
            ),
            'dettes': _indicateur(
                'dettes', dettes,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                {'detail': {'engagements': engagements, 'capital_restant': capital}},
            ),
            'engagements': _indicateur(
                'engagements', engagements,
                etablissement, date_debut, date_fin, annee_scolaire, exercice, regime,
                extra_engagements,
            ),
        },
    }


def valeur(etablissement, identifiant, date_debut=None, date_fin=None, annee_scolaire=None):
    return calculer_indicateurs(etablissement, date_debut, date_fin, annee_scolaire)['indicateurs'][identifiant]['valeur']
