"""
Elv4 — lecture scolaire (wrappers self-only).
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.services.assistant_eleve_schema import (
    ELEVE_NAV_TOOLS,
    ELEVE_SCOLAIRE_TOOLS,
)
from school_admin.services.assistant_eleve_tools import execute_eleve_tool, get_eleve_tools_schema
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
    _make_etablissement_type,
)


class AssistantEleveToolsElv4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab_col = _make_etablissement()
        cls.annee_col = _make_annee(cls.etab_col)
        cls.cl_col = Classe.objects.create(
            nom='Elv4 Col',
            niveau='college',
            code_classe=f'E4C-{cls.etab_col.pk}',
            capacite_max=30,
            etablissement=cls.etab_col,
        )
        cls.eleve_col = _make_eleve_simple(
            cls.etab_col, cls.cl_col, 'Sarr', 'Ousmane', suffix='e4c'
        )
        cls.etab_pri = _make_etablissement_type('primary', 'e4pri')
        cls.annee_pri = _make_annee(cls.etab_pri)
        cls.cl_pri = Classe.objects.create(
            nom='CM2 Elv4',
            niveau='primaire',
            code_classe=f'E4P-{cls.etab_pri.pk}',
            capacite_max=30,
            etablissement=cls.etab_pri,
        )
        cls.eleve_pri = _make_eleve_simple(
            cls.etab_pri, cls.cl_pri, 'Gueye', 'Aida', suffix='e4p'
        )

    def _ctx(self, eleve):
        return build_assistant_context(
            eleve.etablissement,
            {},
            eleve=eleve,
            persona='eleve',
        )

    def test_schema_inclut_scolaire(self):
        names = {
            item['function']['name']
            for item in get_eleve_tools_schema(self._ctx(self.eleve_col))
            if item.get('function')
        }
        self.assertEqual(names, set(ELEVE_NAV_TOOLS | ELEVE_SCOLAIRE_TOOLS))

    def test_get_mes_notes_college(self):
        out = execute_eleve_tool(self._ctx(self.eleve_col), 'get_mes_notes', {})
        self.assertIn('message', out)
        self.assertNotIn('erreur', out.get('statut', ''))

    def test_get_mes_notes_primaire(self):
        out = execute_eleve_tool(self._ctx(self.eleve_pri), 'get_mes_notes', {})
        self.assertIn('message', out)

    def test_get_mon_profil(self):
        out = execute_eleve_tool(self._ctx(self.eleve_col), 'get_mon_profil', {})
        self.assertIn('matricule', out)
        self.assertIn('profil', out.get('url_profil', ''))

    def test_get_mes_devoirs(self):
        out = execute_eleve_tool(self._ctx(self.eleve_col), 'get_mes_devoirs', {})
        self.assertIn('message', out)
