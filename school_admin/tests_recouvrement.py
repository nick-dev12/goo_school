from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from django.test import SimpleTestCase

from school_admin.services.recouvrement import (
    calculer_remise_fratrie,
    construire_message_relance,
    eleve_eligible_relance_auto,
    formater_numero_recu,
    verifier_rupture_moratoire,
    ResumeDette,
)


class RemiseFratrieTests(SimpleTestCase):
    def _params(self, **kwargs):
        params = Mock()
        params.appliquer_remise_famille_nombreuse = kwargs.get('flag', True)
        params.pourcentage_remise_famille_nombreuse = kwargs.get('pct', Decimal('10.00'))
        params.nombre_enfants_minimum_remise = kwargs.get('min_enfants', 3)
        return params

    def test_applique_si_seuil_atteint(self):
        result = calculer_remise_fratrie(Decimal('20000'), self._params(), 3)
        self.assertTrue(result.applicable)
        self.assertEqual(result.montant_remise, Decimal('2000.00'))
        self.assertEqual(result.montant_net, Decimal('18000.00'))

    def test_ignoree_si_flag_off(self):
        result = calculer_remise_fratrie(Decimal('20000'), self._params(flag=False), 4)
        self.assertFalse(result.applicable)
        self.assertEqual(result.montant_net, Decimal('20000.00'))

    def test_ignoree_si_fratrie_insuffisante(self):
        result = calculer_remise_fratrie(Decimal('20000'), self._params(), 2)
        self.assertFalse(result.applicable)
        self.assertEqual(result.montant_remise, Decimal('0.00'))

    def test_applique_sur_charge_non_payee(self):
        from school_admin.services.recouvrement import appliquer_remise_sur_charge

        charge = Mock()
        charge.montant = Decimal('15000')
        charge.montant_brut = None
        charge.montant_paye = Decimal('0.00')
        charge.remise_fratrie = Decimal('0.00')
        charge.reste_a_payer = Decimal('15000')
        saved = {}

        def save(update_fields=None):
            saved['fields'] = update_fields

        charge.save = save
        appliquer_remise_sur_charge(charge, self._params(pct=Decimal('10')), 3)
        self.assertEqual(charge.montant, Decimal('13500.00'))
        self.assertEqual(charge.remise_fratrie, Decimal('1500.00'))
        self.assertTrue(saved['fields'])

    def test_ne_modifie_pas_charge_deja_payee(self):
        from school_admin.services.recouvrement import appliquer_remise_sur_charge

        charge = Mock()
        charge.montant = Decimal('15000')
        charge.montant_brut = Decimal('15000')
        charge.montant_paye = Decimal('5000')
        charge.remise_fratrie = Decimal('0.00')
        charge.save = Mock()
        appliquer_remise_sur_charge(charge, self._params(), 3)
        charge.save.assert_not_called()
        self.assertEqual(charge.montant, Decimal('15000'))


class RecuEtRelanceTests(SimpleTestCase):
    def test_numero_recu_sequentiel(self):
        self.assertEqual(formater_numero_recu(2025, 1), 'REC-2025-00001')
        self.assertEqual(formater_numero_recu(2026, 42), 'REC-2026-00042')

    def test_message_relance_contient_dette_et_echeance(self):
        eleve = Mock(nom='Diallo', prenom='Awa', nom_complet='Diallo Awa')
        etablissement = Mock(nom='Lycée ARIA', devise_monnaie='XOF')
        resume = ResumeDette(
            reste=Decimal('45000'),
            prochaine_echeance=date(2026, 10, 5),
            prochaine_libelle='Octobre 2026',
        )
        message = construire_message_relance(eleve, resume, etablissement)
        self.assertIn('45000', message)
        self.assertIn('XOF', message)
        self.assertIn('05/10/2026', message)
        self.assertIn('Diallo Awa', message)

    def test_eligible_avant_echeance(self):
        params = Mock(
            envoyer_rappels_automatiques=True,
            jours_avant_rappel=7,
            jours_apres_retard_rappel=3,
        )
        resume = ResumeDette(
            reste=Decimal('10000'),
            prochaine_echeance=date(2026, 9, 20),
        )
        self.assertTrue(eleve_eligible_relance_auto(resume, params, date(2026, 9, 14)))

    def test_eligible_apres_retard(self):
        params = Mock(
            envoyer_rappels_automatiques=True,
            jours_avant_rappel=7,
            jours_apres_retard_rappel=3,
        )
        resume = ResumeDette(
            reste=Decimal('10000'),
            prochaine_echeance=date(2026, 9, 10),
        )
        self.assertTrue(eleve_eligible_relance_auto(resume, params, date(2026, 9, 14)))
        self.assertFalse(eleve_eligible_relance_auto(resume, params, date(2026, 9, 11)))

    def test_ineligible_si_flag_off_ou_solde(self):
        params = Mock(
            envoyer_rappels_automatiques=False,
            jours_avant_rappel=7,
            jours_apres_retard_rappel=3,
        )
        resume = ResumeDette(reste=Decimal('10000'), prochaine_echeance=date(2026, 9, 20))
        self.assertFalse(eleve_eligible_relance_auto(resume, params, date(2026, 9, 14)))
        params.envoyer_rappels_automatiques = True
        solde = ResumeDette(reste=Decimal('0.00'), prochaine_echeance=date(2026, 9, 20))
        self.assertFalse(eleve_eligible_relance_auto(solde, params, date(2026, 9, 14)))


class MoratoireRuptureTests(SimpleTestCase):
    def test_rupture_si_echeance_impayee_passee(self):
        echeance = Mock()
        echeance.est_totalement_paye.return_value = False
        echeance.date_echeance = date(2026, 9, 1)
        echeance.statut = 'en_attente'
        echeance.save = Mock()

        moratoire = Mock()
        moratoire.statut = 'actif'
        moratoire.echeances.all.return_value = [echeance]
        moratoire.save = Mock()

        rompu = verifier_rupture_moratoire(moratoire, aujourdhui=date(2026, 9, 14))
        self.assertTrue(rompu)
        self.assertEqual(moratoire.statut, 'rompu')
        echeance.save.assert_called()
        moratoire.save.assert_called()

    def test_solde_si_toutes_payees(self):
        echeance = Mock()
        echeance.est_totalement_paye.return_value = True
        echeance.date_echeance = date(2026, 9, 1)
        moratoire = Mock()
        moratoire.statut = 'actif'
        moratoire.echeances.all.return_value = [echeance]
        moratoire.save = Mock()
        rompu = verifier_rupture_moratoire(moratoire, aujourdhui=date(2026, 9, 14))
        self.assertFalse(rompu)
        self.assertEqual(moratoire.statut, 'solde')
