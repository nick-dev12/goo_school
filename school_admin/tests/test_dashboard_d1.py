"""Tests dashboard directeur D1 — filtres, effectifs, executive."""
from datetime import date
from uuid import uuid4
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.periode_model import PeriodeScolaire
from school_admin.services.dashboard.context import build_dashboard_context
from school_admin.services.dashboard.executive import build_executive_dashboard
from school_admin.services.dashboard.metrics.engine import compute_metric, ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = uuid4().hex[:12]
    email = f'dbd.d1.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard D1 {suffix}',
        code_etablissement=f'D1{suffix[-8:]}',
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


def _make_eleve(etab, classe, annee, nom, prenom, suffix):
    with patch.object(Eleve, '_should_regenerate_qr', return_value=False):
        with patch.object(Etablissement, 'recalculer_facturation', return_value=None):
            eleve = Eleve(
                username=f'd1-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'D1{suffix}{etab.pk}'[:15],
                nom=nom,
                prenom=prenom,
                date_naissance=date(2010, 1, 1),
                lieu_naissance='Dakar',
                sexe='F',
                nationalite='Sénégalaise',
                etablissement=etab,
                classe=classe,
                date_inscription=date(2026, 9, 1),
                statut='nouvelle',
                parent_nom=nom,
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


class DashboardD1Tests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-d1',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        self.college = Classe.objects.create(
            nom='6e A',
            niveau='college',
            code_classe=f'C-{self.etab.pk}',
            capacite_max=2,
            etablissement=self.etab,
        )
        self.lycee = Classe.objects.create(
            nom='2nde A',
            niveau='lycee',
            code_classe=f'L-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.e1 = _make_eleve(self.etab, self.college, self.annee, 'Ba', 'Awa', 'a')
        self.e2 = _make_eleve(self.etab, self.college, self.annee, 'Diop', 'Sira', 'b')
        self.e3 = _make_eleve(self.etab, self.lycee, self.annee, 'Fall', 'Ibra', 'c')
        self.periode = PeriodeScolaire.objects.create(
            etablissement=self.etab,
            nom_periode='1er Trimestre',
            type_periode='trimestre',
            date_debut=date(2026, 9, 1),
            date_fin=date(2026, 12, 15),
            annee_scolaire=self.annee.libelle,
            annee_scolaire_fk=self.annee,
            est_active=True,
        )

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def _ctx(self, params=None, **kwargs):
        request = self.factory.get('/dashboard/directeur/', params or {})
        return build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=self.periode,
            is_directeur=True,
            **kwargs,
        )

    def test_student_count_respects_cycle_filter(self):
        all_count = compute_metric('student_count', self._ctx())
        college_count = compute_metric('student_count', self._ctx({'cycle': 'college'}))
        self.assertEqual(all_count['value'], 3)
        self.assertEqual(college_count['value'], 2)

    def test_invalid_cycle_ignored(self):
        ctx = self._ctx({'cycle': 'inconnu'})
        self.assertEqual(ctx.filters.cycle, '')
        self.assertEqual(compute_metric('student_count', ctx)['value'], 3)

    def test_classe_other_etablissement_ignored(self):
        other = _make_etab()
        other_classe = Classe.objects.create(
            nom='Intrus',
            niveau='lycee',
            code_classe=f'X-{other.pk}',
            capacite_max=10,
            etablissement=other,
        )
        ctx = self._ctx({'classe': str(other_classe.id)})
        self.assertEqual(compute_metric('student_count', ctx)['value'], 3)

    def test_class_capacity_detects_overflow(self):
        metric = compute_metric('class_capacity', self._ctx({'cycle': 'college'}))
        self.assertFalse(metric['empty'])
        self.assertEqual(metric['extra']['effectif'], 2)
        self.assertEqual(metric['extra']['capacite'], 2)
        self.assertEqual(metric['extra']['classes_pleines'], 1)

    def test_cycle_distribution(self):
        metric = compute_metric('cycle_distribution', self._ctx())
        labels = metric['charts']['labels']
        self.assertIn('Collège', labels)
        self.assertIn('Lycée', labels)

    def test_periode_other_year_ignored(self):
        other_annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2025-2026-d1',
            annee_debut=2025,
            annee_fin=2026,
            date_debut=date(2025, 9, 1),
            date_fin=date(2026, 6, 30),
            est_active=False,
            est_ouverte=False,
        )
        other_periode = PeriodeScolaire.objects.create(
            etablissement=self.etab,
            nom_periode='Ancien T1',
            type_periode='trimestre',
            date_debut=date(2025, 9, 1),
            date_fin=date(2025, 12, 15),
            annee_scolaire=other_annee.libelle,
            annee_scolaire_fk=other_annee,
            est_active=False,
        )
        ctx = self._ctx({'periode': str(other_periode.id)})
        self.assertEqual(ctx.periode_scolaire.id, self.periode.id)

    def test_personnel_without_eleves_permission(self):
        request = self.factory.get('/dashboard/directeur/')
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=self.periode,
            is_directeur=False,
            permissions=frozenset({'presences_liste'}),
        )
        result = compute_metric('student_count', ctx)
        self.assertTrue(result['empty'])

    def test_executive_payload_empty_attendance_not_zero(self):
        payload = build_executive_dashboard(self._ctx())
        attendance = next(k for k in payload['kpis'] if k['id'] == 'attendance_rate')
        self.assertTrue(attendance['empty'])
        self.assertIsNone(attendance.get('value'))
        self.assertIn('today', payload)
        self.assertIn('completeness', payload)
        self.assertTrue(payload['filters']['cycles'])
