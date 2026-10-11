"""Tests dashboard D2 — retards ≠ présents, alertes, insights."""
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.model.matiere_model import Matiere
from school_admin.model.presence_model import Presence
from school_admin.model.professeur_model import Professeur
from school_admin.services.dashboard.alerts import build_dashboard_alerts
from school_admin.services.dashboard.context import build_dashboard_context
from school_admin.services.dashboard.executive import build_executive_dashboard
from school_admin.services.dashboard.metrics.engine import compute_metric, ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = uuid4().hex[:12]
    email = f'dbd.d2.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard D2 {suffix}',
        code_etablissement=f'D2{suffix[-8:]}',
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
                username=f'd2-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'D2{suffix}{etab.pk}'[:15],
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


class DashboardD2Tests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-d2',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        self.classe = Classe.objects.create(
            nom='2nde D2',
            niveau='lycee',
            code_classe=f'D2-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.matiere = Matiere.objects.create(
            nom='SVT',
            code=f'S{self.etab.pk}'[:8],
            etablissement=self.etab,
        )
        self.prof = Professeur.objects.create_user(
            username=f'prof.d2.{self.etab.pk}',
            email=f'prof.d2.{self.etab.pk}@test.local',
            password='Prof@Test1!',
            nom='Prof',
            prenom='D2',
            telephone='770000099',
            numero_employe=f'PD2{self.etab.pk}',
            matiere_principale=self.matiere,
            etablissement=self.etab,
            niveau_enseignement='lycee',
            actif=True,
        )
        self.eleve = _make_eleve(self.etab, self.classe, self.annee, 'x')
        self.today = date(2026, 10, 2)

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def _ctx(self):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
        )
        ctx.today = self.today
        return ctx

    def _presence(self, day, statut):
        return Presence.objects.create(
            eleve=self.eleve,
            classe=self.classe,
            professeur=self.prof,
            etablissement=self.etab,
            date=day,
            statut=statut,
            annee_scolaire=self.annee,
        )

    def test_retard_does_not_count_as_present(self):
        self._presence(self.today, 'present')
        self._presence(self.today - timedelta(days=1), 'retard')
        trend = compute_metric('attendance_trend', self._ctx())
        self.assertFalse(trend['empty'])
        self.assertEqual(trend['rate_7'], 50.0)

    def test_attendance_rate_year_excludes_retard_from_numerator(self):
        self._presence(self.today, 'present')
        self._presence(self.today - timedelta(days=1), 'retard')
        rate = compute_metric('attendance_rate', self._ctx())
        self.assertEqual(rate['value'], 50.0)
        self.assertIn('retard', rate['definition'].lower())

    def test_alerts_include_missing_rollcalls(self):
        alerts = build_dashboard_alerts(self._ctx())
        ids = {a['id'] for a in alerts}
        self.assertIn('missing_rollcalls', ids)

    def test_executive_includes_alerts_and_trend(self):
        self._presence(self.today, 'present')
        payload = build_executive_dashboard(self._ctx())
        self.assertIn('alerts', payload)
        self.assertIn('insights', payload)
        self.assertIn('attendance_trend', payload)
        self.assertFalse(payload['attendance_trend']['empty'])
