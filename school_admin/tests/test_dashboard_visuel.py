"""Maquette visuelle dashboard — KPI, today, graphiques (données réelles)."""
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import patch

from django.test import Client, RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services.dashboard.context import build_dashboard_context
from school_admin.services.dashboard.executive import build_executive_dashboard
from school_admin.services.dashboard.insights import build_insight_bar
from school_admin.services.dashboard.metrics.engine import ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = uuid4().hex[:12]
    email = f'dbd.vis.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard Visuel {suffix}',
        code_etablissement=f'V{suffix[-8:]}',
        adresse='Test',
        pays='Sénégal',
        ville='Dakar',
        type_etablissement='lycée',
        directeur_prenom='Test',
        directeur_nom='Dir',
        directeur_email=email,
        actif=True,
    )
    etab.set_password('Test@1234')
    etab.save()
    return etab


class DashboardVisuelP1Tests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-vis',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        classe = Classe.objects.create(
            nom='2nde V',
            niveau='lycee',
            code_classe=f'V-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
            with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
                eleve = Eleve(
                    username=f'vis-{self.etab.pk}'[:20],
                    numero_eleve=f'V{self.etab.pk}'[:15],
                    nom='Vis',
                    prenom='Awa',
                    date_naissance=date(2010, 1, 1),
                    lieu_naissance='Dakar',
                    sexe='F',
                    nationalite='Sénégalaise',
                    etablissement=self.etab,
                    classe=classe,
                    date_inscription=date(2026, 9, 1),
                    statut='nouvelle',
                    parent_nom='P',
                    parent_prenom='P',
                    parent_telephone='770000001',
                    parent_lien='mere',
                    mot_de_passe_provisoire='123456',
                    actif=True,
                )
                eleve.set_password('Eleve@Test1!')
                eleve.save()
        InscriptionEleve.objects.create(
            annee_scolaire=self.annee,
            eleve=eleve,
            nom=eleve.nom,
            prenom=eleve.prenom,
            date_naissance=eleve.date_naissance,
            lieu_naissance=eleve.lieu_naissance,
            sexe=eleve.sexe,
            nationalite=eleve.nationalite,
            numero_eleve=eleve.numero_eleve,
            matricule_eleve=eleve.matricule_eleve,
            etablissement=self.etab,
            classe=classe,
            date_inscription=date(2026, 9, 1),
            statut='nouvelle',
            parent_nom=eleve.parent_nom,
            parent_prenom=eleve.parent_prenom,
            parent_telephone=eleve.parent_telephone,
            parent_lien=eleve.parent_lien,
        )

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def test_premium_kpis_order_and_empty_finance(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        payload = build_executive_dashboard(ctx)
        ids = [k['id'] for k in payload['premium_kpis']]
        self.assertEqual(
            ids,
            ['student_count', 'attendance_rate', 'success_rate', 'school_revenue', 'incomplete_files'],
        )
        recette = payload['premium_kpis'][3]
        self.assertTrue(recette['empty'])
        self.assertIsNone(recette['value'])
        self.assertEqual(payload['premium_kpis'][0]['value'], 1)

    def test_today_block_has_real_empty_states(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        payload = build_executive_dashboard(ctx)
        by_id = {item['id']: item for item in payload['today']['items']}
        self.assertTrue(by_id['presence_today']['empty'])
        self.assertIsNone(by_id['presence_today']['value'])
        self.assertIn('cours_today', by_id)
        self.assertTrue(by_id['cours_today']['empty'])
        self.assertIn('events_today', by_id)
        self.assertTrue(by_id['events_today']['empty'])
        self.assertIn('activity', payload)
        self.assertIsInstance(payload['activity'], list)

    def test_cycle_rows_include_percent(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        payload = build_executive_dashboard(ctx)
        rows = payload['cycle_distribution']['charts']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['label'], 'Lycée')
        self.assertEqual(rows[0]['value'], 1)
        self.assertEqual(rows[0]['pct'], 100.0)
        self.assertEqual(payload['cycle_distribution']['charts']['total'], 1)

    def test_presence_by_class_empty_without_rollcalls(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        payload = build_executive_dashboard(ctx)
        bloc = payload['presence_by_class']
        self.assertTrue(bloc['empty'])
        self.assertIsNone(bloc['value'])
        self.assertEqual(bloc['charts']['labels'], [])

    def test_presence_by_class_ranks_and_colors_threshold(self):
        classe = Classe.objects.get(etablissement=self.etab, nom='2nde V')
        eleve = Eleve.objects.get(etablissement=self.etab)
        matiere = Matiere.objects.create(
            nom='Hist',
            code=f'H{self.etab.pk}'[:8],
            etablissement=self.etab,
        )
        prof = Professeur.objects.create_user(
            username=f'prof.vis.{self.etab.pk}',
            email=f'prof.vis.{self.etab.pk}@test.local',
            password='Prof@Test1!',
            nom='Prof',
            prenom='Vis',
            telephone='770000088',
            numero_employe=f'PV{self.etab.pk}',
            matiere_principale=matiere,
            etablissement=self.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        today = date(2026, 10, 2)
        Presence.objects.create(
            eleve=eleve, classe=classe, professeur=prof,
            etablissement=self.etab, date=today, statut='present',
            annee_scolaire=self.annee,
        )
        Presence.objects.create(
            eleve=eleve, classe=classe, professeur=prof,
            etablissement=self.etab, date=today - timedelta(days=1), statut='absent',
            annee_scolaire=self.annee,
        )
        Presence.objects.create(
            eleve=eleve, classe=classe, professeur=prof,
            etablissement=self.etab, date=today - timedelta(days=2), statut='retard',
            annee_scolaire=self.annee,
        )
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        ctx.today = today
        payload = build_executive_dashboard(ctx)
        bloc = payload['presence_by_class']
        self.assertFalse(bloc['empty'])
        self.assertEqual(bloc['extra']['rows'][0]['taux'], 33.3)
        self.assertTrue(bloc['extra']['rows'][0]['watch'])
        self.assertEqual(bloc['charts']['colors'][0], '#ef4444')

    def test_insight_bar_flags_partial_data(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        payload = build_executive_dashboard(ctx)
        bar = payload['insight_bar']
        self.assertEqual(payload['completeness']['status'], 'partial')
        self.assertTrue(bar['partial'])
        self.assertFalse(bar['empty'])
        self.assertTrue(bar['items'])
        self.assertIn(bar['items'][0]['label'], ('À surveiller', 'Information', 'Fiabilité'))
        self.assertTrue(bar['items'][0]['message'])

    def test_insight_bar_empty_when_complete(self):
        bar = build_insight_bar([], {'status': 'complete', 'detail': '', 'gaps': []})
        self.assertTrue(bar['empty'])
        self.assertFalse(bar['partial'])
        self.assertIn('règles de pilotage', bar['empty_reason'])

    def test_premium_css_has_responsive_breakpoints(self):
        from pathlib import Path

        css = Path(__file__).resolve().parents[1].joinpath(
            'static', 'school_admin', 'css', 'directeur', 'dashboard_premium.css'
        ).read_text(encoding='utf-8')
        for breakpoint in ('1440px', '1024px', '768px', '430px'):
            self.assertIn(f'@media (max-width: {breakpoint})', css)

    def test_finance_empty_without_compta_permission(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=False,
            permissions=frozenset({'presences_liste'}),
        )
        payload = build_executive_dashboard(ctx)
        self.assertTrue(payload['finance']['empty'])
        self.assertIn('autorisé', payload['finance'].get('empty_reason', '').lower())
        recette = next(k for k in payload['premium_kpis'] if k['id'] == 'school_revenue')
        self.assertTrue(recette['empty'])
        self.assertIsNone(recette['value'])


class DashboardVisuelP6HttpTests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.etab = _make_etab()
        AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-p6',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        Classe.objects.create(
            nom='4ème P6',
            niveau='college',
            code_classe=f'P6-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.client = Client(HTTP_HOST='127.0.0.1')

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def test_anonymous_redirects_to_login(self):
        response = self.client.get('/dashboard/directeur/', {'vue': 'executive'})
        self.assertIn(response.status_code, (301, 302))
        self.assertIn('connexion', response.url)

    def test_directeur_dashboard_http_200_and_filters(self):
        logged = self.client.login(username=self.etab.username, password='Test@1234')
        self.assertTrue(logged)
        response = self.client.get(
            '/dashboard/directeur/',
            {'vue': 'executive', 'cycle': 'college'},
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        # Refonte V3 : nouvelle page et nouvelle navigation commune.
        self.assertIn('axd-page', html)
        self.assertIn('ax-dock', html)
        self.assertNotIn('linear-gradient', html)
        self.assertNotIn('dbd-a-retenir', html)
        self.assertNotIn('dbd-a-traiter', html)
        self.assertIn('value="college"', html)
        self.assertNotIn('12,4 M', html)
        self.assertNotIn('1 248', html)
        self.assertNotIn('94,2 %', html)
        self.assertNotIn('ax-sidebar', html)
        self.assertIn('id="axd-presence"', html)
        self.assertRegex(html, r'value="college"[^>]*selected|selected[^>]*value="college"')
