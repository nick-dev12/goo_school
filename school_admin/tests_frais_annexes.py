from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from django.http import QueryDict
from django.test import SimpleTestCase

from school_admin.utils.frais_annexes import (
    FRAIS_ANNEXES_CATALOGUE,
    extraire_frais_annexes_depuis_args,
    extraire_frais_annexes_depuis_post,
    frais_annexes_actifs,
    get_frais_annexes_from_parametres,
    normaliser_frais_annexes,
    serialiser_frais_annexes_pour_stockage,
    date_echeance_frais_annexe,
    appliquer_nouveau_montant,
)


class FraisAnnexesCatalogueTests(SimpleTestCase):
    def test_catalogue_couvre_les_frais_typiques(self):
        codes = {item['code'] for item in FRAIS_ANNEXES_CATALOGUE}
        for attendu in (
            'tenue',
            'carte_scolaire',
            'dossier',
            'assurance',
            'examen',
            'transport',
            'cantine',
            'apport',
            'autre',
        ):
            self.assertIn(attendu, codes)

    def test_transport_et_cantine_sont_optionnels(self):
        optionnels = {
            item['code'] for item in FRAIS_ANNEXES_CATALOGUE if item['optionnel']
        }
        self.assertEqual(optionnels, {'transport', 'cantine'})

    def test_normaliser_inactive_par_defaut(self):
        items = normaliser_frais_annexes([])
        self.assertGreaterEqual(len(items), 9)
        self.assertFalse(any(item['actif'] for item in items))

    def test_actifs_uniquement_si_montant_positif(self):
        stored = [
            {
                'code': 'tenue',
                'actif': True,
                'montant': '15000',
                'periodicite': 'annuel',
                'libelle': 'Tenue',
            },
            {
                'code': 'cantine',
                'actif': True,
                'montant': '0',
                'periodicite': 'annuel',
            },
        ]
        actifs = frais_annexes_actifs(stored)
        self.assertEqual([item['code'] for item in actifs], ['tenue'])

    def test_extraire_depuis_post(self):
        post = QueryDict(mutable=True)
        post['frais_annexe_tenue_actif'] = 'on'
        post['frais_annexe_tenue_montant'] = '12000'
        post['frais_annexe_tenue_periodicite'] = 'annuel'
        post['frais_annexe_autre_actif'] = 'on'
        post['frais_annexe_autre_montant'] = '2500'
        post['frais_annexe_autre_libelle'] = 'Frais de laboratoire'
        post['frais_annexe_autre_periodicite'] = 'ponctuel'
        payload = extraire_frais_annexes_depuis_post(post)
        by_code = {item['code']: item for item in payload}
        self.assertTrue(by_code['tenue']['actif'])
        self.assertEqual(by_code['tenue']['montant'], '12000.00')
        self.assertEqual(by_code['autre']['libelle'], 'Frais de laboratoire')
        self.assertFalse(by_code['cantine']['actif'])

    def test_fusion_assistant_preserve_existants(self):
        existants = serialiser_frais_annexes_pour_stockage([
            {'code': 'tenue', 'actif': True, 'montant': '10000', 'periodicite': 'annuel'},
        ])
        merged = extraire_frais_annexes_depuis_args(
            {
                'frais_annexes': [
                    {'code': 'assurance', 'actif': True, 'montant': 5000, 'periodicite': 'annuel'},
                ]
            },
            existants,
        )
        by_code = {item['code']: item for item in merged}
        self.assertTrue(by_code['tenue']['actif'])
        self.assertEqual(by_code['tenue']['montant'], '10000.00')
        self.assertTrue(by_code['assurance']['actif'])
        self.assertEqual(by_code['assurance']['montant'], '5000.00')

    def test_date_echeance_inscription_plus_30_jours(self):
        inscription = Mock(date_inscription=date(2026, 9, 1))
        echeance = date_echeance_frais_annexe('inscription', inscription=inscription)
        self.assertEqual(echeance, date(2026, 10, 1))

    def test_appliquer_nouveau_montant_conserve_paiement(self):
        charge = Mock(
            montant=Decimal('10000'),
            montant_paye=Decimal('4000'),
            reste_a_payer=Decimal('6000'),
            statut='en_attente',
            date_paiement=None,
        )
        appliquer_nouveau_montant(charge, Decimal('15000'))
        self.assertEqual(charge.montant, Decimal('15000'))
        self.assertEqual(charge.reste_a_payer, Decimal('11000'))
        self.assertEqual(charge.statut, 'en_attente')

    def test_get_frais_annexes_from_parametres_none(self):
        items = get_frais_annexes_from_parametres(None)
        self.assertTrue(items)
        self.assertEqual(items[0]['code'], 'tenue')


class FraisAnnexePaiementTests(SimpleTestCase):
    def test_ajouter_paiement_partiel_puis_solde(self):
        class Charge:
            montant = Decimal('10000.00')
            montant_paye = Decimal('0.00')
            reste_a_payer = Decimal('10000.00')
            statut = 'en_attente'
            date_paiement = None

            def est_totalement_paye(self):
                return self.montant_paye >= self.montant

            def save(self, update_fields=None):
                pass

        frais = Charge()

        def ajouter_paiement(self, montant):
            montant_paye_actuel = Decimal(str(self.montant_paye)) if self.montant_paye else Decimal('0.00')
            montant_a_ajouter = Decimal(str(montant))
            nouveau = montant_paye_actuel + montant_a_ajouter
            if nouveau > self.montant:
                nouveau = self.montant
            self.montant_paye = nouveau
            reste = self.montant - nouveau
            self.reste_a_payer = reste if reste > Decimal('0.00') else Decimal('0.00')
            if self.est_totalement_paye():
                self.statut = 'paye'
            else:
                self.statut = 'en_attente'

        ajouter_paiement(frais, Decimal('4000'))
        self.assertEqual(frais.montant_paye, Decimal('4000.00'))
        self.assertEqual(frais.reste_a_payer, Decimal('6000.00'))
        self.assertEqual(frais.statut, 'en_attente')
        ajouter_paiement(frais, Decimal('6000'))
        self.assertEqual(frais.montant_paye, Decimal('10000.00'))
        self.assertEqual(frais.reste_a_payer, Decimal('0.00'))
        self.assertEqual(frais.statut, 'paye')


class AssistantPaiementSchemaTests(SimpleTestCase):
    def test_outils_declares_dans_le_module(self):
        from pathlib import Path

        tools = Path('school_admin/services/assistant_tools.py').read_text()
        actions = Path('school_admin/services/assistant_actions.py').read_text()
        for name in (
            'get_parametres_comptabilite',
            'creer_parametres_comptabilite',
            'modifier_parametres_comptabilite',
            'supprimer_parametres_comptabilite',
            'enregistrer_paiement',
        ):
            self.assertIn(f"'{name}'", tools)
            self.assertIn(name, actions)
