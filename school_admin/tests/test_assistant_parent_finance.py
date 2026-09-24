"""
Tests Par5 — scolarité parent, reçus, agrégats famille.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.comptabilite_eleve_model import ComptabiliteEleve, FraisInscription, PaiementEleve
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.services.assistant_parent_tools import execute_parent_tool
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_eleve_simple, _make_etablissement
from school_admin.tests.test_assistant_parent_scope import _make_parent


class AssistantParentFinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Tle Par5',
            niveau='lycee',
            code_classe=f'P5-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='p5')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Diop', 'Aminata', suffix='p5')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )
        cls.fiche = ComptabiliteEleve.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            statut_paiement='en_attente',
        )
        cls.frais = FraisInscription.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            comptabilite_eleve=cls.fiche,
            montant=Decimal('80000'),
            montant_paye=Decimal('20000'),
            reste_a_payer=Decimal('60000'),
            date_echeance=date(2026, 10, 15),
            statut='en_attente',
            type_frais='inscription',
        )
        cls.paiement = PaiementEleve.objects.create(
            eleve=cls.eleve,
            etablissement=cls.etab,
            annee_scolaire=cls.annee,
            type_paiement='frais_inscription',
            frais_inscription=cls.frais,
            montant=Decimal('20000'),
            mode_paiement='especes',
            numero_recu='REC-PAR5-001',
        )

    def _ctx(self, session=None):
        from school_admin.services.assistant_tools import build_assistant_context

        return build_assistant_context(
            self.etab,
            session or {'eleve_consulte_id': self.eleve.id},
            parent=self.parent,
            persona='parent',
        )

    def test_get_scolarite_enfant(self):
        out = execute_parent_tool(self._ctx(), 'get_scolarite_enfant', {})
        self.assertEqual(out.get('eleve_id'), self.eleve.id)
        self.assertIsNotNone(out.get('reste'))
        self.assertIn('recus_recents', out)

    def test_get_scolarite_famille(self):
        out = execute_parent_tool(self._ctx(), 'get_scolarite_famille', {})
        self.assertGreaterEqual(out.get('nb_enfants'), 1)
        self.assertIn('dette_totale', out)

    def test_ouvrir_recu_lie(self):
        out = execute_parent_tool(
            self._ctx(),
            'ouvrir_recu',
            {'paiement_id': self.paiement.id},
        )
        self.assertEqual(out.get('statut'), 'ok')
        self.assertIn('/parent/scolarite/recu/', out.get('url', ''))

    def test_ouvrir_recu_refuse_non_lie(self):
        other = _make_eleve_simple(self.etab, self.classe, 'X', 'Y', suffix='p5x')
        fiche = ComptabiliteEleve.objects.create(
            eleve=other,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            statut_paiement='en_attente',
        )
        frais = FraisInscription.objects.create(
            eleve=other,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            comptabilite_eleve=fiche,
            montant=Decimal('10000'),
            montant_paye=Decimal('1000'),
            reste_a_payer=Decimal('9000'),
            date_echeance=date(2026, 11, 1),
            statut='en_attente',
            type_frais='inscription',
        )
        pay = PaiementEleve.objects.create(
            eleve=other,
            etablissement=self.etab,
            annee_scolaire=self.annee,
            type_paiement='frais_inscription',
            frais_inscription=frais,
            montant=Decimal('1000'),
            mode_paiement='especes',
            numero_recu='REC-OTHER',
        )
        out = execute_parent_tool(self._ctx(), 'ouvrir_recu', {'paiement_id': pay.id})
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_enregistrer_paiement_interdit(self):
        out = execute_parent_tool(
            self._ctx(),
            'enregistrer_paiement',
            {'eleve_id': self.eleve.id, 'montant': 1000},
        )
        self.assertEqual(out.get('statut'), 'hors_perimetre')
