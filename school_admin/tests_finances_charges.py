"""Factures fournisseurs : plusieurs paiements, deux régimes, pas de double sortie."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_generale_model import (
    EcritureComptable,
    FactureFournisseur,
    FournisseurEtablissement,
    LigneEcriture,
    PeriodeComptable,
)
from school_admin.model.finances_model import CategorieFinanciere, PaiementCharge
from school_admin.services.comptabilite_generale import (
    REGIME_TRESORERIE,
    enregistrer_regime_comptable,
    ensure_exercice,
    ensure_plan_comptable,
)
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.charges import (
    annuler_facture,
    annuler_paiement,
    enregistrer_facture,
    enregistrer_paiement,
    factures_historique_sans_lignes,
)
from school_admin.services.finances.operations import enregistrer_sortie
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class ChargesFacturesTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('fac')
        self.annee = _make_annee(self.etab)
        ensure_plan_comptable(self.etab)
        assurer_categories(self.etab)
        self.jour = timezone.now().date()
        self.fournisseur = FournisseurEtablissement.objects.create(
            etablissement=self.etab, nom='Senelec'
        )
        self.categorie = CategorieFinanciere.objects.get(
            etablissement=self.etab, libelle='Électricité / eau'
        )

    def _facture(self, montant='450', numero='F-1'):
        return enregistrer_facture(
            self.etab,
            self.fournisseur,
            numero,
            'Courant',
            Decimal(montant),
            self.jour,
            self.jour,
            self.categorie,
            annee_scolaire=self.annee,
            user=self.etab,
        )

    def test_engagement_plusieurs_paiements_sans_montant_paye(self):
        facture, ecriture = self._facture()
        self.assertIsNotNone(ecriture)
        self.assertEqual(
            LigneEcriture.objects.get(ecriture=ecriture, compte__numero='605').debit,
            Decimal('450'),
        )
        self.assertEqual(
            LigneEcriture.objects.get(ecriture=ecriture, compte__numero='401').credit,
            Decimal('450'),
        )
        enregistrer_paiement(facture, self.jour, Decimal('300'), annee_scolaire=self.annee, user=self.etab)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'partiel')
        self.assertEqual(facture.reste_a_payer(), Decimal('150'))
        enregistrer_paiement(facture, self.jour, Decimal('150'), annee_scolaire=self.annee, user=self.etab)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'payee')
        self.assertEqual(facture.reste_a_payer(), Decimal('0'))
        self.assertEqual(facture.montant_paye, Decimal('0'))
        self.assertEqual(DepenseEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        with self.assertRaises(ValueError):
            enregistrer_paiement(facture, self.jour, Decimal('1'), annee_scolaire=self.annee, user=self.etab)
        self.assertEqual(PaiementCharge.objects.filter(facture=facture).count(), 2)

    def test_tresorerie_passe_la_charge_au_paiement(self):
        enregistrer_regime_comptable(self.etab, REGIME_TRESORERIE, annee_scolaire=self.annee)
        facture, ecriture = self._facture(montant='80', numero='F-T')
        self.assertIsNone(ecriture)
        self.assertFalse(EcritureComptable.objects.filter(source='facture', source_id=facture.id).exists())
        paiement, piece = enregistrer_paiement(
            facture, self.jour, Decimal('80'), annee_scolaire=self.annee, user=self.etab
        )
        self.assertIsNotNone(piece)
        self.assertEqual(
            LigneEcriture.objects.get(ecriture=piece, compte__numero='605').debit,
            Decimal('80'),
        )
        self.assertFalse(LigneEcriture.objects.filter(ecriture=piece, compte__numero='401').exists())
        self.assertEqual(paiement.facture_id, facture.id)

    def test_ancien_montant_paye_est_signale_sans_ligne_inventee(self):
        facture = FactureFournisseur.objects.create(
            etablissement=self.etab,
            fournisseur=self.fournisseur,
            numero='OLD',
            libelle='Archive',
            date_facture=self.jour,
            date_echeance=self.jour,
            montant=Decimal('200'),
            montant_paye=Decimal('80'),
            categorie=self.categorie,
        )
        self.assertEqual(factures_historique_sans_lignes(self.etab).count(), 1)
        self.assertEqual(PaiementCharge.objects.filter(facture=facture).count(), 0)
        self.assertEqual(facture.reste_a_payer(), Decimal('200'))

    def test_sortie_immediate_refusee_si_facture_ouverte(self):
        self._facture(montant='100', numero='F-D')
        with self.assertRaises(ValueError):
            enregistrer_sortie(
                self.etab,
                self.jour,
                'electricite',
                Decimal('100'),
                annee_scolaire=self.annee,
                user=self.etab,
                fournisseur=self.fournisseur,
            )
        self.assertEqual(DepenseEtablissement.objects.filter(etablissement=self.etab).count(), 0)

    def test_periode_verrouillee_n_enregistre_pas_la_facture(self):
        exercice = ensure_exercice(self.etab, self.annee)
        PeriodeComptable.objects.filter(exercice=exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            self._facture(numero='F-LOCK')
        self.assertEqual(FactureFournisseur.objects.filter(etablissement=self.etab).count(), 0)

    def test_annulation_paiement_restaure_le_reste(self):
        facture, _ecriture = self._facture(montant='200', numero='F-A')
        paiement, _piece = enregistrer_paiement(
            facture, self.jour, Decimal('50'), annee_scolaire=self.annee, user=self.etab
        )
        annuler_paiement(paiement, 'erreur de saisie', user=self.etab)
        paiement.refresh_from_db()
        facture.refresh_from_db()
        self.assertEqual(paiement.statut, 'annulee')
        self.assertTrue(PaiementCharge.objects.filter(pk=paiement.id).exists())
        self.assertEqual(facture.statut, 'a_payer')
        self.assertEqual(facture.reste_a_payer(), Decimal('200'))
        self.assertEqual(
            EcritureComptable.objects.filter(
                etablissement=self.etab, source='extourne'
            ).count(),
            1,
        )
        annuler_facture(facture, 'facture saisie par erreur', user=self.etab)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'annulee')
        self.assertEqual(facture.reste_a_payer(), Decimal('0'))
        self.assertTrue(FactureFournisseur.objects.filter(pk=facture.id).exists())

    def test_factures_isolees_par_etablissement(self):
        import uuid

        self._facture(numero='F-ISO')
        autre = _make_etablissement(uuid.uuid4().hex[:8])
        self.assertEqual(FactureFournisseur.objects.filter(etablissement=autre).count(), 0)
        self.assertEqual(PaiementCharge.objects.filter(etablissement=autre).count(), 0)
