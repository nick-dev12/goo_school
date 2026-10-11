"""Tests socle dashboard directeur (D0)."""
from datetime import date
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.services.dashboard.context import (
    VUE_ANALYTIQUE,
    VUE_EXECUTIVE,
    build_dashboard_context,
)
from school_admin.services.dashboard.metrics.engine import compute_metric, ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = date.today().strftime('%Y%m%d%H%M%S%f')
    email = f'dbd.d0.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard D0 {suffix}',
        code_etablissement=f'D0{suffix[-8:]}',
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


class DashboardD0ContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee_active = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        self.annee_old = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2025-2026',
            annee_debut=2025,
            annee_fin=2026,
            date_debut=date(2025, 9, 1),
            date_fin=date(2026, 6, 30),
            est_active=False,
            est_ouverte=False,
        )

    def test_vue_executive_default(self):
        request = self.factory.get('/dashboard/directeur/')
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee_active,
            annee_scolaire_reellement_active=self.annee_active,
            periode_scolaire=None,
            is_directeur=True,
        )
        self.assertEqual(ctx.vue, VUE_EXECUTIVE)
        self.assertTrue(ctx.is_executive)

    def test_vue_analytique_query(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'analytique'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee_active,
            annee_scolaire_reellement_active=self.annee_active,
            periode_scolaire=None,
            is_directeur=True,
        )
        self.assertEqual(ctx.vue, VUE_ANALYTIQUE)

    def test_filters_parsed(self):
        request = self.factory.get(
            '/dashboard/directeur/',
            {'classe': '12', 'cycle': 'college', 'periode': '3'},
        )
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee_active,
            annee_scolaire_reellement_active=self.annee_active,
            periode_scolaire=None,
            is_directeur=True,
        )
        self.assertEqual(ctx.filters.classe_id, 12)
        self.assertEqual(ctx.filters.cycle, 'college')
        self.assertEqual(ctx.filters.periode_id, 3)

    def test_freshness_meta_not_live(self):
        request = self.factory.get('/dashboard/directeur/')
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee_active,
            annee_scolaire_reellement_active=self.annee_active,
            periode_scolaire=None,
            is_directeur=True,
        )
        meta = ctx.freshness_meta()
        self.assertIn('computed_at', meta)
        self.assertIn('Mis à jour', meta['freshness_label'])
        self.assertFalse(meta['is_live'])


class DashboardD0MetricsTests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def test_student_count_empty_without_annee(self):
        request = RequestFactory().get('/')
        ctx = build_dashboard_context(
            request,
            etablissement=_make_etab(),
            annee_scolaire=None,
            annee_scolaire_reellement_active=None,
            periode_scolaire=None,
            is_directeur=True,
        )
        result = compute_metric('student_count', ctx)
        self.assertTrue(result.get('empty'))
        self.assertIsNone(result.get('value'))

    def test_permission_denied_for_personnel_without_right(self):
        request = RequestFactory().get('/')
        etab = _make_etab()
        ctx = build_dashboard_context(
            request,
            etablissement=etab,
            annee_scolaire=None,
            annee_scolaire_reellement_active=None,
            periode_scolaire=None,
            is_directeur=False,
            permissions=frozenset({'presences_liste'}),
        )
        result = compute_metric('student_count', ctx)
        self.assertTrue(result.get('empty'))
        self.assertIn('autorisé', result.get('empty_reason', '').lower())
