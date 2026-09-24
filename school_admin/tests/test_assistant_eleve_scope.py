"""
Tests périmètre assistant élève (Elv0).
"""
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.services.assistant_eleve_scope import assert_self_only, get_self_eleve
from school_admin.services.assistant_eleve_tools import execute_eleve_tool, get_eleve_tools_schema
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


class AssistantEleveScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='3eme Elv0',
            niveau='college',
            code_classe=f'E0-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Diallo', 'Mamadou', suffix='elv0')
        cls.autre = _make_eleve_simple(cls.etab, cls.classe, 'Ba', 'Fatou', suffix='elv0b')

    def _ctx(self, eleve=None):
        eleve = eleve or self.eleve
        return build_assistant_context(
            eleve.etablissement,
            {},
            eleve=eleve,
            persona='eleve',
        )

    def test_get_self_eleve(self):
        ctx = self._ctx()
        self.assertEqual(get_self_eleve(ctx).pk, self.eleve.pk)

    def test_assert_self_only_refuse_autre_id(self):
        ctx = self._ctx()
        denied = assert_self_only(ctx, self.autre.id)
        self.assertEqual(denied.get('statut'), 'acces_refuse')

    def test_schema_nav_elv2(self):
        names = {
            item['function']['name']
            for item in get_eleve_tools_schema(self._ctx())
            if item.get('function')
        }
        self.assertIn('ouvrir_page', names)

    def test_bloque_tool_directeur(self):
        out = execute_tool(self._ctx(), 'get_effectifs', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_bloque_tool_parent(self):
        out = execute_eleve_tool(self._ctx(), 'get_mes_enfants', {})
        self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_get_mes_notes_self_only(self):
        out = execute_eleve_tool(self._ctx(), 'get_mes_notes', {})
        self.assertIn('message', out)
        self.assertNotEqual(out.get('statut'), 'acces_refuse')

    def test_context_snapshot_eleve(self):
        from school_admin.services.assistant_tools import context_snapshot

        snap = context_snapshot(self._ctx())
        self.assertEqual(snap.get('persona'), 'eleve')
        self.assertIn('eleve', snap)


class AssistantEleveParentCrossTests(TestCase):
    """Parent WS ≠ Eleve ; persona parent inchangé."""

    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='Cross Elv0',
            niveau='college',
            code_classe=f'CR-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab, suffix='crs')
        cls.eleve = _make_eleve_simple(cls.etab, cls.classe, 'Sow', 'Awa', suffix='crs')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )

    def test_parent_context_rest_parent(self):
        ctx = build_assistant_context(
            self.etab,
            {'eleve_consulte_id': self.eleve.id},
            parent=self.parent,
            persona='parent',
        )
        self.assertEqual(ctx.persona, 'parent')
        self.assertIsNone(getattr(ctx, 'eleve', None))
        self.assertEqual(ctx.eleve_consulte.id, self.eleve.id)
