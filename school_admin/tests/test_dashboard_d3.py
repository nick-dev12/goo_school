"""Tests dashboard D3 — pédagogie : seuil, empty, isolation."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.moyenne_periode_model import MoyennePeriode
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.model.standards_reussite_model import StandardsReussite
from school_admin.services.dashboard.alerts import build_dashboard_alerts
from school_admin.services.dashboard.context import build_dashboard_context
from school_admin.services.dashboard.executive import build_executive_dashboard
from school_admin.services.dashboard.metrics.engine import compute_metric, ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = uuid4().hex[:12]
    email = f'dbd.d3.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard D3 {suffix}',
        code_etablissement=f'D3{suffix[-8:]}',
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


def _make_eleve(etab, classe, annee, suffix):
    with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
        with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
            eleve = Eleve(
                username=f'd3-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'D3{suffix}{etab.pk}'[:15],
                nom='Test',
                prenom=suffix,
                date_naissance=date(2010, 1, 1),
                lieu_naissance='Dakar',
                sexe='M',
                nationalite='Sénégalaise',
                etablissement=etab,
                classe=classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom='P',
                parent_prenom='P',
                parent_telephone='770000001',
                parent_lien='pere',
                mot_de_passe_provisoire='123456',
                actif=True,
            )
            eleve.set_password('Eleve@Test1!')
            eleve.save()
    InscriptionEleve.objects.create(
        annee_scolaire=annee,
        eleve=eleve,
        nom=eleve.nom,
        prenom=eleve.prenom,
        date_naissance=eleve.date_naissance,
        lieu_naissance=eleve.lieu_naissance,
        sexe=eleve.sexe,
        nationalite=eleve.nationalite,
        numero_eleve=eleve.numero_eleve,
        matricule_eleve=eleve.matricule_eleve,
        etablissement=etab,
        classe=classe,
        date_inscription=date(2026, 9, 1),
        statut='nouvelle',
        parent_nom=eleve.parent_nom,
        parent_prenom=eleve.parent_prenom,
        parent_telephone=eleve.parent_telephone,
        parent_lien=eleve.parent_lien,
    )
    return eleve


class DashboardD3Tests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-d3',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        self.classe = Classe.objects.create(
            nom='2nde D3',
            niveau='lycee',
            code_classe=f'D3-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.eleve_a = _make_eleve(self.etab, self.classe, self.annee, 'a')
        self.eleve_b = _make_eleve(self.etab, self.classe, self.annee, 'b')
        self.periode_1 = PeriodeScolaire.objects.create(
            etablissement=self.etab,
            nom_periode='Trimestre 1',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee,
            est_active=False,
        )
        self.periode_2 = PeriodeScolaire.objects.create(
            etablissement=self.etab,
            nom_periode='Trimestre 2',
            type_periode='trimestre',
            date_debut=date(2027, 1, 5),
            date_fin=date(2027, 3, 31),
            annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee,
            est_active=True,
        )

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def _ctx(self, periode=None, params=None, **kwargs):
        request = self.factory.get('/dashboard/directeur/', params or {'vue': 'executive'})
        return build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=periode or self.periode_2,
            is_directeur=True,
            **kwargs,
        )

    def _moyenne(self, eleve, periode, value, **kwargs):
        defaults = {
            'eleve': eleve,
            'etablissement': self.etab,
            'periode': periode,
            'annee_scolaire': self.annee,
            'est_moyenne_generale': True,
            'moyenne_generale': Decimal(str(value)),
        }
        defaults.update(kwargs)
        return MoyennePeriode.objects.create(**defaults)

    def test_success_rate_empty_without_averages(self):
        metric = compute_metric('success_rate', self._ctx())
        self.assertTrue(metric['empty'])
        self.assertIsNone(metric['value'])

    def test_success_rate_uses_configured_threshold(self):
        StandardsReussite.objects.create(
            etablissement=self.etab,
            annee_scolaire=self.annee,
            moyenne_passage=Decimal('12.00'),
        )
        self._moyenne(self.eleve_a, self.periode_2, '11.00')
        self._moyenne(self.eleve_b, self.periode_2, '13.00')
        metric = compute_metric('success_rate', self._ctx())
        self.assertFalse(metric['empty'])
        self.assertEqual(metric['value'], 50.0)
        self.assertEqual(metric['extra']['seuil'], 12.0)
        self.assertEqual(metric['extra']['sous_seuil'], 1)

    def test_default_threshold_is_ten(self):
        self._moyenne(self.eleve_a, self.periode_2, '09.50')
        self._moyenne(self.eleve_b, self.periode_2, '10.00')
        metric = compute_metric('success_rate', self._ctx())
        self.assertEqual(metric['value'], 50.0)
        self.assertEqual(metric['extra']['seuil'], 10.0)

    def test_average_grade_and_distribution(self):
        self._moyenne(self.eleve_a, self.periode_2, '08.00')
        self._moyenne(self.eleve_b, self.periode_2, '14.00')
        avg = compute_metric('average_grade', self._ctx())
        dist = compute_metric('grade_distribution', self._ctx())
        self.assertEqual(avg['value'], 11.0)
        self.assertFalse(dist['empty'])
        self.assertEqual(dist['extra']['sous_seuil'], 1)
        self.assertEqual(len(dist['charts']['labels']), 6)
        self.assertEqual(len(dist['extra']['at_risk']), 1)
        self.assertEqual(dist['extra']['at_risk'][0]['nom'], self.eleve_a.nom_complet)
        self.assertTrue(dist['extra']['by_cycle'])
        self.assertEqual(dist['charts']['by_cycle']['labels'][0], 'Lycée')
        self.assertEqual(dist['charts']['by_cycle']['values'][0], 50.0)

    def test_previous_period_comparison(self):
        self._moyenne(self.eleve_a, self.periode_1, '14.00')
        self._moyenne(self.eleve_b, self.periode_1, '15.00')
        self._moyenne(self.eleve_a, self.periode_2, '08.00')
        self._moyenne(self.eleve_b, self.periode_2, '09.00')
        metric = compute_metric('success_rate', self._ctx())
        self.assertEqual(metric['value'], 0.0)
        self.assertTrue(metric['comparison']['compatible'])
        self.assertEqual(metric['comparison']['reference_value'], 100.0)
        self.assertEqual(metric['comparison']['delta'], -100.0)

    def test_other_etablissement_ignored(self):
        other = _make_etab()
        other_annee = AnneeScolaire.objects.create(
            etablissement=other,
            libelle='2026-2027-d3o',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        other_classe = Classe.objects.create(
            nom='Intrus',
            niveau='lycee',
            code_classe=f'XO-{other.pk}',
            capacite_max=10,
            etablissement=other,
        )
        other_eleve = _make_eleve(other, other_classe, other_annee, 'z')
        other_periode = PeriodeScolaire.objects.create(
            etablissement=other,
            nom_periode='T2',
            type_periode='trimestre',
            date_debut=date(2027, 1, 5),
            date_fin=date(2027, 3, 31),
            annee_scolaire=other_annee.libelle,
            annee_scolaire_fk=other_annee,
            est_active=True,
        )
        MoyennePeriode.objects.create(
            eleve=other_eleve,
            etablissement=other,
            periode=other_periode,
            annee_scolaire=other_annee,
            est_moyenne_generale=True,
            moyenne_generale=Decimal('18.00'),
        )
        metric = compute_metric('success_rate', self._ctx())
        self.assertTrue(metric['empty'])

    def test_personnel_without_notes_permission(self):
        self._moyenne(self.eleve_a, self.periode_2, '14.00')
        request = self.factory.get('/dashboard/directeur/')
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=self.periode_2,
            is_directeur=False,
            permissions=frozenset({'presences_liste'}),
        )
        result = compute_metric('success_rate', ctx)
        self.assertTrue(result['empty'])
        self.assertIn('autorisé', result.get('empty_reason', '').lower())

    def test_alerts_and_executive_results(self):
        self._moyenne(self.eleve_a, self.periode_2, '07.00')
        self._moyenne(self.eleve_b, self.periode_2, '15.00')
        ctx = self._ctx()
        alerts = build_dashboard_alerts(ctx)
        ids = {a['id'] for a in alerts}
        self.assertIn('students_below_threshold', ids)
        self.assertIn('unpublished_bulletins', ids)
        payload = build_executive_dashboard(ctx)
        success = next(k for k in payload['kpis'] if k['id'] == 'success_rate')
        average = next(k for k in payload['kpis'] if k['id'] == 'average_grade')
        self.assertEqual(success['value'], 50.0)
        self.assertEqual(average['value'], 11.0)
        self.assertFalse(payload['results']['empty'])
        self.assertEqual(payload['results']['charts']['values'][0], 1)
