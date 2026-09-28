"""Caisse du mois : recettes (paiements élèves) − dépenses école."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.db.models import Sum

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_eleve_model import PaiementEleve

_QUANTUM = Decimal('0.01')


@dataclass(frozen=True)
class BornesMois:
    debut: date
    fin: date
    label: str
    valeur: str  # YYYY-MM


def bornes_mois(reference: date) -> BornesMois:
    debut = date(reference.year, reference.month, 1)
    fin = date(reference.year, reference.month, monthrange(reference.year, reference.month)[1])
    mois_fr = (
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
    )
    return BornesMois(
        debut=debut,
        fin=fin,
        label=f"{mois_fr[reference.month]} {reference.year}",
        valeur=f"{reference.year:04d}-{reference.month:02d}",
    )


def parser_mois(valeur, fallback: date) -> date:
    if not valeur:
        return date(fallback.year, fallback.month, 1)
    try:
        annee_s, mois_s = str(valeur).split('-', 1)
        return date(int(annee_s), int(mois_s), 1)
    except (TypeError, ValueError):
        return date(fallback.year, fallback.month, 1)


def _dec(valeur) -> Decimal:
    if valeur is None:
        return Decimal('0.00')
    return Decimal(str(valeur)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def parser_montant(valeur) -> Decimal | None:
    texte = str(valeur or '').strip().replace(' ', '').replace(',', '.')
    if not texte:
        return None
    try:
        montant = Decimal(texte)
    except (InvalidOperation, ValueError):
        return None
    if montant <= 0:
        return None
    return montant.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def net_apres_retenue(brut, retenue_pct) -> Decimal:
    brut_d = _dec(brut)
    try:
        pct = Decimal(str(retenue_pct or 0))
    except (InvalidOperation, ValueError):
        pct = Decimal('0')
    if pct < 0:
        pct = Decimal('0')
    if pct > 100:
        pct = Decimal('100')
    retenue = (brut_d * pct / Decimal('100')).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    return (brut_d - retenue).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def recettes_mois(etablissement, debut: date, fin: date):
    return (
        PaiementEleve.objects.filter(
            etablissement=etablissement,
            date_paiement__date__gte=debut,
            date_paiement__date__lte=fin,
        )
        .select_related('eleve')
        .order_by('-date_paiement')
    )


def total_recettes(etablissement, debut: date, fin: date) -> Decimal:
    total = recettes_mois(etablissement, debut, fin).aggregate(s=Sum('montant'))['s']
    return _dec(total)


def depenses_mois(etablissement, debut: date, fin: date):
    return DepenseEtablissement.objects.filter(
        etablissement=etablissement,
        date_depense__gte=debut,
        date_depense__lte=fin,
    )


def total_depenses(etablissement, debut: date, fin: date) -> Decimal:
    total = depenses_mois(etablissement, debut, fin).aggregate(s=Sum('montant'))['s']
    return _dec(total)


def solde_mois(etablissement, debut: date, fin: date) -> Decimal:
    return total_recettes(etablissement, debut, fin) - total_depenses(etablissement, debut, fin)
