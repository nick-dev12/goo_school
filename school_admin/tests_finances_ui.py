"""Interface Finances : cinq onglets, métriques, filtres GET, isolation."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from school_admin.model.finances_model import RecetteEtablissement
from school_admin.services.finances.categories import assurer_categories
from school_admin.services.finances.operations import enregistrer_sortie
from school_admin.services.finances.prets import enregistrer_pret, enregistrer_remboursement
from school_admin.services.finances.queries import dernieres_operations
from school_admin.services.finances.recettes import enregistrer_recette
from school_admin.services.finances.tresorerie import assurer_comptes_defaut, compte_principal
from school_admin.tests_comptabilite_generale import _make_annee, _make_etablissement


class FinancesInterfaceTests(TestCase):
    PASSWORD = 'Pce@Test1!'

    def setUp(self):
        self.etab = _make_etablissement('fui')
        self.annee = _make_annee(self.etab)
        assurer_categories(self.etab)
        assurer_comptes_defaut(self.etab)
        self.jour = timezone.now().date()
        self.caisse = compte_principal(self.etab, 'caisse')
        self.assertTrue(self.client.login(username=self.etab.username, password=self.PASSWORD))

    def _categorie(self, libelle):
        from school_admin.model.finances_model import CategorieFinanciere

        return CategorieFinanciere.objects.get(
            etablissement=self.etab, type_categorie='recette', libelle=libelle,
        )

    def _personnel(self, fonction):
        from school_admin.model.personnel_administratif_model import PersonnelAdministratif

        person = PersonnelAdministratif(
            username=f'{fonction}{self.etab.pk}@aria-test.local',
            email=f'{fonction}{self.etab.pk}@aria-test.local',
            nom='Ndiaye',
            prenom=fonction,
            telephone='770000333',
            fonction=fonction,
            etablissement=self.etab,
            actif=True,
            permissions={},
        )
        person.set_password('Test@Test1!')
        person.save()
        return person

    def test_cinq_onglets_et_metriques_sans_kpi_cg(self):
        enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('600'), libelle='Sortie pédagogique',
            annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_sortie(
            self.etab, self.jour, 'fournitures', Decimal('75'),
            libelle='Cahiers', annee_scolaire=self.annee, user=self.etab,
        )
        response = self.client.get(reverse('directeur:finances_situation'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for mot in ('Situation', 'Entrées', 'Sorties', 'Trésorerie', 'Financements'):
            self.assertIn(mot, html)
        self.assertIn('600', html)
        self.assertIn('75', html)
        self.assertIn('indicateurs', response.context)
        self.assertNotIn('kpi_cg', response.context)
        self.assertNotIn('kpis', response.context)
        self.assertEqual(response.context['indicateurs']['encaisse']['valeur'], Decimal('600'))
        self.assertEqual(response.context['indicateurs']['paye']['valeur'], Decimal('75'))
        self.assertIn('fin-kpi--sortie', html)
        self.assertNotIn('cg-pill--danger', html)

    def test_filtre_mois_reste_dans_ladresse(self):
        response = self.client.get(
            reverse('directeur:finances_entrees'),
            {'mois': '2026-09', 'vue': 'activite'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['bornes'].valeur, '2026-09')
        html = response.content.decode()
        self.assertIn('name="mois"', html)
        self.assertIn('2026-09', html)
        self.assertIn('vue=activite', html)

    def test_post_activite_et_isolation(self):
        categorie = self._categorie('Activité')
        response = self.client.post(
            reverse('directeur:finances_entrees'),
            {
                'action': 'ajouter_recette',
                'nature': 'activite',
                'categorie_id': str(categorie.pk),
                'compte_id': str(self.caisse.pk),
                'date_recette': self.jour.isoformat(),
                'montant': '600',
                'libelle': 'Sortie pédagogique',
                'vue': 'activite',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RecetteEtablissement.objects.filter(etablissement=self.etab).count(), 1)
        autre = _make_etablissement('fu2')
        _make_annee(autre)
        assurer_categories(autre)
        assurer_comptes_defaut(autre)
        self.client.logout()
        self.assertTrue(self.client.login(username=autre.username, password=self.PASSWORD))
        response = self.client.get(reverse('directeur:finances_entrees'), {'vue': 'activite'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Sortie pédagogique', response.content.decode())

    def test_post_sortie_validee_pas_rouge(self):
        response = self.client.post(
            reverse('directeur:finances_sorties'),
            {
                'action': 'ajouter_sortie',
                'date_depense': self.jour.isoformat(),
                'motif': 'fournitures',
                'montant': '75',
                'libelle': 'Cahiers',
                'vue': 'jour',
            },
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('directeur:finances_sorties'), {'vue': 'jour'})
        html = response.content.decode()
        self.assertIn('Cahiers', html)
        self.assertIn('cg-pill--info', html)
        self.assertIn('fin-montant-sortie', html)
        self.assertNotIn('#ef4444', html)

    def test_caissier_ouvre_finances_sans_annuler(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from school_admin.controllers.finances_controller import FinancesController

        recette, _ecriture = enregistrer_recette(
            self.etab, 'activite', self._categorie('Activité'), self.caisse,
            self.jour, Decimal('100'), libelle='Atelier',
            annee_scolaire=self.annee, user=self.etab,
        )
        caissier = self._personnel('caissier')

        def _req(method='get', data=None):
            factory = RequestFactory()
            request = factory.post('/finances/entrees/', data or {}) if method == 'post' else factory.get('/finances/')
            request.user = caissier
            SessionMiddleware(lambda req: None).process_request(request)
            request.session.save()
            request._messages = FallbackStorage(request)
            return request

        response = FinancesController.situation(_req())
        self.assertEqual(response.status_code, 200)
        FinancesController.entrees(_req('post', {
            'action': 'annuler_recette',
            'recette_id': str(recette.pk),
            'motif': 'erreur',
            'vue': 'activite',
        }))
        recette.refresh_from_db()
        self.assertEqual(recette.statut, 'validee')

    def test_menu_et_onglets_tresorerie_financements(self):
        self.assertEqual(self.client.get(reverse('directeur:finances_tresorerie')).status_code, 200)
        self.assertEqual(self.client.get(reverse('directeur:finances_financements')).status_code, 200)
        self.assertTrue(reverse('directeur:finances_situation').endswith('/finances/'))
        hub = self.client.get(reverse('directeur:gestion_etablissement'))
        self.assertContains(hub, 'Finances')
        self.assertContains(hub, reverse('directeur:finances_situation'))

    def test_dernieres_operations_lit_un_remboursement_de_pret(self):
        banque = compte_principal(self.etab, 'banque')
        pret, _ecriture = enregistrer_pret(
            self.etab, banque, self.jour, Decimal('1000'),
            reference='EMP-UI', objet='Bus', annee_scolaire=self.annee, user=self.etab,
        )
        enregistrer_remboursement(
            pret, self.jour, capital=Decimal('200'), interets=Decimal('30'), frais=Decimal('5'),
            motif='Échéance', user=self.etab,
        )
        ops = dernieres_operations(self.etab, self.jour, self.jour)
        self.assertTrue(any('EMP-UI' in item['libelle'] for item in ops))
        response = self.client.get(reverse('directeur:finances_situation'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EMP-UI')
