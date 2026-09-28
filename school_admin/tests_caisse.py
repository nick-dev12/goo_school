from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from school_admin.services.caisse import bornes_mois, net_apres_retenue, parser_mois, parser_montant
from school_admin.utils.volume_horaire import minutes_creneaux_pour_date


class CaisseCalculTests(TestCase):
    def test_bornes_septembre_2026(self):
        bornes = bornes_mois(date(2026, 9, 14))
        self.assertEqual(bornes.debut, date(2026, 9, 1))
        self.assertEqual(bornes.fin, date(2026, 9, 30))
        self.assertEqual(bornes.valeur, '2026-09')
        self.assertIn('Septembre', bornes.label)

    def test_parser_mois_invalide_revient_au_mois_courant(self):
        fallback = date(2026, 8, 3)
        parsed = parser_mois('pas-un-mois', fallback)
        self.assertEqual(parsed, date(2026, 8, 1))

    def test_parser_montant_refuse_zero_et_texte(self):
        self.assertIsNone(parser_montant('0'))
        self.assertIsNone(parser_montant('abc'))
        self.assertEqual(parser_montant('1500,5'), Decimal('1500.50'))

    def test_net_apres_retenue(self):
        self.assertEqual(net_apres_retenue(Decimal('10000'), Decimal('10')), Decimal('9000.00'))
        self.assertEqual(net_apres_retenue(Decimal('10000'), Decimal('0')), Decimal('10000.00'))
        self.assertEqual(net_apres_retenue(Decimal('10000'), Decimal('200')), Decimal('0.00'))


class MinutesCreneauJourTests(TestCase):
    def test_compte_uniquement_le_jour(self):
        creneaux = [
            SimpleNamespace(jour='lundi', duree_minutes=120, est_pause=False, type_cours='cours'),
            SimpleNamespace(jour='mardi', duree_minutes=60, est_pause=False, type_cours='cours'),
        ]
        # 14 septembre 2026 = lundi
        self.assertEqual(minutes_creneaux_pour_date(creneaux, date(2026, 9, 14)), 120)
        self.assertEqual(minutes_creneaux_pour_date(creneaux, date(2026, 9, 15)), 60)
