"""Transferts de trésorerie : tous les sens, sans rejouer l'historique."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import (
    EcritureComptable,
    LigneEcriture,
    MouvementTresorerie,
    PeriodeComptable,
)
from school_admin.services.comptabilite_generale import (
    ensure_exercice,
    ensure_plan_comptable,
    pont_virement_interne,
)
from school_admin.services.finances.transferts import (
    annuler_transfert,
    enregistrer_transfert,
    rattacher_virements_historiques,
)
from school_admin.services.finances.tresorerie import (
    assurer_comptes_defaut,
    compte_principal,
    ouvrir_compte,
    solde_calcule,
)
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class TransfertsTresorerieTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('trf')
        self.annee = _make_annee(self.etab)
        ensure_plan_comptable(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')
        self.banque = compte_principal(self.etab, 'banque')
        self.mobile = compte_principal(self.etab, 'mobile_money')

    def _lignes(self, ecriture):
        return {
            ligne.compte.numero: (ligne.debit, ligne.credit)
            for ligne in ecriture.lignes.select_related('compte')
        }

    def test_caisse_vers_banque_sans_charge_ni_produit(self):
        mouvement, ecriture = enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('1500'),
            reference='DEP-1', motif='Dépôt', annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['521'], (Decimal('1500'), Decimal('0')))
        self.assertEqual(lignes['571'], (Decimal('0'), Decimal('1500')))
        self.assertFalse(
            LigneEcriture.objects.filter(ecriture=ecriture, compte__classe__in=['6', '7']).exists()
        )
        self.assertEqual(mouvement.statut, 'validee')
        self.assertEqual(solde_calcule(self.banque), Decimal('1500'))
        self.assertEqual(solde_calcule(self.caisse), Decimal('-1500'))

    def test_banque_vers_caisse_et_vers_mobile(self):
        enregistrer_transfert(
            self.etab, self.banque, self.caisse, self.jour, Decimal('400'),
            annee_scolaire=self.annee, user=self.etab,
        )
        self.assertEqual(solde_calcule(self.caisse), Decimal('400'))
        enregistrer_transfert(
            self.etab, self.caisse, self.mobile, self.jour, Decimal('100'),
            annee_scolaire=self.annee, user=self.etab,
        )
        self.assertEqual(solde_calcule(self.mobile), Decimal('100'))
        self.assertEqual(solde_calcule(self.caisse), Decimal('300'))

    def test_banque_vers_autre_banque(self):
        autre = ouvrir_compte(self.etab, 'banque', 'Banque secondaire')
        _mouvement, ecriture = enregistrer_transfert(
            self.etab, self.banque, autre, self.jour, Decimal('250'),
            annee_scolaire=self.annee, user=self.etab,
        )
        lignes = self._lignes(ecriture)
        self.assertEqual(lignes['5211'], (Decimal('250'), Decimal('0')))
        self.assertEqual(lignes['521'], (Decimal('0'), Decimal('250')))

    def test_meme_compte_refuse(self):
        with self.assertRaises(ValueError):
            enregistrer_transfert(
                self.etab, self.caisse, self.caisse, self.jour, Decimal('10'),
                annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(MouvementTresorerie.objects.filter(etablissement=self.etab).count(), 0)

    def test_virement_historique_est_nomme_sans_nouvelle_ecriture(self):
        ancien = MouvementTresorerie.objects.create(
            etablissement=self.etab,
            type_mouvement='virement_interne',
            date_mouvement=self.jour,
            montant=Decimal('80'),
            libelle='Ancien dépôt',
        )
        pont_virement_interne(ancien, annee_scolaire=self.annee, user=self.etab)
        avant = EcritureComptable.objects.filter(etablissement=self.etab).count()
        rattacher_virements_historiques(self.etab)
        ancien.refresh_from_db()
        self.assertEqual(ancien.compte_source_id, self.caisse.id)
        self.assertEqual(ancien.compte_destination_id, self.banque.id)
        self.assertEqual(EcritureComptable.objects.filter(etablissement=self.etab).count(), avant)
        self.assertEqual(
            EcritureComptable.objects.filter(etablissement=self.etab, source='transfert').count(),
            0,
        )

    def test_periode_verrouillee_bloque_le_transfert(self):
        exercice = ensure_exercice(self.etab, self.annee)
        PeriodeComptable.objects.filter(exercice=exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            enregistrer_transfert(
                self.etab, self.caisse, self.banque, self.jour, Decimal('20'),
                annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(MouvementTresorerie.objects.filter(etablissement=self.etab).count(), 0)

    def test_transferts_isoles_par_etablissement(self):
        import uuid

        enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('15'),
            annee_scolaire=self.annee, user=self.etab,
        )
        autre = _make_etablissement(uuid.uuid4().hex[:8])
        self.assertEqual(MouvementTresorerie.objects.filter(etablissement=autre).count(), 0)

    def test_annulation_garde_la_ligne_et_compense(self):
        mouvement, _ecriture = enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('60'),
            annee_scolaire=self.annee, user=self.etab,
        )
        annuler_transfert(mouvement, 'erreur de dépôt', user=self.etab)
        mouvement.refresh_from_db()
        self.assertEqual(mouvement.statut, 'annulee')
        self.assertTrue(MouvementTresorerie.objects.filter(pk=mouvement.id).exists())
        self.assertEqual(solde_calcule(self.caisse), Decimal('0'))
        self.assertEqual(solde_calcule(self.banque), Decimal('0'))
