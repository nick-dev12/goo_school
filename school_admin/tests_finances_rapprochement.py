"""Rapprochement bancaire : relevé, écart, pointage. Aucune écriture créée."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_generale_model import EcritureComptable, MouvementTresorerie, PeriodeComptable
from school_admin.model.finances_model import JournalAuditFinancier, LigneReleve, ReleveBancaire
from school_admin.services.comptabilite_generale import ensure_exercice, ensure_plan_comptable
from school_admin.services.finances.rapprochement import (
    ajouter_ligne,
    cloturer_releve,
    creer_releve,
    depointer_ligne,
    mettre_a_jour_ligne,
    pointer_ligne,
    synthese_releve,
)
from school_admin.services.finances.transferts import annuler_transfert, enregistrer_transfert
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal, solde_calcule
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class RapprochementBancaireTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('rap')
        self.annee = _make_annee(self.etab)
        ensure_plan_comptable(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')
        self.banque = compte_principal(self.etab, 'banque')
        self.exercice = ensure_exercice(self.etab, self.annee)

    def _transfert(self, montant='1000'):
        return enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal(montant),
            reference='VIR-R', motif='Versement test', annee_scolaire=self.annee, user=self.etab,
        )

    def test_caisse_refusee_ecart_et_pointage_sans_ecriture(self):
        with self.assertRaises(ValueError):
            creer_releve(
                self.etab, self.caisse, 'REL-C', self.jour, self.jour, 0, 0, user=self.etab,
            )
        avant = EcritureComptable.objects.filter(etablissement=self.etab).count()
        mouvement, ecriture = self._transfert('1500')
        releve = creer_releve(
            self.etab, self.banque, 'REL-1', self.jour, self.jour,
            Decimal('0'), Decimal('1500'), user=self.etab,
        )
        ligne = ajouter_ligne(
            releve, self.jour, 'Versement caisse', credit=Decimal('1500'), user=self.etab,
        )
        self.assertEqual(EcritureComptable.objects.filter(etablissement=self.etab).count(), avant + 1)
        synthese = synthese_releve(releve)
        self.assertEqual(synthese['solde_aria'], Decimal('1500'))
        self.assertEqual(synthese['solde_releve'], Decimal('1500'))
        self.assertEqual(synthese['ecart'], Decimal('0'))
        self.assertTrue(synthese['coherence_interne'])
        self.assertEqual(synthese['nb_non_pointees'], 1)
        pointer_ligne(ligne, ecriture, user=self.etab)
        ligne.refresh_from_db()
        mouvement.refresh_from_db()
        self.assertTrue(ligne.pointe)
        self.assertTrue(mouvement.pointe)
        self.assertEqual(ligne.ecriture_id, ecriture.id)
        self.assertEqual(synthese_releve(releve)['nb_non_pointees'], 0)
        self.assertEqual(solde_calcule(self.banque), Decimal('1500'))
        self.assertEqual(EcritureComptable.objects.filter(etablissement=self.etab).count(), avant + 1)
        self.assertTrue(
            JournalAuditFinancier.objects.filter(
                etablissement=self.etab, action='rapprochement', cible_object_id=ligne.id,
            ).exists()
        )

    def test_ligne_pointee_immuable_et_depointage_avec_motif(self):
        mouvement, ecriture = self._transfert('800')
        releve = creer_releve(
            self.etab, self.banque, 'REL-2', self.jour, self.jour, 0, Decimal('800'), user=self.etab,
        )
        ligne = ajouter_ligne(releve, self.jour, 'Dépôt', credit=Decimal('800'), user=self.etab)
        pointer_ligne(ligne, ecriture, user=self.etab)
        with self.assertRaises(ValueError):
            mettre_a_jour_ligne(ligne, libelle='Autre', user=self.etab)
        with self.assertRaises(ValueError):
            pointer_ligne(ligne, ecriture, user=self.etab)
        with self.assertRaises(ValueError):
            depointer_ligne(ligne, '', user=self.etab)
        mouvement.refresh_from_db()
        self.assertTrue(mouvement.pointe)
        with self.assertRaises(ValueError):
            annuler_transfert(mouvement, 'Trop tôt', user=self.etab)
        depointer_ligne(ligne, 'Erreur de rapprochement', user=self.etab)
        ligne.refresh_from_db()
        mouvement.refresh_from_db()
        self.assertFalse(ligne.pointe)
        self.assertIsNone(ligne.ecriture_id)
        self.assertFalse(mouvement.pointe)
        mettre_a_jour_ligne(ligne, libelle='Dépôt corrigé', user=self.etab)
        ligne.refresh_from_db()
        self.assertEqual(ligne.libelle, 'Dépôt corrigé')

    def test_montant_different_periode_et_autre_ecole(self):
        _mouvement, ecriture = self._transfert('400')
        releve = creer_releve(
            self.etab, self.banque, 'REL-3', self.jour, self.jour, 0, Decimal('400'), user=self.etab,
        )
        ligne = ajouter_ligne(releve, self.jour, 'Dépôt', credit=Decimal('399'), user=self.etab)
        with self.assertRaises(ValueError):
            pointer_ligne(ligne, ecriture, user=self.etab)
        self.assertFalse(LigneReleve.objects.get(pk=ligne.pk).pointe)
        PeriodeComptable.objects.filter(exercice=self.exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            creer_releve(
                self.etab, self.banque, 'REL-BLOQUE', self.jour, self.jour, 0, 0, user=self.etab,
            )
        PeriodeComptable.objects.filter(exercice=self.exercice, type_periode='mois').update(verrouillee=False)
        autre = _make_etablissement('rp2')
        ensure_plan_comptable(autre)
        assurer_comptes_defaut(autre)
        banque_autre = compte_principal(autre, 'banque')
        with self.assertRaises(ValueError):
            creer_releve(
                self.etab, banque_autre, 'REL-X', self.jour, self.jour, 0, 0, user=self.etab,
            )
        self.assertEqual(ReleveBancaire.objects.filter(etablissement=autre).count(), 0)

    def test_pointe_historique_non_converti_et_cloture(self):
        mouvement, _ecriture = self._transfert('50')
        mouvement.pointe = True
        mouvement.save(update_fields=['pointe'])
        releve = creer_releve(
            self.etab, self.banque, 'REL-4', self.jour, self.jour, 0, Decimal('50'), user=self.etab,
        )
        self.assertEqual(LigneReleve.objects.filter(mouvement=mouvement).count(), 0)
        mouvement.refresh_from_db()
        self.assertTrue(mouvement.pointe)
        cloturer_releve(releve, user=self.etab)
        releve.refresh_from_db()
        self.assertEqual(releve.statut, 'cloture')
        with self.assertRaises(ValueError):
            ajouter_ligne(releve, self.jour, 'Trop tard', credit=Decimal('1'), user=self.etab)
        self.assertEqual(ReleveBancaire.objects.filter(etablissement=self.etab).count(), 1)
