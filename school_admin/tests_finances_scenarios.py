"""Étape 10 : les 17 scénarios financiers, isolation, ORM, orphelines. Pas de nouvelle fonctionnalité."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from school_admin.model.caisse_etablissement_model import DepenseEtablissement
from school_admin.model.comptabilite_generale_model import (
    EcritureComptable,
    FournisseurEtablissement,
    PeriodeComptable,
)
from school_admin.model.finances_model import CategorieFinanciere, RecetteEtablissement
from school_admin.services.comptabilite_generale import (
    COMPTE_CAISSE,
    REGIME_TRESORERIE,
    compte,
    creer_ecriture,
    ecritures_depenses_orphelines,
    enregistrer_regime_comptable,
    ensure_exercice,
    journal,
    kpi_cg,
)
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.charges import enregistrer_facture, enregistrer_paiement
from school_admin.services.finances.metrics import calculer_indicateurs
from school_admin.services.finances.operations import annuler_sortie, enregistrer_sortie
from school_admin.services.finances.prets import enregistrer_pret, enregistrer_remboursement
from school_admin.services.finances.rapprochement import ajouter_ligne, creer_releve, pointer_ligne
from school_admin.services.finances.recettes import (
    enregistrer_recette,
    enregistrer_remboursement as rembourser_recette,
)
from school_admin.services.finances.transferts import enregistrer_transfert
from school_admin.services.finances.tresorerie import (
    assurer_comptes_defaut,
    compte_principal,
    ouvrir_compte,
    solde_calcule,
)
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class FinancesScenariosTests(TestCase):
    PASSWORD = 'Pce@Test1!'

    def setUp(self):
        self.etab = _make_etablissement('sc')
        self.annee = _make_annee(self.etab)
        assurer_categories(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')
        self.banque = compte_principal(self.etab, 'banque')
        self.mobile = compte_principal(self.etab, 'mobile_money')
        self.exercice = ensure_exercice(self.etab, self.annee)
        self.assertTrue(self.client.login(username=self.etab.username, password=self.PASSWORD))

    def _vals(self, etab=None):
        cible = etab or self.etab
        annee = self.annee if cible is self.etab else None
        data = calculer_indicateurs(cible, self.jour, self.jour, annee)
        return {cle: item['valeur'] for cle, item in data['indicateurs'].items()}, data

    def _categorie(self, libelle, type_categorie='recette'):
        return CategorieFinanciere.objects.get(
            etablissement=self.etab, type_categorie=type_categorie, libelle=libelle,
        )

    def _personnel(self, fonction):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        person = PersonnelAdministratif(
            username=f'{fonction}{self.etab.pk}@aria-test.local',
            email=f'{fonction}{self.etab.pk}@aria-test.local',
            nom='Fall',
            prenom=fonction,
            telephone='770000444',
            fonction=fonction,
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        person.set_password('Test@Test1!')
        person.save()
        return person

    def _eleve(self):
        from school_admin.model.classe_model import Classe
        from school_admin.model.eleve_model import Eleve
        from school_admin.model.etablissement_model import Etablissement

        classe = Classe.objects.create(
            nom='CE1 S', niveau='primaire', code_classe=f'SC{self.etab.pk}'[:20],
            capacite_max=30, etablissement=self.etab,
        )
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False), patch.object(
            Etablissement, 'recalculer_facturation', return_value=None
        ):
            eleve = Eleve(
                username=f'SC{self.etab.pk:06d}'[:20],
                numero_eleve=f'SC{self.etab.pk:06d}'[:20],
                nom='Sow', prenom='Awa', date_naissance=date(2016, 2, 2),
                lieu_naissance='Dakar', sexe='F', nationalite='Sénégalaise',
                etablissement=self.etab, classe=classe, date_inscription=self.jour,
                statut='nouvelle', parent_nom='Sow', parent_prenom='Ibrahima',
                parent_telephone='770000010', parent_lien='pere',
                mot_de_passe_provisoire='123456', actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
        return eleve

    def _fournisseur(self, nom='Senelec'):
        return FournisseurEtablissement.objects.create(etablissement=self.etab, nom=nom)

    def _req(self, user, path='/finances/', method='get', data=None):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post(path, data or {}) if method == 'post' else factory.get(path)
        request.user = user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_01_paiement_scolaire(self):
        from school_admin.model.comptabilite_eleve_model import PaiementEleve

        eleve = self._eleve()
        PaiementEleve.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
            type_paiement='autre', montant=Decimal('1500'), mode_paiement='especes',
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('1500'))
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        response = self.client.get(reverse('directeur:finances_entrees'), {'vue': 'scolarite'})
        self.assertContains(response, 'SOW')
        self.assertContains(response, '1500')

    def test_02_depense(self):
        enregistrer_sortie(
            self.etab, self.jour, 'fournitures', Decimal('75'),
            libelle='Cahiers', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('75'))
        response = self.client.get(reverse('directeur:finances_sorties'), {'vue': 'jour'})
        self.assertContains(response, 'Cahiers')
        self.assertContains(response, 'cg-pill--info')

    def test_03_facture_partiellement_payee(self):
        fournisseur = self._fournisseur()
        facture, _ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-P', 'Courant', Decimal('450'),
            self.jour, self.jour, self._categorie('Électricité / eau', 'sortie'),
            annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_paiement(facture, self.jour, Decimal('430'), annee_scolaire=self.annee, user=self.etab)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'partiel')
        self.assertEqual(facture.reste_a_payer(), Decimal('20'))
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('430'))
        self.assertEqual(vals['engagements'], Decimal('20'))

    def test_04_facture_entierement_payee(self):
        fournisseur = self._fournisseur()
        facture, _ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-T', 'Courant', Decimal('450'),
            self.jour, self.jour, self._categorie('Électricité / eau', 'sortie'),
            annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_paiement(facture, self.jour, Decimal('450'), annee_scolaire=self.annee, user=self.etab)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'payee')
        self.assertEqual(facture.reste_a_payer(), Decimal('0'))
        vals, _data = self._vals()
        self.assertEqual(vals['engagements'], Decimal('0'))
        self.assertEqual(vals['paye'], Decimal('450'))

    def test_05_transfert(self):
        avant, _data = self._vals()
        enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('1500'),
            motif='Versement scolarité', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], avant['encaisse'])
        self.assertEqual(vals['paye'], avant['paye'])
        self.assertEqual(vals['resultat'], avant['resultat'])
        self.assertEqual(solde_calcule(self.banque), Decimal('1500'))
        self.assertEqual(solde_calcule(self.caisse), Decimal('-1500'))
        self.assertEqual(vals['disponible'], avant['disponible'])

    def test_06_pret(self):
        enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('20000'),
            reference='EMP-S', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(vals['disponible'], Decimal('20000'))
        self.assertEqual(vals['dettes'], Decimal('20000'))
        self.assertEqual(vals['resultat'], Decimal('0.00'))

    def test_07_remboursement_pret(self):
        pret, _ecriture = enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('20000'),
            reference='EMP-R', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_remboursement(
            pret, self.jour, capital=Decimal('500'), interets=Decimal('100'), frais=Decimal('10'),
            motif='Échéance 1', user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('110'))
        self.assertEqual(vals['dettes'], Decimal('19500'))
        self.assertEqual(vals['resultat'], Decimal('-110'))
        self.assertEqual(_data['indicateurs']['paye']['detail']['sorties'], Decimal('0.00'))

    def test_08_remboursement_operation(self):
        recette, _ecriture = enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Sortie pédagogique',
            annee_scolaire=self.annee, user=self.etab,
        )
        rembourser_recette(recette, self.jour, Decimal('50'), 'Trop perçu', user=self.etab)
        recette.refresh_from_db()
        self.assertEqual(recette.montant, Decimal('600'))
        self.assertEqual(recette.net(), Decimal('550'))
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('550'))
        self.assertTrue(RecetteEtablissement.objects.filter(pk=recette.pk, statut='validee').exists())

    def test_09_annulation(self):
        recette, _ecriture = enregistrer_recette(
            self.etab, 'divers', self._categorie('Recette diverse'), self.caisse,
            self.jour, Decimal('80'), libelle='Divers',
            annee_scolaire=self.annee, user=self.etab,
        )
        depense, _ecr = enregistrer_sortie(
            self.etab, self.jour, 'fournitures', Decimal('75'),
            annee_scolaire=self.annee, user=self.etab,
        )
        from school_admin.services.finances.recettes import annuler_recette

        annuler_recette(recette, 'erreur', user=self.etab)
        annuler_sortie(depense, 'erreur', user=self.etab)
        recette.refresh_from_db()
        depense.refresh_from_db()
        self.assertEqual(recette.statut, 'annulee')
        self.assertEqual(depense.statut, 'annulee')
        self.assertTrue(RecetteEtablissement.objects.filter(pk=recette.pk).exists())
        self.assertTrue(DepenseEtablissement.objects.filter(pk=depense.pk).exists())
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))

    def test_10_periode_verrouillee(self):
        PeriodeComptable.objects.filter(exercice=self.exercice, type_periode='mois').update(verrouillee=True)
        with self.assertRaises(ValueError):
            enregistrer_sortie(
                self.etab, self.jour, 'loyer', Decimal('10'),
                annee_scolaire=self.annee, user=self.etab,
            )
        with self.assertRaises(ValueError):
            enregistrer_recette(
                self.etab, 'activite', self._categorie('Activité'), self.caisse,
                self.jour, Decimal('10'), annee_scolaire=self.annee, user=self.etab,
            )
        self.assertEqual(DepenseEtablissement.objects.filter(etablissement=self.etab).count(), 0)
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)

    def test_11_permissions(self):
        from school_admin.controllers.finances_controller import FinancesController

        recette, _ecriture = enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('40'), libelle='Atelier',
            annee_scolaire=self.annee, user=self.etab,
        )
        self.client.logout()
        response = self.client.get(reverse('directeur:finances_situation'))
        self.assertEqual(response.status_code, 302)

        secretaire = self._personnel('secretaire')
        denied = FinancesController.situation(self._req(secretaire))
        self.assertEqual(denied.status_code, 302)

        caissier = self._personnel('caissier')
        ok = FinancesController.situation(self._req(caissier))
        self.assertEqual(ok.status_code, 200)
        FinancesController.entrees(self._req(caissier, '/finances/entrees/', 'post', {
            'action': 'annuler_recette',
            'recette_id': str(recette.pk),
            'motif': 'interdit',
            'vue': 'activite',
        }))
        recette.refresh_from_db()
        self.assertEqual(recette.statut, 'validee')

    def test_12_rapprochement(self):
        avant = EcritureComptable.objects.filter(etablissement=self.etab).count()
        _mouvement, ecriture = enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('900'),
            motif='Versement', annee_scolaire=self.annee, user=self.etab,
        )
        releve = creer_releve(
            self.etab, self.banque, 'REL-S', self.jour, self.jour,
            Decimal('0'), Decimal('900'), user=self.etab,
        )
        ligne = ajouter_ligne(releve, self.jour, 'Dépôt', credit=Decimal('900'), user=self.etab)
        pointer_ligne(ligne, ecriture, user=self.etab)
        ligne.refresh_from_db()
        self.assertTrue(ligne.pointe)
        self.assertEqual(
            EcritureComptable.objects.filter(etablissement=self.etab).count(),
            avant + 1,
        )

    def test_13_multi_banques(self):
        autre_banque = ouvrir_compte(self.etab, 'banque', 'Banque secondaire', reference='SN2')
        enregistrer_transfert(
            self.etab, self.banque, autre_banque, self.jour, Decimal('300'),
            motif='Répartition', annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_transfert(
            self.etab, self.caisse, self.mobile, self.jour, Decimal('50'),
            motif='Recharge', annee_scolaire=self.annee, user=self.etab,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(solde_calcule(autre_banque), Decimal('300'))
        self.assertEqual(solde_calcule(self.mobile), Decimal('50'))
        self.assertEqual(solde_calcule(self.banque), Decimal('-300'))

    def test_14_regime_engagement(self):
        fournisseur = self._fournisseur()
        facture, _ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-E', 'Courant', Decimal('450'),
            self.jour, self.jour, self._categorie('Électricité / eau', 'sortie'),
            annee_scolaire=self.annee, user=self.etab,
        )
        vals, data = self._vals()
        self.assertEqual(data['regime'], 'engagement')
        self.assertEqual(vals['paye'], Decimal('0.00'))
        self.assertEqual(vals['resultat'], Decimal('-450'))
        self.assertEqual(vals['engagements'], Decimal('450'))
        enregistrer_paiement(facture, self.jour, Decimal('430'), annee_scolaire=self.annee, user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('430'))
        self.assertEqual(vals['resultat'], Decimal('-450'))

    def test_15_regime_tresorerie(self):
        enregistrer_regime_comptable(self.etab, REGIME_TRESORERIE, annee_scolaire=self.annee)
        fournisseur = self._fournisseur()
        facture, ecriture = enregistrer_facture(
            self.etab, fournisseur, 'F-TRES', 'Courant', Decimal('450'),
            self.jour, self.jour, self._categorie('Électricité / eau', 'sortie'),
            annee_scolaire=self.annee, user=self.etab,
        )
        self.assertIsNone(ecriture)
        vals, data = self._vals()
        self.assertEqual(data['regime'], REGIME_TRESORERIE)
        self.assertEqual(vals['resultat'], Decimal('0.00'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        enregistrer_paiement(facture, self.jour, Decimal('430'), annee_scolaire=self.annee, user=self.etab)
        vals, _data = self._vals()
        self.assertEqual(vals['paye'], Decimal('430'))
        self.assertEqual(vals['resultat'], Decimal('-430'))

    def test_16_double_comptabilisation(self):
        from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, FraisInscription, PaiementEleve
        from school_admin.services.comptabilite_generale import pont_paiement_eleve

        fournisseur = self._fournisseur()
        enregistrer_facture(
            self.etab, fournisseur, 'F-D', 'Courant', Decimal('100'),
            self.jour, self.jour, self._categorie('Électricité / eau', 'sortie'),
            annee_scolaire=self.annee, user=self.etab,
        )
        with self.assertRaises(ValueError):
            enregistrer_sortie(
                self.etab, self.jour, 'electricite', Decimal('100'),
                annee_scolaire=self.annee, user=self.etab, fournisseur=fournisseur,
            )
        self.assertEqual(DepenseEtablissement.objects.filter(etablissement=self.etab).count(), 0)

        eleve = self._eleve()
        cpta = ComptabiliteEleve.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
        )
        frais = FraisInscription.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
            comptabilite_eleve=cpta, montant=Decimal('1000'), montant_paye=Decimal('0'),
            date_echeance=self.jour, type_frais='inscription',
        )
        paiement = PaiementEleve.objects.create(
            eleve=eleve, etablissement=self.etab, annee_scolaire=self.annee,
            type_paiement='frais_inscription', frais_inscription=frais,
            montant=Decimal('400'), mode_paiement='especes',
        )
        pont_paiement_eleve(paiement, annee_scolaire=self.annee, user=self.etab)
        FraisInscription.objects.filter(pk=frais.pk).update(montant_paye=Decimal('400'))
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 0)

        enregistrer_pret(
            self.etab, self.banque, self.jour, Decimal('2000'),
            reference='EMP-D', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_transfert(
            self.etab, self.caisse, self.banque, self.jour, Decimal('100'),
            motif='Versement', annee_scolaire=self.annee, user=self.etab,
        )
        vals, data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('400'))
        self.assertEqual(vals['creances'], Decimal('600'))
        self.assertEqual(vals['resultat'], Decimal('900'))
        self.assertNotEqual(vals['encaisse'] + vals['creances'], vals['resultat'])
        self.assertEqual(data['indicateurs']['encaisse']['detail']['scolarite'], Decimal('400'))
        self.assertIsNone(data['indicateurs']['encaisse'].get('creances'))
        kpis = kpi_cg(self.etab, self.annee)
        self.assertEqual(kpis['entrees_mois'], Decimal('400'))

    def test_17_isolation_etablissement(self):
        enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Atelier isolé',
            annee_scolaire=self.annee, user=self.etab,
        )
        autre = _make_etablissement('sc2')
        annee_autre = _make_annee(autre)
        assurer_categories(autre)
        assurer_comptes_defaut(autre)
        enregistrer_sortie(
            autre, self.jour, 'loyer', Decimal('999'),
            libelle='Loyer autre école', annee_scolaire=annee_autre, user=autre,
        )
        vals, _data = self._vals()
        self.assertEqual(vals['encaisse'], Decimal('600'))
        self.assertEqual(vals['paye'], Decimal('0.00'))
        autre_vals, _autre = self._vals(autre)
        self.assertEqual(autre_vals['paye'], Decimal('999'))
        self.assertEqual(autre_vals['encaisse'], Decimal('0.00'))

        self.client.logout()
        self.assertTrue(self.client.login(username=autre.username, password=self.PASSWORD))
        html = self.client.get(reverse('directeur:finances_entrees'), {'vue': 'activite'}).content.decode()
        self.assertNotIn('Atelier isolé', html)
        html_sorties = self.client.get(reverse('directeur:finances_sorties'), {'vue': 'jour'}).content.decode()
        self.assertIn('Loyer autre école', html_sorties)
        self.assertNotIn('Atelier isolé', html_sorties)

    def test_orm_disponible_pas_n_plus_un(self):
        for index in range(4):
            ouvrir_compte(self.etab, 'banque', f'Banque extra {index}')
        calculer_indicateurs(self.etab, self.jour, self.jour, self.annee)
        with CaptureQueriesContext(connection) as ctx:
            calculer_indicateurs(self.etab, self.jour, self.jour, self.annee)
        sqls = [query['sql'].lower() for query in ctx.captured_queries]
        lignes = [sql for sql in sqls if 'ligneecriture' in sql.replace('_', '')]
        self.assertLessEqual(len(lignes), 4, lignes)
        self.assertLessEqual(len(ctx.captured_queries), 90)

    def test_orphelines_filtrees_sans_extourne(self):
        creer_ecriture(
            self.etab,
            self.exercice,
            journal(self.etab, 'CAI'),
            self.jour,
            'Sortie disparue',
            [
                {'compte': compte(self.etab, '604'), 'debit': Decimal('1000'), 'credit': Decimal('0')},
                {'compte': compte(self.etab, COMPTE_CAISSE), 'debit': Decimal('0'), 'credit': Decimal('1000')},
            ],
            source='depense',
            source_id=999999,
        )
        self.assertEqual(ecritures_depenses_orphelines(self.etab).count(), 1)
        autre = _make_etablissement('sc3')
        self.assertEqual(ecritures_depenses_orphelines(autre).count(), 0)
        self.assertEqual(
            EcritureComptable.objects.filter(etablissement=self.etab, source='extourne').count(),
            0,
        )

    def test_cinq_onglets_tiennent_avec_operations(self):
        enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Atelier',
            annee_scolaire=self.annee, user=self.etab,
        )
        for nom in (
            'directeur:finances_situation',
            'directeur:finances_entrees',
            'directeur:finances_sorties',
            'directeur:finances_tresorerie',
            'directeur:finances_financements',
        ):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200)
        self.client.get(reverse('directeur:finances_situation'))
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse('directeur:finances_situation'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('kpi_cg', response.context)
        self.assertLessEqual(len(ctx.captured_queries), 320)
