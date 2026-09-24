"""
Tests outils assistant parent Par2.
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.services.assistant_pages_parent import find_page, list_pages
from school_admin.services.assistant_parent_tools import (
    PARENT_TOOL_NAMES,
    execute_parent_tool,
    get_parent_tools_schema,
    tool_ouvrir_page,
    tool_select_enfant,
)
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.services.gemini_assistant_service import tools_schema_for
from school_admin.tests.test_assistant_directeur_tools import _make_annee, _make_etablissement
from school_admin.tests.test_assistant_parent_scope import _make_parent
from school_admin.tests.test_assistant_directeur_tools import _make_eleve_simple


class AssistantParentToolsPar2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='1ere Parent Par2',
            niveau='lycee',
            code_classe=f'P2-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='p2')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Ba', 'Awa', suffix='p2')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )

    def _ctx(self, session=None):
        store = {} if session is None else session
        return build_assistant_context(
            self.etab,
            store,
            parent=self.parent,
            persona='parent',
        )

    def test_schema_parent_quinze_tools(self):
        schema = get_parent_tools_schema()
        names = {item['function']['name'] for item in schema}
        self.assertEqual(names, PARENT_TOOL_NAMES)
        self.assertEqual(len(names), 20)
        ctx = self._ctx({'eleve_consulte_id': self.eleve.id})
        self.assertEqual(len(tools_schema_for(ctx)), 20)

    def test_catalogue_pages_parent_enfant(self):
        pages = list_pages()
        keys = {p['key'] for p in pages}
        self.assertIn('accueil_parent', keys)
        self.assertIn('notes', keys)
        self.assertIn('accueil_enfant', keys)
        self.assertTrue(find_page('scolarité'))

    def test_get_mes_enfants(self):
        out = execute_parent_tool(self._ctx(), 'get_mes_enfants', {})
        self.assertEqual(out['nb'], 1)
        self.assertEqual(out['enfants'][0]['id'], self.eleve.id)

    def test_select_enfant_session(self):
        session = {}
        ctx = self._ctx(session)
        out = tool_select_enfant(ctx, {'eleve_id': self.eleve.id})
        self.assertEqual(out['statut'], 'ok')
        self.assertEqual(session.get('eleve_consulte_id'), self.eleve.id)
        self.assertTrue(session.get('mode_consultation_parent'))

    def test_ouvrir_page_hub(self):
        out = tool_ouvrir_page(self._ctx(), {'page_key': 'annonces_parent'})
        self.assertEqual(out['statut'], 'ok')
        self.assertIn('/parent/annonces', out['url'])
        self.assertTrue(out['ouvrir'])

    def test_ouvrir_page_enfant_sans_session(self):
        out = tool_ouvrir_page(self._ctx(), {'page_key': 'notes'})
        self.assertEqual(out.get('statut'), 'enfant_requis')

    def test_ouvrir_page_enfant_avec_session(self):
        session = {'eleve_consulte_id': self.eleve.id}
        out = tool_ouvrir_page(self._ctx(session), {'page_key': 'notes'})
        self.assertEqual(out['statut'], 'ok')
        self.assertIn('/eleve/notes', out['url'])

    def test_get_resume_enfant(self):
        out = execute_parent_tool(
            self._ctx({'eleve_consulte_id': self.eleve.id}),
            'get_resume_enfant',
            {},
        )
        self.assertEqual(out['eleve_id'], self.eleve.id)
        self.assertIn('message', out)

    def test_execute_tool_bloque_directeur(self):
        out = execute_tool(self._ctx(), 'get_effectifs', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_select_enfant_refuse_non_lie(self):
        other = _make_eleve_simple(self.etab, self.classe, 'X', 'Y', suffix='p2x')
        out = tool_select_enfant(self._ctx(), {'eleve_id': other.id})
        self.assertEqual(out.get('statut'), 'acces_refuse')
