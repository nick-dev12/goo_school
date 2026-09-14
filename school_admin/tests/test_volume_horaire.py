"""Tests du calculateur volume horaire → montant à payer."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from school_admin.utils.volume_horaire import (
    NOTE_ABSENCES_ENSEIGNANTS_ABSENTES,
    calculer_volume_horaire,
    lundi_de_la_semaine,
    minutes_planifiees_periode,
    minutes_semaine_planifiees,
    minutes_vers_heures,
    montant_a_payer,
    occurrences_jours,
    resoudre_periode,
)


def _slot(jour, minutes, *, pause=False, type_cours='cours'):
    return SimpleNamespace(
        jour=jour,
        duree_minutes=minutes,
        est_pause=pause,
        type_cours=type_cours,
    )


def _annee(debut, fin, libelle='2025-2026'):
    return SimpleNamespace(date_debut=debut, date_fin=fin, libelle=libelle)


class OccurrencesJoursTests(TestCase):
    def test_semaine_complete_une_occurrence_par_jour(self):
        counts = occurrences_jours(date(2026, 9, 14), date(2026, 9, 20))
        self.assertEqual(counts['lundi'], 1)
        self.assertEqual(counts['dimanche'], 1)
        self.assertEqual(sum(counts.values()), 7)

    def test_septembre_2026_lundis_et_mardis(self):
        counts = occurrences_jours(date(2026, 9, 1), date(2026, 9, 30))
        # 1er septembre 2026 = mardi
        self.assertEqual(counts['mardi'], 5)
        self.assertEqual(counts['lundi'], 4)
        self.assertEqual(sum(counts.values()), 30)

    def test_periode_vide(self):
        counts = occurrences_jours(date(2026, 9, 10), date(2026, 9, 1))
        self.assertEqual(sum(counts.values()), 0)


class ResoudrePeriodeTests(TestCase):
    def test_semaine_iso_lundi_dimanche(self):
        periode = resoudre_periode(
            'semaine',
            reference=date(2026, 9, 16),
            clip_annee_scolaire=False,
        )
        self.assertEqual(periode.date_debut, date(2026, 9, 14))
        self.assertEqual(periode.date_fin, date(2026, 9, 20))
        self.assertEqual(periode.kind, 'semaine')

    def test_mois_calendaire(self):
        periode = resoudre_periode(
            'mois',
            reference=date(2026, 9, 14),
            clip_annee_scolaire=False,
        )
        self.assertEqual(periode.date_debut, date(2026, 9, 1))
        self.assertEqual(periode.date_fin, date(2026, 9, 30))
        self.assertIn('Septembre', periode.label)

    def test_annee_scolaire_utilise_les_bornes(self):
        annee = _annee(date(2025, 9, 15), date(2026, 6, 30))
        periode = resoudre_periode('annee', reference=date(2026, 1, 1), annee_scolaire=annee)
        self.assertEqual(periode.date_debut, date(2025, 9, 15))
        self.assertEqual(periode.date_fin, date(2026, 6, 30))
        self.assertIn('2025-2026', periode.label)

    def test_mois_clippe_sur_rentree(self):
        annee = _annee(date(2025, 9, 15), date(2026, 6, 30))
        periode = resoudre_periode(
            'mois',
            reference=date(2025, 9, 20),
            annee_scolaire=annee,
        )
        self.assertEqual(periode.date_debut, date(2025, 9, 15))
        self.assertEqual(periode.date_fin, date(2025, 9, 30))

    def test_mois_hors_annee_scolaire_est_vide(self):
        annee = _annee(date(2025, 9, 15), date(2026, 6, 30))
        periode = resoudre_periode(
            'mois',
            reference=date(2025, 8, 1),
            annee_scolaire=annee,
        )
        self.assertTrue(periode.est_vide)
        self.assertIn('hors année scolaire', periode.label)

    def test_annee_sans_session_leve(self):
        with self.assertRaises(ValueError):
            resoudre_periode('annee', reference=date(2026, 1, 1), annee_scolaire=None)

    def test_lundi_de_la_semaine(self):
        self.assertEqual(lundi_de_la_semaine(date(2026, 9, 16)), date(2026, 9, 14))


class MinutesEdtTests(TestCase):
    def test_pause_exclue(self):
        slots = [
            _slot('lundi', 60),
            _slot('lundi', 15, pause=True),
            _slot('mardi', 120, type_cours='pause'),
        ]
        occ = {'lundi': 1, 'mardi': 1}
        self.assertEqual(minutes_planifiees_periode(slots, occ), 60)
        self.assertEqual(minutes_semaine_planifiees(slots), 60)

    def test_occurrences_multiplient_la_duree(self):
        slots = [_slot('lundi', 90), _slot('mercredi', 60)]
        occ = {'lundi': 4, 'mercredi': 5}
        # 90*4 + 60*5 = 360 + 300 = 660
        self.assertEqual(minutes_planifiees_periode(slots, occ), 660)


class MontantTests(TestCase):
    def test_heures_arrondies_au_centieme(self):
        self.assertEqual(minutes_vers_heures(90), Decimal('1.50'))
        self.assertEqual(minutes_vers_heures(50), Decimal('0.83'))

    def test_montant_heures_fois_tarif(self):
        self.assertEqual(
            montant_a_payer(Decimal('12.50'), Decimal('4000')),
            Decimal('50000.00'),
        )

    def test_sans_tarif_montant_none(self):
        self.assertIsNone(montant_a_payer(Decimal('10'), None))


class CalculerVolumeHoraireTests(TestCase):
    def test_semaine_montant_egal_heures_fois_tarif(self):
        slots = [_slot('lundi', 120), _slot('jeudi', 60)]
        periode = resoudre_periode(
            'semaine',
            reference=date(2026, 9, 16),
            clip_annee_scolaire=False,
        )
        resultat = calculer_volume_horaire(slots, periode, Decimal('3500'))
        # 2 h + 1 h = 3 h × 3500
        self.assertEqual(resultat.heures_planifiees, Decimal('3.00'))
        self.assertEqual(resultat.heures, Decimal('3.00'))
        self.assertEqual(resultat.montant, Decimal('10500.00'))
        self.assertEqual(resultat.heures_semaine, Decimal('3.00'))
        self.assertEqual(resultat.note_absences, NOTE_ABSENCES_ENSEIGNANTS_ABSENTES)
        self.assertFalse(resultat.absences_disponibles)

    def test_sans_modele_absence_on_ignore_les_minutes_fournies(self):
        slots = [_slot('lundi', 180)]
        periode = resoudre_periode(
            'semaine',
            reference=date(2026, 9, 14),
            clip_annee_scolaire=False,
        )
        resultat = calculer_volume_horaire(
            slots,
            periode,
            Decimal('2000'),
            minutes_absences=60,
            absences_disponibles=False,
        )
        self.assertEqual(resultat.heures, Decimal('3.00'))
        self.assertEqual(resultat.minutes_absences, 0)
        self.assertEqual(resultat.montant, Decimal('6000.00'))

    def test_absences_justifiees_soustraites_si_disponibles(self):
        slots = [_slot('lundi', 180)]
        periode = resoudre_periode(
            'semaine',
            reference=date(2026, 9, 14),
            clip_annee_scolaire=False,
        )
        resultat = calculer_volume_horaire(
            slots,
            periode,
            Decimal('2000'),
            minutes_absences=60,
            absences_disponibles=True,
        )
        self.assertEqual(resultat.heures_planifiees, Decimal('3.00'))
        self.assertEqual(resultat.heures, Decimal('2.00'))
        self.assertEqual(resultat.montant, Decimal('4000.00'))
        self.assertIsNone(resultat.note_absences)

    def test_mois_compte_chaque_occurrence_du_jour(self):
        slots = [_slot('mardi', 60)]
        periode = resoudre_periode(
            'mois',
            reference=date(2026, 9, 1),
            clip_annee_scolaire=False,
        )
        resultat = calculer_volume_horaire(slots, periode, Decimal('1000'))
        # 5 mardis en septembre 2026
        self.assertEqual(resultat.heures_planifiees, Decimal('5.00'))
        self.assertEqual(resultat.montant, Decimal('5000.00'))

    def test_periode_vide_zero(self):
        annee = _annee(date(2025, 9, 15), date(2026, 6, 30))
        periode = resoudre_periode(
            'mois',
            reference=date(2025, 8, 10),
            annee_scolaire=annee,
        )
        resultat = calculer_volume_horaire([_slot('lundi', 60)], periode, Decimal('1000'))
        self.assertEqual(resultat.heures, Decimal('0.00'))
        self.assertEqual(resultat.montant, Decimal('0.00'))

    def test_sans_tarif_montant_none_heures_calculees(self):
        slots = [_slot('vendredi', 45)]
        periode = resoudre_periode(
            'semaine',
            reference=date(2026, 9, 18),
            clip_annee_scolaire=False,
        )
        resultat = calculer_volume_horaire(slots, periode, None)
        self.assertEqual(resultat.heures, Decimal('0.75'))
        self.assertIsNone(resultat.montant)
