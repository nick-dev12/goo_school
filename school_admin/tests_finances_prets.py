"""Prêt : dette et trésorerie, pas un produit. Capital hors résultat. Intérêts et frais en charges."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable, LigneEcriture, PeriodeComptable
from school_admin.model.finances_model import PretEtablissement
from school_admin.services.comptabilite_generale import (
    COMPTE_EMPRUNTS,
    COMPTE_FRAIS_EMPRUNTS,
    COMPTE_INTERETS_EMPRUNTS,
    PLAN_SYSCOHADA_EDUCATION,
    ensure_exercice,
    ensure_plan_comptable,
    synthese_bilan,
)
from school_admin.services.finances.prets import (
    ajouter_echeance,
    annuler_pret,
    annuler_remboursement,
    enregistrer_pret,
    enregistrer_remboursement,
)
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal, solde_calcule
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class PretsTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('prt')
        self.annee = _make_annee(self.etab)
        ensure_plan_comptable(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.banque = compte_principal(self.etab, 'banque')
        self.exercice = ensure_exercice(self.etab, self.annee)

    def _lignes(self, ecriture):
        return {
            ligne.compte.numero: (ligne.debit, ligne.credit)
            for ligne in ecriture.lignes.select_related('compte')
        }

    def test_plan_contient_les_comptes_de_pret(self):
        numeros = {row[0] for row in PLAN_SYSCOHADA_EDUCATION}
        self.assertIn(COMPTE_EMPRUNTS, numeros)
        self.assertIn(COMPTE_INTERETS_EMPRUNTS, numeros)
        self.assertIn(COMPTE_FRAIS_EMPRUNTS, numeros)

    def test_reception_debite_la_banque_et_credite_la_dette(self):
        avant = synthese_bilan(self.etab, self.exercice)
        pret, ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('20000000'),
            reference='EMP-1', objet='Travaux', annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['521'], (Decimal('20000000'), Decimal('0')))
        self.assertEqual(lignes['1621'], (Decimal('0'), Decimal('20000000')))
        self.assertFalse(LigneEcriture.objects.filter(ecriture=ecriture, compte__classe__in=['6', '7']).exists())
        self.assertEqual(pret.capital_restant(), Decimal('20000000'))
        self.assertEqual(solde_calcule(self.banque), Decimal('20000000'))
        apres = synthese_bilan(self.etab, self.exercice)
        self.assertEqual(apres['produits'], avant['produits'])
        self.assertEqual(apres['charges'], avant['charges'])
        self.assertEqual(apres['resultat'], avant['resultat'])

    def test_remboursement_separe_capital_interets_et_frais(self):
        pret, _ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('20000000'),
            reference='EMP-2', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        avant = synthese_bilan(self.etab, self.exercice)['charges']
        avant_ecritures = EcritureComptable.objects.filter(etablissement=self.etab).count()
        ajouter_echeance(pret, self.jour, Decimal('500000'), Decimal('100000'), Decimal('10000'))
        self.assertEqual(EcritureComptable.objects.filter(etablissement=self.etab).count(), avant_ecritures)
        remboursement, ecriture = enregistrer_remboursement(
            pret, self.jour,
            capital=Decimal('500000'), interets=Decimal('100000'), frais=Decimal('10000'),
            motif='Échéance 1', user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['1621'], (Decimal('500000'), Decimal('0')))
        self.assertEqual(lignes['6711'], (Decimal('100000'), Decimal('0')))
        self.assertEqual(lignes['6712'], (Decimal('10000'), Decimal('0')))
        self.assertEqual(lignes['521'], (Decimal('0'), Decimal('610000')))
        self.assertFalse(LigneEcriture.objects.filter(ecriture=ecriture, compte__classe='7').exists())
        pret.refresh_from_db()
        self.assertEqual(pret.montant, Decimal('20000000'))
        self.assertEqual(pret.capital_restant(), Decimal('19500000'))
        self.assertEqual(pret.statut, 'en_cours')
        self.assertEqual(remboursement.total, Decimal('610000'))
        self.assertEqual(solde_calcule(self.banque), Decimal('19390000'))
        charges = synthese_bilan(self.etab, self.exercice)['charges']
        self.assertEqual(charges - avant, Decimal('110000'))

    def test_capital_au_dela_du_restant_est_refuse(self):
        pret, _ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('1000'),
            reference='EMP-3', objet='Court', annee_scolaire=self.annee, user=self.etab,
        )
        with self.assertRaises(ValueError):
            enregistrer_remboursement(
                pret, self.jour, capital=Decimal('1001'), motif='Trop', user=self.etab,
            )
        pret.refresh_from_db()
        self.assertEqual(pret.capital_restant(), Decimal('1000'))
        self.assertEqual(pret.remboursements.count(), 0)
        self.assertEqual(solde_calcule(self.banque), Decimal('1000'))

    def test_annulation_restaure_la_dette_puis_le_pret(self):
        pret, _ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('800'),
            reference='EMP-4', objet='Test', annee_scolaire=self.annee, user=self.etab,
        )
        remboursement, _piece = enregistrer_remboursement(
            pret, self.jour, capital=Decimal('800'), motif='Solde', user=self.etab,
        )
        pret.refresh_from_db()
        self.assertEqual(pret.statut, 'solde')
        self.assertEqual(pret.capital_restant(), Decimal('0'))
        with self.assertRaises(ValueError):
            annuler_pret(pret, 'Trop tôt', user=self.etab)
        annuler_remboursement(remboursement, 'Erreur', user=self.etab)
        pret.refresh_from_db()
        self.assertEqual(pret.statut, 'en_cours')
        self.assertEqual(pret.montant, Decimal('800'))
        self.assertEqual(pret.capital_restant(), Decimal('800'))
        annuler_pret(pret, 'Vérification', user=self.etab)
        pret.refresh_from_db()
        self.assertEqual(pret.statut, 'annulee')
        self.assertEqual(pret.capital_restant(), Decimal('0'))
        self.assertEqual(solde_calcule(self.banque), Decimal('0'))
        self.assertTrue(PretEtablissement.objects.filter(pk=pret.pk).exists())

    def test_periode_verrouillee_et_autre_ecole(self):
        PeriodeComptable.objects.filter(exercice=self.exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            enregistrer_pret(
                self.etab, self.banque, self.jour, Decimal('50'),
                reference='EMP-5', objet='Bloqué', annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(PretEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        autre = _make_etablissement('pr2')
        ensure_plan_comptable(autre)
        assurer_comptes_defaut(autre)
        with self.assertRaises(ValueError):
            enregistrer_pret(
                self.etab, compte_principal(autre, 'banque'), self.jour, Decimal('40'),
                reference='EMP-6', objet='Ailleurs', annee_scolaire=self.annee, user=self.etab,
            )
