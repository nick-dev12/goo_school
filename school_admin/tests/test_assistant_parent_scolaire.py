"""
Tests Par4 — outils suivi scolaire parent.
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.services.assistant_parent_tools import execute_parent_tool
from school_admin.services.assistant_tools import build_assistant_context, spoken_from_tool_result
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


class AssistantParentScolaireTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='2nde Par4',
            niveau='lycee',
            code_classe=f'P4-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='p4')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Sow', 'Ibra', suffix='p4')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            type_lien='pere',
            statut='valide',
            actif=True,
        )

    def _ctx(self, session=None):
        return build_assistant_context(
            self.etab,
            session or {'eleve_consulte_id': self.eleve.id},
            parent=self.parent,
            persona='parent',
        )

    def test_get_notes_enfant_lie(self):
        out = execute_parent_tool(self._ctx(), 'get_notes_enfant', {})
        self.assertEqual(out.get('eleve_id'), self.eleve.id)
        self.assertIn('message', out)
        spoken = spoken_from_tool_result('get_notes_enfant', out, ctx=self._ctx())
        self.assertTrue(spoken)

    def test_get_devoirs_enfant(self):
        out = execute_parent_tool(self._ctx(), 'get_devoirs_enfant', {'periode': 'semaine'})
        self.assertEqual(out.get('eleve_id'), self.eleve.id)
        self.assertIn('url_devoirs', out)

    def test_get_absences_enfant(self):
        out = execute_parent_tool(self._ctx(), 'get_absences_enfant', {})
        self.assertIn('total_absences', out)

    def test_get_convocations_famille(self):
        out = execute_parent_tool(self._ctx(), 'get_convocations_famille', {})
        self.assertIn('convocations', out)

    def test_get_emploi_enfant(self):
        out = execute_parent_tool(self._ctx(), 'get_emploi_enfant', {})
        self.assertIn('publie', out)

    def test_refus_eleve_non_lie(self):
        other = _make_eleve_simple(self.etab, self.classe, 'X', 'Y', suffix='p4x')
        out = execute_parent_tool(
            self._ctx(),
            'get_notes_enfant',
            {'eleve_id': other.id},
        )
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_bloque_tool_directeur(self):
        out = execute_parent_tool(self._ctx(), 'get_effectifs', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')
