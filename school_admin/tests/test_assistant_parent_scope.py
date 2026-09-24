"""
Tests périmètre assistant parent (Par0).
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.model.parent_model import Parent
from school_admin.services.assistant_parent_scope import (
    assert_eleve_autorise,
    eleve_depuis_session,
    enfants_lies_ids,
    get_eleve_lie,
    resume_enfants,
)
from school_admin.services.assistant_parent_tools import (
    execute_parent_tool,
    get_parent_tools_schema,
)
from school_admin.services.assistant_tools import build_assistant_context, execute_tool
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)


def _make_parent(etab, suffix='1'):
    mat = f'BPP-TEST-{etab.pk}-{suffix}'[:20]
    par = Parent(
        username=mat,
        matricule_parental=mat,
        nom='Diop',
        prenom='Aminata',
        telephone='770000099',
        type_parent='mere',
        etablissement=etab,
        mot_de_passe_provisoire='Test1234',
        email=f'parent.{etab.pk}.{suffix}@aria-test.local',
        actif=True,
    )
    par.set_password('Parent@Test1!')
    par.save()
    return par


class AssistantParentScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.etab = _make_etablissement()
        cls.annee = _make_annee(cls.etab)
        cls.classe = Classe.objects.create(
            nom='2nde Parent',
            niveau='lycee',
            code_classe=f'LYP-{cls.etab.pk}',
            capacite_max=30,
            etablissement=cls.etab,
        )
        cls.parent = _make_parent(cls.etab)
        cls.eleve_lie = _make_eleve_simple(cls.etab, cls.classe, 'Fall', 'Khady', suffix='p1')
        cls.eleve_autre = _make_eleve_simple(cls.etab, cls.classe, 'Sow', 'Ibra', suffix='p2')
        LienFamilial.objects.create(
            parent=cls.parent,
            eleve=cls.eleve_lie,
            type_lien='mere',
            statut='valide',
            actif=True,
        )

    def test_enfants_lies_ids(self):
        ids = enfants_lies_ids(self.parent)
        self.assertIn(self.eleve_lie.id, ids)
        self.assertNotIn(self.eleve_autre.id, ids)

    def test_get_eleve_lie_refuse_non_lie(self):
        self.assertIsNone(get_eleve_lie(self.parent, self.eleve_autre.id))

    def test_eleve_depuis_session(self):
        session = {'eleve_consulte_id': self.eleve_lie.id}
        el = eleve_depuis_session(self.parent, session)
        self.assertEqual(el.id, self.eleve_lie.id)
        session_bad = {'eleve_consulte_id': self.eleve_autre.id}
        self.assertIsNone(eleve_depuis_session(self.parent, session_bad))

    def test_assert_eleve_autorise(self):
        self.assertIsNone(assert_eleve_autorise(self.parent, self.eleve_lie.id))
        denied = assert_eleve_autorise(self.parent, self.eleve_autre.id)
        self.assertEqual(denied.get('statut'), 'acces_refuse')

    def test_resume_enfants(self):
        items = resume_enfants(self.parent)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.eleve_lie.id)

    def test_execute_tool_parent_bloque_directeur(self):
        ctx = build_assistant_context(
            self.etab,
            {},
            parent=self.parent,
            persona='parent',
        )
        out = execute_tool(ctx, 'get_effectifs', {})
        self.assertIn('erreur', out)
        self.assertEqual(out.get('statut'), 'hors_perimetre')

    def test_execute_tool_parent_bloque_eleve_non_lie(self):
        ctx = build_assistant_context(
            self.etab,
            {},
            parent=self.parent,
            persona='parent',
        )
        out = execute_parent_tool(ctx, 'get_resume_enfant', {'eleve_id': self.eleve_autre.id})
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_schema_parent_par2(self):
        ctx = build_assistant_context(
            self.etab,
            {},
            parent=self.parent,
            persona='parent',
        )
        from school_admin.services.gemini_assistant_service import tools_schema_for

        self.assertEqual(len(tools_schema_for(ctx)), 7)
        self.assertEqual(len(get_parent_tools_schema()), 7)

    def test_context_enfant_consulte(self):
        ctx = build_assistant_context(
            self.etab,
            {'eleve_consulte_id': self.eleve_lie.id},
            parent=self.parent,
            persona='parent',
        )
        self.assertEqual(ctx.eleve_consulte.id, self.eleve_lie.id)
        self.assertEqual(len(ctx.enfants_lies), 1)
