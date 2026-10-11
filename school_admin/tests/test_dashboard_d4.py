"""Tests dashboard D4 — finances : recouvrement, reste, permissions."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from school_admin.model.annee_scolaire_model import AnneeScolaire
from school_admin.model.classe_model import Classe
from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, FraisInscription
from school_admin.model.eleve_model import Eleve
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.inscription_eleve_model import InscriptionEleve
from school_admin.services.dashboard.context import build_dashboard_context
from school_admin.services.dashboard.executive import build_executive_dashboard
from school_admin.services.dashboard.metrics.engine import compute_metric, ensure_metrics_registered
from school_admin.services.dashboard.metrics.registry import METRIC_REGISTRY


def _make_etab():
    suffix = uuid4().hex[:12]
    email = f'dbd.d4.{suffix}@aria-test.local'
    etab = Etablissement(
        username=email,
        email=email,
        nom=f'Dashboard D4 {suffix}',
        code_etablissement=f'D4{suffix[-8:]}',
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
                username=f'd4-{suffix}-{etab.pk}'[:20],
                numero_eleve=f'D4{suffix}{etab.pk}'[:15],
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


class DashboardD4Tests(TestCase):
    def setUp(self):
        METRIC_REGISTRY.clear()
        ensure_metrics_registered()
        self.factory = RequestFactory()
        self.etab = _make_etab()
        self.annee = AnneeScolaire.objects.create(
            etablissement=self.etab,
            libelle='2026-2027-d4',
            annee_debut=2026,
            annee_fin=2027,
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            est_active=True,
            est_ouverte=True,
        )
        self.classe = Classe.objects.create(
            nom='2nde D4',
            niveau='lycee',
            code_classe=f'D4-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.eleve = _make_eleve(self.etab, self.classe, self.annee, 'fin')
        self.today = date(2026, 10, 2)

    def tearDown(self):
        METRIC_REGISTRY.clear()

    def _ctx(self, **kwargs):
        request = self.factory.get('/dashboard/directeur/', {'vue': 'executive'})
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=True,
            **kwargs,
        )
        ctx.today = self.today
        return ctx

    def _fiche(self, montant='50000', paye='20000', statut='en_retard'):
        fiche = ComptabiliteEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            statut_paiement=statut,
        )
        FraisInscription.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            comptabilite_eleve=fiche,
            montant=Decimal(montant),
            montant_paye=Decimal(paye),
            reste_a_payer=Decimal(montant) - Decimal(paye),
            date_echeance=date(2026, 9, 1),
            statut='en_retard',
            type_frais='inscription',
        )
        return fiche

    def test_collection_rate_empty_without_charges(self):
        ComptabiliteEleve.objects.create(
            eleve=self.eleve,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            statut_paiement='a_jour',
        )
        metric = compute_metric('collection_rate', self._ctx())
        self.assertTrue(metric['empty'])

    def test_collection_rate_matches_assistant_formula(self):
        self._fiche('50000', '20000')
        rate = compute_metric('collection_rate', self._ctx())
        outstanding = compute_metric('outstanding_amount', self._ctx())
        self.assertFalse(rate['empty'])
        self.assertEqual(rate['value'], 40.0)
        self.assertEqual(outstanding['value'], 30000.0)

    def test_finance_status_includes_class_row(self):
        self._fiche('50000', '20000')
        status = compute_metric('finance_status', self._ctx())
        self.assertFalse(status['empty'])
        self.assertEqual(len(status['extra']['classes']), 1)
        self.assertEqual(status['extra']['classes'][0]['classe'], '2nde D4')
        self.assertEqual(status['extra']['recouvrement'], 40.0)
        self.assertEqual(status['extra']['reste'], 30000.0)
        self.assertIn(status['charts']['mode'], ('payments', 'statuts'))

    def test_personnel_without_compta_permission(self):
        self._fiche('50000', '20000')
        request = self.factory.get('/dashboard/directeur/')
        ctx = build_dashboard_context(
            request,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            annee_scolaire_reellement_active=self.annee,
            periode_scolaire=None,
            is_directeur=False,
            permissions=frozenset({'presences_liste'}),
        )
        ctx.today = self.today
        result = compute_metric('collection_rate', ctx)
        self.assertTrue(result['empty'])
        self.assertIn('autorisé', result.get('empty_reason', '').lower())

    def test_executive_includes_finance_block(self):
        self._fiche('50000', '20000')
        payload = build_executive_dashboard(self._ctx())
        collection = next(k for k in payload['kpis'] if k['id'] == 'collection_rate')
        self.assertEqual(collection['value'], 40.0)
        self.assertFalse(payload['finance']['empty'])
