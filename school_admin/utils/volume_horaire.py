"""
Calcul du volume horaire enseignants : EDT publié × période − absences → montant.

Les vacataires sont payés à l'heure. Le tarif (`prix_volume_horaire`) est stocké
sur le professeur mais n'était jamais multiplié. Ce module fait le calcul pur
(sans I/O) pour rester testable.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Optional

JOURS_SEMAINE = (
    'lundi',
    'mardi',
    'mercredi',
    'jeudi',
    'vendredi',
    'samedi',
    'dimanche',
)

PERIODES_VOLUME = ('semaine', 'mois', 'annee')

MOIS_FR = {
    1: 'Janvier',
    2: 'Février',
    3: 'Mars',
    4: 'Avril',
    5: 'Mai',
    6: 'Juin',
    7: 'Juillet',
    8: 'Août',
    9: 'Septembre',
    10: 'Octobre',
    11: 'Novembre',
    12: 'Décembre',
}

NOTE_ABSENCES_ENSEIGNANTS_ABSENTES = (
    "Aucune fiche d'absence enseignant n'est enregistrée dans ARIA. "
    "Les heures à payer égalent les heures planifiées (EDT publié)."
)

_HEURES_QUANTUM = Decimal('0.01')
_MONTANT_QUANTUM = Decimal('0.01')


@dataclass(frozen=True)
class PeriodeVolumeHoraire:
    kind: str
    date_debut: date
    date_fin: date
    label: str

    @property
    def est_vide(self) -> bool:
        return self.date_debut > self.date_fin


@dataclass(frozen=True)
class ResultatVolumeHoraire:
    heures_planifiees: Decimal
    heures: Decimal
    minutes_planifiees: int
    minutes_absences: int
    minutes_a_payer: int
    montant: Optional[Decimal]
    prix_horaire: Optional[Decimal]
    note_absences: Optional[str]
    absences_disponibles: bool
    heures_semaine: Decimal


def lundi_de_la_semaine(jour: date) -> date:
    """Lundi ISO de la semaine contenant `jour`."""
    return jour - timedelta(days=jour.weekday())


def occurrences_jours(date_debut: date, date_fin: date) -> dict[str, int]:
    """Nombre d'occurrences de chaque jour de la semaine sur [debut, fin] inclus."""
    counts = {jour: 0 for jour in JOURS_SEMAINE}
    if date_debut > date_fin:
        return counts
    courant = date_debut
    un_jour = timedelta(days=1)
    while courant <= date_fin:
        counts[JOURS_SEMAINE[courant.weekday()]] += 1
        courant += un_jour
    return counts


def _clip_aux_bornes_annee(
    debut: date,
    fin: date,
    annee_scolaire,
) -> tuple[date, date]:
    if annee_scolaire is None:
        return debut, fin
    annee_debut = getattr(annee_scolaire, 'date_debut', None)
    annee_fin = getattr(annee_scolaire, 'date_fin', None)
    if annee_debut:
        debut = max(debut, annee_debut)
    if annee_fin:
        fin = min(fin, annee_fin)
    return debut, fin


def resoudre_periode(
    kind: str,
    *,
    reference: date,
    annee_scolaire=None,
    clip_annee_scolaire: bool = True,
) -> PeriodeVolumeHoraire:
    """
    Construit une période semaine / mois / année scolaire.

    - semaine : lundi–dimanche ISO contenant `reference`
    - mois : mois calendaire de `reference`
    - annee : bornes de `annee_scolaire` (obligatoire)

    Semaine et mois sont recadrés sur l'année scolaire si elle est fournie,
    pour ne pas compter des jours hors rentrée / vacances d'été.
    """
    kind = (kind or 'mois').strip().lower()
    if kind not in PERIODES_VOLUME:
        kind = 'mois'

    if kind == 'semaine':
        debut = lundi_de_la_semaine(reference)
        fin = debut + timedelta(days=6)
        if clip_annee_scolaire:
            debut, fin = _clip_aux_bornes_annee(debut, fin, annee_scolaire)
        label = f"Semaine du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}"
    elif kind == 'annee':
        if annee_scolaire is None or not getattr(annee_scolaire, 'date_debut', None):
            raise ValueError("L'année scolaire est requise pour la période annuelle.")
        debut = annee_scolaire.date_debut
        fin = annee_scolaire.date_fin
        libelle = getattr(annee_scolaire, 'libelle', '') or ''
        label = f"Année scolaire {libelle}".strip()
    else:
        debut = date(reference.year, reference.month, 1)
        dernier_jour = monthrange(reference.year, reference.month)[1]
        fin = date(reference.year, reference.month, dernier_jour)
        if clip_annee_scolaire:
            debut, fin = _clip_aux_bornes_annee(debut, fin, annee_scolaire)
        label = f"{MOIS_FR[reference.month]} {reference.year}"

    if debut > fin:
        label = f"{label} — hors année scolaire"

    return PeriodeVolumeHoraire(kind=kind, date_debut=debut, date_fin=fin, label=label)


def _est_pause(creneau) -> bool:
    if getattr(creneau, 'est_pause', False):
        return True
    return getattr(creneau, 'type_cours', None) == 'pause'


def _duree_minutes_creneau(creneau) -> int:
    try:
        minutes = int(creneau.duree_minutes)
    except (TypeError, ValueError, AttributeError):
        return 0
    return max(0, minutes)


def minutes_planifiees_periode(
    creneaux: Iterable,
    occurrences: Mapping[str, int],
) -> int:
    """Minutes EDT sur la période = Σ (durée du créneau × occurrences du jour)."""
    total = 0
    for creneau in creneaux:
        if _est_pause(creneau):
            continue
        jour = getattr(creneau, 'jour', None)
        if jour not in occurrences:
            continue
        total += _duree_minutes_creneau(creneau) * int(occurrences.get(jour, 0))
    return total


def minutes_semaine_planifiees(creneaux: Iterable) -> int:
    """Volume hebdomadaire d'une grille EDT (une occurrence par jour de grille)."""
    total = 0
    for creneau in creneaux:
        if _est_pause(creneau):
            continue
        total += _duree_minutes_creneau(creneau)
    return total


def minutes_vers_heures(minutes: int) -> Decimal:
    return (Decimal(max(0, int(minutes))) / Decimal(60)).quantize(
        _HEURES_QUANTUM, rounding=ROUND_HALF_UP
    )


def montant_a_payer(heures: Decimal, prix_horaire) -> Optional[Decimal]:
    if prix_horaire is None:
        return None
    try:
        tarif = Decimal(str(prix_horaire))
    except Exception:
        return None
    if tarif < 0:
        tarif = Decimal('0')
    return (Decimal(heures) * tarif).quantize(_MONTANT_QUANTUM, rounding=ROUND_HALF_UP)


def calculer_volume_horaire(
    creneaux: Iterable,
    periode: PeriodeVolumeHoraire,
    prix_horaire,
    *,
    minutes_absences: int = 0,
    absences_disponibles: bool = False,
) -> ResultatVolumeHoraire:
    """
    Heures planifiées (EDT publié sur la période) − absences justifiées → montant.

    Si aucun modèle d'absence enseignant n'existe, passer
    `absences_disponibles=False` (défaut) : les absences valent 0 et une note
    explicite est jointe au résultat.
    """
    if periode.est_vide:
        occurrences = {jour: 0 for jour in JOURS_SEMAINE}
        minutes_planifiees = 0
    else:
        occurrences = occurrences_jours(periode.date_debut, periode.date_fin)
        minutes_planifiees = minutes_planifiees_periode(creneaux, occurrences)

    absences = max(0, int(minutes_absences or 0))
    if not absences_disponibles:
        absences = 0

    minutes_a_payer = max(0, minutes_planifiees - absences)
    heures_planifiees = minutes_vers_heures(minutes_planifiees)
    heures = minutes_vers_heures(minutes_a_payer)
    tarif = None if prix_horaire is None else Decimal(str(prix_horaire))
    montant = montant_a_payer(heures, tarif)
    note = None if absences_disponibles else NOTE_ABSENCES_ENSEIGNANTS_ABSENTES

    return ResultatVolumeHoraire(
        heures_planifiees=heures_planifiees,
        heures=heures,
        minutes_planifiees=minutes_planifiees,
        minutes_absences=absences,
        minutes_a_payer=minutes_a_payer,
        montant=montant,
        prix_horaire=tarif,
        note_absences=note,
        absences_disponibles=absences_disponibles,
        heures_semaine=minutes_vers_heures(minutes_semaine_planifiees(creneaux)),
    )
