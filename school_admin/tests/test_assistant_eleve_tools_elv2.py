"""
Elv2 — navigation assistant élève.
"""
from django.test import TestCase
from django.urls import reverse

from school_admin.model.classe_model import Classe
from school_admin.services.assistant_eleve_schema import ELEVE_NAV_TOOLS
from school_admin.services.assistant_eleve_tools import (
    execute_eleve_tool,
    get_eleve_tools_schema,
)
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)


class AssistantEleveToolsElv2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Elv2 Nav',
            niveau='college',
            code_classe=f'E2N-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Fall', 'Aminata', suffix='e2n')

    def _ctx(self):
        return build_assistant_context(
            self.eleve.etablissement,
            {},
            eleve=self.eleve,
            persona='eleve',
        )

    def test_schema_contient_nav(self):
        names = {
            item['function']['name']
            for item in get_eleve_tools_schema(self._ctx())
            if item.get('function')
        }
        self.assertTrue(set(ELEVE_NAV_TOOLS) <= names)

    def test_lister_pages_espace_eleve(self):
        out = execute_eleve_tool(self._ctx(), 'lister_pages', {})
        keys = {p['key'] for p in out.get('pages', [])}
        self.assertIn('devoirs', keys)
        self.assertIn('notes', keys)

    def test_ouvrir_devoirs(self):
        out = execute_eleve_tool(self._ctx(), 'ouvrir_page', {'page_key': 'devoirs'})
        self.assertEqual(out.get('statut'), 'ok')
        self.assertIn('devoirs', out.get('url', ''))
        self.assertTrue(out.get('ouvrir'))

    def test_get_mon_resume(self):
        out = execute_eleve_tool(self._ctx(), 'get_mon_resume', {})
        self.assertEqual(out.get('eleve_id'), self.eleve.id)
        self.assertIn('classe', out)

    def test_refuse_eleve_id_autre(self):
        from school_admin.tests.test_assistant_directeur_tools import _make_eleve_simple

        autre = _make_eleve_simple(self.etab, self.classe, 'X', 'Y', suffix='e2o')
        out = execute_eleve_tool(self._ctx(), 'ouvrir_page', {
            'page_key': 'devoirs',
            'eleve_id': autre.id,
        })
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_bloque_directeur(self):
        out = execute_tool(self._ctx(), 'get_effectifs', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')
