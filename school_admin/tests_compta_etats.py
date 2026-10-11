"""États comptables : saisie, balance, grand livre, bilan, compte de résultat, clôture, immobilisations."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from school_admin.model.comptabilite_generale_model import EcritureComptable, Immobilisation
from school_admin.services import compta_etats as ce
from school_admin.services import comptabilite_generale as cg
from school_admin.tests_comptabilite_generale import _make_etablissement


class ComptaEtatsTests(TestCase):
    def setUp(self):
        self.etab = _make_etablissement('etats')
        cg.ensure_journaux(self.etab)
        self.exo = cg.exercice_pour_date(self.etab, date(2026, 3, 1))
        self.od = cg.journal(self.etab, 'OD')

    def cpt(self, numero):
        return cg.compte(self.etab, numero)

    def saisir(self, jour, libelle, lignes):
        brutes = [{'compte_id': self.cpt(n).pk, 'debit': d, 'credit': c} for n, d, c in lignes]
        return ce.saisir_ecriture(self.etab, self.od, jour, libelle, brutes)

    def peupler(self):
        # Apport 1 000 000 en banque, scolarité encaissée 600 000, charges 250 000, achat bus 1 200 000.
        self.saisir(date(2026, 1, 5), 'Apport', [('521', '1000000', ''), ('101', '', '1000000')])
        self.saisir(date(2026, 2, 10), 'Scolarité', [('571', '600000', ''), ('7052', '', '600000')])
        self.saisir(date(2026, 3, 15), 'Électricité', [('605', '150000', ''), ('571', '', '150000')])
        self.saisir(date(2026, 3, 20), 'Fournitures', [('604', '100000', ''), ('401', '', '100000')])
        immo = Immobilisation.objects.create(etablissement=self.etab, libelle='Bus', categorie='bus',
                                             date_acquisition=date(2026, 7, 1), valeur_origine=Decimal('1200000'),
                                             duree_annees=5)
        cg.pont_acquisition_immobilisation(immo, fournisseur=None)
        return immo

    def test_saisie_refuse_desequilibre_et_double_sens(self):
        with self.assertRaises(ValueError):
            self.saisir(date(2026, 1, 5), 'KO', [('521', '100', ''), ('101', '', '90')])
        with self.assertRaises(ValueError):
            ce.saisir_ecriture(self.etab, self.od, date(2026, 1, 5), 'KO', [
                {'compte_id': self.cpt('521').pk, 'debit': '10', 'credit': '10'},
                {'compte_id': self.cpt('101').pk, 'credit': '0'},
            ])

    def test_ecriture_antidatee_va_dans_son_exercice(self):
        e = self.saisir(date(2025, 12, 31), 'Antidatée', [('521', '100', ''), ('101', '', '100')])
        self.assertEqual(e.exercice.libelle, '2025')

    def test_balance_bilan_resultat_coherents(self):
        immo = self.peupler()
        bal = ce.balance_generale(self.etab, self.exo)
        self.assertTrue(bal['equilibree'])
        cr = ce.compte_de_resultat(self.etab, self.exo)
        self.assertEqual(cr['total_produits'], Decimal('600000'))
        self.assertEqual(cr['total_charges'], Decimal('250000'))
        self.assertEqual(cr['resultat'], Decimal('350000'))
        b = ce.bilan(self.etab, self.exo)
        self.assertTrue(b['equilibre'])
        self.assertEqual(b['total_actif'], b['total_passif'])
        self.assertEqual(b['resultat'], Decimal('350000'))
        # Dotation au prorata : 6 mois sur 12 la première année.
        e = cg.pont_amortissement(immo, exercice=self.exo)
        self.assertEqual(e.total_debit(), Decimal('120000.00'))
        self.assertEqual(e.date_ecriture, self.exo.date_fin)
        with self.assertRaises(ValueError):
            cg.pont_amortissement(immo, exercice=self.exo)
        self.assertTrue(ce.bilan(self.etab, self.exo)['equilibre'])

    def test_grand_livre_solde_progressif(self):
        self.peupler()
        bloc = ce.grand_livre(self.etab, self.exo, compte=self.cpt('571'))[0]
        self.assertEqual([r['solde'] for r in bloc['rows']], [Decimal('600000'), Decimal('450000')])
        bloc_mars = ce.grand_livre(self.etab, self.exo, compte=self.cpt('571'), du=date(2026, 3, 1))[0]
        self.assertEqual(bloc_mars['report'], Decimal('600000'))

    def test_cloture_reporte_les_soldes_et_le_resultat(self):
        self.peupler()
        with self.assertRaises(ValueError):
            ce.cloturer_exercice(cg.exercice_pour_date(self.etab, date(2099, 6, 1)))
        res = ce.cloturer_exercice(self.exo, avant_terme=True)
        self.exo.refresh_from_db()
        self.assertEqual(self.exo.statut, 'cloture')
        an = res['ecriture']
        self.assertEqual(an.journal.code, 'AN')
        self.assertEqual(an.exercice.libelle, '2027')
        self.assertTrue(an.est_equilibree())
        suivant = res['suivant']
        b = ce.bilan(self.etab, suivant)
        self.assertTrue(b['equilibre'])
        cap = ce.soldes_comptes(self.etab, suivant)
        self.assertEqual(cap[self.cpt('1301').pk]['solde'], Decimal('-350000'))
        with self.assertRaises(ValueError):
            self.saisir(date(2026, 6, 1), 'Après clôture', [('521', '1', ''), ('101', '', '1')])
        ce.rouvrir_exercice(self.exo)
        self.assertFalse(EcritureComptable.objects.filter(source='a_nouveaux').exists())

    def test_controles_et_series(self):
        self.peupler()
        ctrl = ce.controles(self.etab, self.exo)
        self.assertEqual(ctrl['nb_alertes'], 0)
        series = ce.series_mensuelles(self.etab, self.exo)
        self.assertEqual(len(series['labels']), 12)
        self.assertEqual(series['produits'][1], 600000.0)
        self.assertEqual(series['tresorerie'][2], 1450000.0)


class ComptaPagesTests(TestCase):
    """Chaque section s'ouvre pour le directeur ; la saisie et la contrepassation passent par l'interface."""

    def setUp(self):
        from school_admin.services.finances.categories import assurer_categories
        from school_admin.services.finances.tresorerie import assurer_comptes_defaut
        from school_admin.tests_comptabilite_generale import _make_annee

        self.etab = _make_etablissement('pages')
        _make_annee(self.etab)
        assurer_categories(self.etab)
        assurer_comptes_defaut(self.etab)
        cg.ensure_journaux(self.etab)
        self.assertTrue(self.client.login(username=self.etab.username, password='Pce@Test1!'))

    def test_toutes_les_sections_et_exports(self):
        from django.urls import reverse

        for name in ('cg_hub_directeur', 'cg_etats', 'cg_journaux', 'cg_grand_livre', 'cg_balance', 'cg_clients',
                     'cg_fournisseurs', 'cg_tresorerie', 'cg_rapprochement', 'cg_recettes', 'cg_prets', 'cg_paie',
                     'cg_immobilisations', 'cg_plan_comptable', 'cg_exercices'):
            response = self.client.get(reverse(f'directeur:{name}'))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, 'cg3-nav', msg_prefix=name)
        for name in ('cg_journaux', 'cg_grand_livre', 'cg_balance', 'cg_etats'):
            response = self.client.get(reverse(f'directeur:{name}') + '?export=csv')
            self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8', name)
        for vue in ('bilan', 'indicateurs'):
            self.assertEqual(self.client.get(reverse('directeur:cg_etats') + f'?vue={vue}').status_code, 200)

    def test_saisie_et_contrepassation_par_formulaire(self):
        from django.urls import reverse

        url = reverse('directeur:cg_journaux')
        od = cg.journal(self.etab, 'OD')
        today = date.today().isoformat()
        self.client.post(url, {
            'action': 'saisir', 'journal_id': od.pk, 'date_ecriture': today, 'libelle': 'Apport',
            'compte_id': [cg.compte(self.etab, '521').pk, cg.compte(self.etab, '101').pk],
            'ligne_libelle': ['', ''], 'auxiliaire': ['', ''], 'debit': ['50000', ''], 'credit': ['', '50 000'],
        })
        e = EcritureComptable.objects.get(etablissement=self.etab, source='saisie')
        self.assertTrue(e.est_equilibree())
        self.client.post(url, {'action': 'extourner', 'ecriture_id': e.pk, 'date_extourne': today, 'motif': 'Erreur'})
        ext = EcritureComptable.objects.get(etablissement=self.etab, source='extourne')
        self.assertEqual(ext.ecriture_origine_id, e.pk)
        self.assertEqual(ext.total_debit(), Decimal('50000'))
