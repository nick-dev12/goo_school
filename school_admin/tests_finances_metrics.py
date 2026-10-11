"""Moteur des sept indicateurs. kpi_cg n'est pas branché. Pas de double comptage créance + encaissement."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, FraisInscription, PaiementEleve
from school_admin.model.comptabilite_generale_model import FournisseurEtablissement
from school_admin.model.finances_model import CategorieFinanciere, RecetteEtablissement
from school_admin.services.comptabilite_generale import (
    REGIME_TRESORERIE,
    enregistrer_regime_comptable,
    ensure_exercice,
    kpi_cg,
    pont_paiement_eleve,
)
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.charges import enregistrer_facture, enregistrer_paiement
from school_admin.services.finances.metrics import DEFINITIONS, calculer_indicateurs
from school_admin.services.finances.operations import annuler_sortie, enregistrer_sortie
from school_admin.services.finances.prets import enregistrer_pret, enregistrer_remboursement
from school_admin.services.finances.recettes import enregistrer_recette, enregistrer_remboursement as rembourser_recette
from school_admin.services.finances.transferts import enregistrer_transfert
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class MetricsFinancesTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('met')
        self.annee = _make_annee(self.etab)
        assurer_categories(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')
        self.banque = compte_principal(self.etab, 'banque')
        self.exercice = ensure_exercice(self.etab, self.annee)

    def _vals(self):
        data = calculer_indicateurs(self.etab, self.jour, self.jour, self.annee)
        return {cle: item['valeur'] for cle, item in data['indicateurs'].items()}, data

    def _categorie(self, libelle):
        return CategorieFinanciere.objects.get(
            etablissement=self.etab, type_categorie='recette', libelle=libelle,
        )

    def test_definitions_des_sept_indicateurs(self):
        self.assertEqual(
            set(DEFINITIONS),
            {'disponible', 'encaisse', 'paye', 'resultat', 'creances', 'dettes', 'engagements'},
        )
        for meta in DEFINITIONS.values():
            self.assertTrue(meta['definition'])
            self.assertTrue(meta['source'])
            self.assertTrue(meta['formule'])
            self.assertTrue(meta['periode'])
            self.assertTrue(meta['inclus'])
            self.assertTrue(meta['exclus'])
        vals, data = self._vals()
        self.assertEqual(data['regime'], 'engagement')
        self.assertEqual(data['exercice_id'], self.exercice.pk)
        for cle, valeur in vals.items():
            self.assertEqual(valeur, Decimal('0.00'))
            self.assertEqual(data['indicateurs'][cle]['etablissement_id'], self.etab.pk)

    def test_transfert_et_pret_hors_encaisse_paye_resultat(self):
        enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('500'),
            motif='Versement', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['disponible'], Decimal('0.00'))
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(vals['resultat'], Decimal('0.00'))
        enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('5000'),
            reference='EMP-M', objet='Travaux', annee_scolaire=self.annee, user=self.etab,
        )
        vals, data = self._vals()
        self.assertEqual(vals['disponible'], Decimal('5000'))
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(vals['resultat'], Decimal('0.00'))
        self.assertEqual(vals['dettes'], Decimal('5000'))
        self.assertEqual(vals['engagements'], Decimal('0.00'))
        self.assertEqual(data['indicateurs']['dettes']['detail']['capital_restant'], Decimal('5000'))

    def test_remboursement_capital_hors_paye_interets_dans_paye_et_resultat(self):
        pret, _ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('1000'),
            reference='EMP-R', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_remboursement(
            pret, self.jour, capital=Decimal('200'), interets=Decimal('30'), frais=Decimal('5'),
            motif='Échéance', user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('35'))
        self.assertEqual(vals['resultat'], Decimal('-35'))
        self.assertEqual(vals['dettes'], Decimal('800'))
        self.assertEqual(vals['disponible'], Decimal('765'))
        self.assertEqual(vals['encaisse'], Decimal('0.00'))

    def test_facture_engagement_resultat_sans_paiement_puis_paye(self):
        fournisseur = FournisseurEtablissement.objects.create(etablissement=self.etab, nom='Senelec')
        categorie = CategorieFinanciere.objects.get(etablissement=self.etab, libelle='Électricité / eau')
        facture, _ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-M1', 'Courant', Decimal('450'),
            self.jour, self.jour, categorie, annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['resultat'], Decimal('-450'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(vals['engagements'], Decimal('450'))
        self.assertEqual(vals['dettes'], Decimal('450'))
        enregistrer_paiement(facture, self.jour, Decimal('300'), annee_scolaire=self.annee, user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['resultat'], Decimal('-450'))
        self.assertEqual(vals['paye'], Decimal('300'))
        self.assertEqual(vals['engagements'], Decimal('150'))
        self.assertEqual(vals['encaisse'], Decimal('0.00'))

    def test_tresorerie_facture_entre_dans_resultat_au_paiement(self):
        enregistrer_regime_comptable(self.etab, REGIME_TRESORERIE, annee_scolaire=self.annee)
        fournisseur = FournisseurEtablissement.objects.create(etablissement=self.etab, nom='Senelec T')
        categorie = CategorieFinanciere.objects.get(etablissement=self.etab, libelle='Électricité / eau')
        facture, ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-T1', 'Courant', Decimal('450'),
            self.jour, self.jour, categorie, annee_scolaire=self.annee, user=self.etab,
        )
        self.assertIsNone(ecriture)
        vals, data = self._vals()
        self.assertEqual(data['regime'], 'tresorerie')
        self.assertEqual(vals['resultat'], Decimal('0.00'))
        self.assertEqual(vals['engagements'], Decimal('450'))
        enregistrer_paiement(facture, self.jour, Decimal('450'), annee_scolaire=self.annee, user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('450'))
        self.assertEqual(vals['resultat'], Decimal('-450'))
        self.assertEqual(vals['engagements'], Decimal('0.00'))

    def test_creances_et_encaisse_ne_s_additionnent_pas(self):
        from school_admin.model.classe_model import Classe
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.etablissement_model import Etablissement

        classe = Classe.objects.create(
            nom='CE1 M', niveau='primaire', code_classe=f'ME{self.etab.pk}'[:20],
            capacite_max=30, etablissement=self.etab,
        )
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False), patch.object(
            Etablissement, 'recalculer_facturation', return_value=None
        ):
            eleve = Eleve(
                username=f'ME{self.etab.pk:06d}'[:20],
                numero_eleve=f'ME{self.etab.pk:06d}'[:20],
                nom='Ndiaye', prenom='Awa', date_naissance=date(2016, 1, 1),
                lieu_naissance='Dakar', sexe='F', nationalite='Sénégalaise',
                etablissement=self.etab, classe=classe, date_inscription=self.jour,
                statut='nouvelle', parent_nom='Ndiaye', parent_prenom='Ibrahima',
                parent_telephone='770000009', parent_lien='pere',
                mot_de_passe_provisoire='123456', actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
        cpta = ComptabiliteEleve.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
        )
        frais = FraisInscription.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
            comptabilite_eleve=cpta, montant=Decimal('1000'), montant_paye=Decimal('0'),
            date_echeance=self.jour, type_frais='inscription',
        )
        vals, _data = self._vals()
        self.assertEqual(vals['creances'], Decimal('1000'))
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['resultat'], Decimal('1000'))
        paiement = PaiementEleve.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
            type_paiement='frais_inscription', frais_inscription=frais,
            montant=Decimal('400'), mode_paiement='especes',
        )
        pont_paiement_eleve(paiement, annee_scolaire=self.annee, user=self.etab)
        FraisInscription.objects.filter(pk=frais.pk).update(montant_paye=Decimal('400'))
        vals, data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('400'))
        self.assertEqual(vals['creances'], Decimal('600'))
        self.assertEqual(vals['resultat'], Decimal('1000'))
        self.assertNotEqual(vals['encaisse'] + Decimal('1000'), vals['resultat'])
        self.assertEqual(data['indicateurs']['encaisse']['detail']['scolarite'], Decimal('400'))
        self.assertIsNone(data['indicateurs']['encaisse'].get('creances'))
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)

    def test_recette_kpi_cg_non_branche_annulation_et_autre_ecole(self):
        enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Sortie', annee_scolaire=self.annee, user=self.etab,
        )
        depense, _ecriture = enregistrer_sortie(
            self.etab, self.jour, 'fournitures', Decimal('75'),
            libelle='Cahiers', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('600'))
        self.assertEqual(vals['paye'], Decimal('75'))
        self.assertEqual(vals['resultat'], Decimal('525'))
        kpis = kpi_cg(self.etab, self.annee)
        self.assertEqual(kpis['entrees_mois'], Decimal('0.00'))
        self.assertEqual(kpis['sorties_mois'], Decimal('75.00'))
        self.assertIn('taux_recouvrement', kpis)
        recette, _ecr = enregistrer_recette(
            self.etab, 'divers', self._categorie('Recette diverse'), self.caisse,
            self.jour, Decimal('80'), libelle='Divers', annee_scolaire=self.annee, user=self.etab,
        )
        rembourser_recette(recette, self.jour, Decimal('30'), 'Trop perçu', user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('650'))
        annuler_sortie(depense, 'Erreur', user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('0.00'))
        autre = _make_etablissement('me2')
        assurer_categories(autre)
        assurer_comptes_defaut(autre)
        enregistrer_sortie(
            autre, self.jour, 'loyer', Decimal('999'),
            annee_scolaire=_make_annee(autre), user=autre,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(
            calculer_indicateurs(autre, self.jour, self.jour)['indicateurs']['paye']['valeur'],
            Decimal('999'),
        )
