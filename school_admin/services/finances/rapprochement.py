"""Rapprochement bancaire. Aucune écriture n'est créée ici."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable, LigneEcriture, MouvementTresorerie
from school_admin.model.finances_model import LigneReleve, ReleveBancaire
from school_admin.services.finances.operations import _exiger_periode_ouverte, journaliser
from school_admin.services.finances.tresorerie import solde_calcule

TYPES_RELEVE = ('banque', 'mobile_money')


def _decimal(valeur):
    if valeur is None or valeur == '':
        return Decimal('0')
    return Decimal(str(valeur))


def _compte_rapprochable(etablissement, compte_tresorerie):
    if compte_tresorerie is None or compte_tresorerie.etablissement_id != etablissement.id:
        raise ValueError("Ce compte de trésorerie n'appartient pas à cette école.")
    if compte_tresorerie.type_compte not in TYPES_RELEVE:
        raise ValueError("Un relevé se saisit pour une banque ou un mobile money, pas pour la caisse.")
    if compte_tresorerie.statut != 'ouvert' or not compte_tresorerie.actif:
        raise ValueError("Ce compte de trésorerie est fermé.")
    return compte_tresorerie


def _releve_modifiable(releve):
    if releve.statut == 'cloture':
        raise ValueError("Ce relevé est clôturé. Il ne se modifie plus.")
    return releve


def _montant_aria(ecriture, compte_comptable):
    totaux = LigneEcriture.objects.filter(
        ecriture=ecriture,
        compte=compte_comptable,
    ).aggregate(debit=Sum('debit'), credit=Sum('credit'))
    return totaux['debit'] or Decimal('0'), totaux['credit'] or Decimal('0')


def _mouvement_lie(ecriture):
    if ecriture is None:
        return None
    mouvement = MouvementTresorerie.objects.filter(ecriture=ecriture).first()
    if mouvement is not None:
        return mouvement
    if ecriture.source == 'transfert' and ecriture.source_id:
        return MouvementTresorerie.objects.filter(
            pk=ecriture.source_id,
            etablissement_id=ecriture.etablissement_id,
        ).first()
    return None


def _marquer_mouvement_pointe(mouvement, pointe):
    if mouvement is None:
        return
    if pointe:
        mouvement.pointe = True
        mouvement.date_pointage = timezone.now()
        mouvement.save(update_fields=['pointe', 'date_pointage'])
        return
    if LigneReleve.objects.filter(mouvement=mouvement, pointe=True).exists():
        return
    mouvement.pointe = False
    mouvement.date_pointage = None
    mouvement.save(update_fields=['pointe', 'date_pointage'])


def creer_releve(
    etablissement,
    compte_tresorerie,
    reference,
    date_debut,
    date_fin,
    solde_ouverture,
    solde_cloture,
    user=None,
):
    reference = (reference or '').strip()
    if not reference:
        raise ValueError("La référence du relevé est obligatoire.")
    if date_debut is None or date_fin is None:
        raise ValueError("Les dates du relevé sont obligatoires.")
    if date_debut > date_fin:
        raise ValueError("La date de début doit précéder la date de fin.")
    _compte_rapprochable(etablissement, compte_tresorerie)
    _exiger_periode_ouverte(etablissement, date_fin)
    ouverture = _decimal(solde_ouverture)
    cloture = _decimal(solde_cloture)
    if ReleveBancaire.objects.filter(
        etablissement=etablissement,
        compte_tresorerie=compte_tresorerie,
        reference=reference,
    ).exists():
        raise ValueError("Cette référence de relevé existe déjà pour ce compte.")
    with transaction.atomic():
        releve = ReleveBancaire.objects.create(
            etablissement=etablissement,
            compte_tresorerie=compte_tresorerie,
            reference=reference[:80],
            date_debut=date_debut,
            date_fin=date_fin,
            solde_ouverture=ouverture,
            solde_cloture=cloture,
            statut='en_cours',
        )
        journaliser(
            etablissement,
            releve,
            'creation',
            user=user,
            apres={
                'reference': releve.reference,
                'compte': compte_tresorerie.libelle,
                'solde_cloture': str(cloture),
            },
        )
    return releve


def ajouter_ligne(releve, date_operation, libelle, debit=0, credit=0, reference='', user=None):
    _releve_modifiable(releve)
    _exiger_periode_ouverte(releve.etablissement, releve.date_fin)
    libelle = (libelle or '').strip()
    if not libelle:
        raise ValueError("Le libellé de la ligne est obligatoire.")
    if date_operation is None:
        raise ValueError("La date de la ligne est obligatoire.")
    if date_operation < releve.date_debut or date_operation > releve.date_fin:
        raise ValueError("La date de la ligne doit être dans la période du relevé.")
    debit = _decimal(debit)
    credit = _decimal(credit)
    if debit < 0 or credit < 0:
        raise ValueError("Le débit et le crédit ne peuvent pas être négatifs.")
    if debit and credit:
        raise ValueError("Une ligne a un débit ou un crédit, pas les deux.")
    if not debit and not credit:
        raise ValueError("Indiquez un débit ou un crédit.")
    with transaction.atomic():
        ligne = LigneReleve.objects.create(
            releve=releve,
            date_operation=date_operation,
            libelle=libelle[:200],
            debit=debit,
            credit=credit,
            reference=(reference or '')[:80],
        )
        journaliser(
            releve.etablissement,
            ligne,
            'creation',
            user=user,
            apres={'libelle': ligne.libelle, 'debit': str(debit), 'credit': str(credit)},
        )
    return ligne


def mettre_a_jour_ligne(ligne, date_operation=None, libelle=None, debit=None, credit=None, reference=None, user=None):
    _releve_modifiable(ligne.releve)
    if ligne.pointe:
        raise ValueError("Cette ligne est pointée. Elle ne se modifie plus.")
    _exiger_periode_ouverte(ligne.releve.etablissement, ligne.releve.date_fin)
    avant = {
        'libelle': ligne.libelle,
        'debit': str(ligne.debit),
        'credit': str(ligne.credit),
        'date': str(ligne.date_operation),
    }
    if date_operation is not None:
        if date_operation < ligne.releve.date_debut or date_operation > ligne.releve.date_fin:
            raise ValueError("La date de la ligne doit être dans la période du relevé.")
        ligne.date_operation = date_operation
    if libelle is not None:
        texte = libelle.strip()
        if not texte:
            raise ValueError("Le libellé de la ligne est obligatoire.")
        ligne.libelle = texte[:200]
    if debit is not None:
        ligne.debit = _decimal(debit)
    if credit is not None:
        ligne.credit = _decimal(credit)
    if ligne.debit < 0 or ligne.credit < 0:
        raise ValueError("Le débit et le crédit ne peuvent pas être négatifs.")
    if ligne.debit and ligne.credit:
        raise ValueError("Une ligne a un débit ou un crédit, pas les deux.")
    if not ligne.debit and not ligne.credit:
        raise ValueError("Indiquez un débit ou un crédit.")
    if reference is not None:
        ligne.reference = (reference or '')[:80]
    with transaction.atomic():
        ligne.save()
        journaliser(
            ligne.releve.etablissement,
            ligne,
            'modification',
            user=user,
            avant=avant,
            apres={
                'libelle': ligne.libelle,
                'debit': str(ligne.debit),
                'credit': str(ligne.credit),
                'date': str(ligne.date_operation),
            },
        )
    return ligne


def operations_a_rapprocher(releve, hors=None):
    """Écritures validées du compte, dans la période, pas encore pointées."""
    deja = LigneReleve.objects.filter(
        releve__etablissement=releve.etablissement,
        pointe=True,
        ecriture_id__isnull=False,
    ).values_list('ecriture_id', flat=True)
    qs = EcritureComptable.objects.filter(
        etablissement=releve.etablissement,
        validee=True,
        date_ecriture__gte=releve.date_debut,
        date_ecriture__lte=releve.date_fin,
        lignes__compte=releve.compte_tresorerie.compte_comptable,
    ).exclude(pk__in=deja).exclude(source='a_nouveaux').distinct().order_by('date_ecriture', 'id')
    if hors is not None:
        qs = qs.exclude(pk=hors)
    return qs


def candidats_pour_ligne(ligne):
    compte = ligne.releve.compte_tresorerie.compte_comptable
    resultat = []
    for ecriture in operations_a_rapprocher(ligne.releve):
        debit_aria, credit_aria = _montant_aria(ecriture, compte)
        if ligne.credit and debit_aria == ligne.credit and credit_aria == 0:
            resultat.append(ecriture)
        elif ligne.debit and credit_aria == ligne.debit and debit_aria == 0:
            resultat.append(ecriture)
    return resultat


def pointer_ligne(ligne, ecriture, user=None):
    _releve_modifiable(ligne.releve)
    if ligne.pointe:
        raise ValueError("Cette ligne est déjà pointée. Elle ne se modifie plus.")
    if ecriture is None:
        raise ValueError("Choisissez l'opération Aria à rapprocher.")
    if ecriture.etablissement_id != ligne.releve.etablissement_id:
        raise ValueError("Cette écriture n'appartient pas à cette école.")
    if not ecriture.validee:
        raise ValueError("Cette écriture n'est pas validée.")
    _exiger_periode_ouverte(ligne.releve.etablissement, ligne.releve.date_fin)
    if LigneReleve.objects.filter(ecriture=ecriture, pointe=True).exists():
        raise ValueError("Cette opération Aria est déjà pointée.")
    compte = ligne.releve.compte_tresorerie.compte_comptable
    debit_aria, credit_aria = _montant_aria(ecriture, compte)
    if ligne.credit:
        if debit_aria != ligne.credit or credit_aria:
            raise ValueError("Le montant du relevé ne correspond pas à l'écriture Aria.")
    elif ligne.debit:
        if credit_aria != ligne.debit or debit_aria:
            raise ValueError("Le montant du relevé ne correspond pas à l'écriture Aria.")
    else:
        raise ValueError("Cette ligne n'a ni débit ni crédit.")
    mouvement = _mouvement_lie(ecriture)
    with transaction.atomic():
        ligne.pointe = True
        ligne.date_pointage = timezone.now()
        ligne.ecriture = ecriture
        ligne.mouvement = mouvement
        ligne.save(update_fields=['pointe', 'date_pointage', 'ecriture', 'mouvement'])
        _marquer_mouvement_pointe(mouvement, True)
        journaliser(
            ligne.releve.etablissement,
            ligne,
            'rapprochement',
            user=user,
            apres={
                'ecriture': ecriture.numero,
                'mouvement': mouvement.pk if mouvement else None,
            },
        )
    return ligne


def depointer_ligne(ligne, motif, user=None):
    texte = (motif or '').strip()
    if not texte:
        raise ValueError("Le motif est obligatoire pour retirer le pointage.")
    _releve_modifiable(ligne.releve)
    if not ligne.pointe:
        raise ValueError("Cette ligne n'est pas pointée.")
    _exiger_periode_ouverte(ligne.releve.etablissement, ligne.releve.date_fin)
    mouvement = ligne.mouvement
    avec_ecriture = ligne.ecriture_id
    with transaction.atomic():
        ligne.pointe = False
        ligne.date_pointage = None
        ligne.ecriture = None
        ligne.mouvement = None
        ligne.save(update_fields=['pointe', 'date_pointage', 'ecriture', 'mouvement'])
        _marquer_mouvement_pointe(mouvement, False)
        journaliser(
            ligne.releve.etablissement,
            ligne,
            'correction',
            user=user,
            motif=texte,
            avant={'ecriture': avec_ecriture, 'pointe': True},
            apres={'ecriture': None, 'pointe': False},
        )
    return ligne


def cloturer_releve(releve, user=None):
    _releve_modifiable(releve)
    _exiger_periode_ouverte(releve.etablissement, releve.date_fin)
    with transaction.atomic():
        releve.statut = 'cloture'
        releve.save(update_fields=['statut'])
        journaliser(
            releve.etablissement,
            releve,
            'cloture',
            user=user,
            avant={'statut': 'en_cours'},
            apres={'statut': 'cloture'},
        )
    return releve


def synthese_releve(releve):
    lignes = list(releve.lignes.all())
    total_debit = sum((ligne.debit or Decimal('0')) for ligne in lignes)
    total_credit = sum((ligne.credit or Decimal('0')) for ligne in lignes)
    solde_lignes = (releve.solde_ouverture or Decimal('0')) + total_credit - total_debit
    solde_aria = solde_calcule(releve.compte_tresorerie, a_date=releve.date_fin)
    solde_releve = releve.solde_cloture or Decimal('0')
    non_pointees = [ligne for ligne in lignes if not ligne.pointe]
    return {
        'solde_aria': solde_aria,
        'solde_releve': solde_releve,
        'ecart': solde_aria - solde_releve,
        'solde_lignes': solde_lignes,
        'coherence_interne': solde_lignes == solde_releve,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'nb_lignes': len(lignes),
        'nb_non_pointees': len(non_pointees),
        'lignes_non_pointees': non_pointees,
        'operations_non_pointees': list(operations_a_rapprocher(releve)),
    }


def operations_non_pointees_detail(releve):
    compte = releve.compte_tresorerie.compte_comptable
    details = []
    for ecriture in operations_a_rapprocher(releve):
        debit_aria, credit_aria = _montant_aria(ecriture, compte)
        details.append({
            'ecriture': ecriture,
            'debit': debit_aria,
            'credit': credit_aria,
        })
    return details
