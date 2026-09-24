"""
Elv7 — actions confirmées volontairement absentes (arbitrage produit).
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.services.assistant_eleve_schema import (
    ELEVE_TOOL_NAMES_ALL,
    ELEVE_WRITE_TOOLS,
    build_eleve_tool_schemas,
)
from school_admin.services.assistant_eleve_tools import execute_eleve_tool
from school_admin.services.assistant_tools import build_assistant_context
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)


class AssistantEleveElv7NoWriteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Elv7',
            niveau='college',
            code_classe=f'E7-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Fall', 'Ibou', suffix='e7')

    def _ctx(self):
        return build_assistant_context(
            self.eleve.etablissement,
            {},
            eleve=self.eleve,
            persona='eleve',
        )

    def test_schema_sans_ecriture(self):
        self.assertFalse(ELEVE_WRITE_TOOLS)
        names = {
            item['function']['name']
            for item in build_eleve_tool_schemas(self._ctx())
            if item.get('function')
        }
        self.assertEqual(names, set(ELEVE_TOOL_NAMES_ALL))
        self.assertNotIn('marquer_notification_lue', names)

    def test_marquer_notification_bloque(self):
        out = execute_eleve_tool(
            self._ctx(),
            'marquer_notification_lue',
            {'notification_id': 1},
        )
        self.assertEqual(out.get('statut'), 'hors_perimetre')
