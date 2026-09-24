"""
Elv8 — recette multi-types + checklist §10 (automatisée).
"""
from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from school_admin.model.classe_model import Classe
from school_admin.model.etablissement_model import Etablissement
from school_admin.services.assistant_eleve_schema import (
    ELEVE_TOOL_NAMES_ALL,
    build_eleve_tool_schemas,
)
from school_admin.services.assistant_eleve_tools import execute_eleve_tool
from school_admin.services.assistant_parent_language import wolof_marker_score
from school_admin.services.assistant_tools import TOOLS_SCHEMA, build_assistant_context, execute_tool
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
    _make_etablissement_type,
)
from school_admin.tests.test_assistant_eleve_ui_elv1 import (
    ELEVE_EXTRA_PAGES,
    ELEVE_NAV_PAGES,
)

TEMPLATES = Path(settings.BASE_DIR) / 'school_admin' / 'templates' / 'school_admin'

DIRECTOR_TOOLS_SAMPLE = frozenset({
    item['function']['name']
    for item in TOOLS_SCHEMA
    if item.get('function', {}).get('name')
})

DIRECTOR_ONLY = (
    'get_effectifs',
    'get_impayes',
    'get_plan_comptable',
    'enregistrer_paiement',
    'get_caisse',
    'publier_bulletin',
)


def _schema_names(ctx):
    return {
        item['function']['name']
        for item in build_eleve_tool_schemas(ctx)
        if item.get('function')
    }


def _desc(ctx, tool_name):
    for item in build_eleve_tool_schemas(ctx):
        fn = item.get('function') or {}
        if fn.get('name') == tool_name:
            return (fn.get('description') or '').lower()
    return ''


class EleveRecetteElv8Fixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        suffix = str(int(time.time() * 1000))[-8:]
        cls.etab_pri = _make_etablissement_type('primary', f'ep{suffix}')
        cls.etab_col = _make_etablissement()
        cls.annee_pri = _make_annee(cls.etab_pri)
        cls.annee_col = _make_annee(cls.etab_col)

        sup_email = f'sup.elv8.{suffix}@aria-test.local'
        cls.etab_sup = Etablissement(
            username=sup_email,
            email=sup_email,
            nom=f'Université Elv8 {suffix}',
            code_etablissement=f'SE8{suffix}'[:12],
            adresse='1 rue LMD',
            pays='Sénégal',
            ville='Dakar',
            type_etablissement='superieur',
            directeur_prenom='Test',
            directeur_nom='Sup',
            directeur_email=f'dir.{suffix}@aria-test.local',
            module_comptabilite=True,
            actif=True,
        )
        cls.etab_sup.set_password('Vague1@Test1!')
        cls.etab_sup.save()
        cls.annee_sup = _make_annee(cls.etab_sup)

        cls.cl_pri = Classe.objects.create(
            nom='CM1 Elv8',
            niveau='primaire',
            code_classe=f'CM8-{suffix}',
            capacite_max=30,
            etablissement=cls.etab_pri,
        )
        cls.cl_col = Classe.objects.create(
            nom='4eme Elv8',
            niveau='college',
            code_classe=f'C8-{cls.etab_col.pk}',
            capacite_max=30,
            etablissement=cls.etab_col,
        )
        cls.cl_sup = Classe.objects.create(
            nom='L1 Elv8',
            niveau='superieur',
            code_classe=f'L8-{suffix}'[:20],
            capacite_max=40,
            etablissement=cls.etab_sup,
        )

        cls.eleve_pri = _make_eleve_simple(
            cls.etab_pri, cls.cl_pri, 'Diop', 'Awa', suffix=f'p8{suffix}'
        )
        cls.eleve_col = _make_eleve_simple(
            cls.etab_col, cls.cl_col, 'Sow', 'Omar', suffix=f'c8{suffix}'
        )
        cls.eleve_sup = _make_eleve_simple(
            cls.etab_sup, cls.cl_sup, 'Ndiaye', 'Fatou', suffix=f's8{suffix}'
        )

    def _ctx(self, eleve):
        return build_assistant_context(
            eleve.etablissement,
            {},
            eleve=eleve,
            persona='eleve',
        )

    def test_schema_14_tools_sans_directeur(self):
        names = _schema_names(self._ctx(self.eleve_col))
        self.assertEqual(len(names), len(ELEVE_TOOL_NAMES_ALL))
        self.assertTrue(names <= ELEVE_TOOL_NAMES_ALL)
        for forbidden in DIRECTOR_ONLY:
            self.assertNotIn(forbidden, names)
        shared_ok = {'lister_pages', 'ouvrir_page', 'get_annonces', 'get_notifications'}
        director_leak = (names & DIRECTOR_TOOLS_SAMPLE) - shared_ok
        self.assertFalse(director_leak, msg=f'tools directeur: {director_leak}')

    def test_descriptions_adaptees_primaire_et_superieur(self):
        self.assertIn('primaire', _desc(self._ctx(self.eleve_pri), 'get_mes_notes'))
        self.assertIn('supérieur', _desc(self._ctx(self.eleve_sup), 'get_mes_notes'))

    def test_ouvrir_devoirs_url(self):
        out = execute_eleve_tool(self._ctx(self.eleve_col), 'ouvrir_page', {'page_key': 'devoirs'})
        self.assertIn('devoirs', out.get('url', ''))

    def test_scope_refuse_autre_eleve(self):
        out = execute_eleve_tool(
            self._ctx(self.eleve_col),
            'get_mes_notes',
            {'eleve_id': self.eleve_sup.id},
        )
        self.assertEqual(out.get('statut'), 'acces_refuse')

    def test_wolof_marker(self):
        self.assertGreater(wolof_marker_score('Na nga def? Wax ma ci sama notes.'), 0)


class EleveRecetteElv8UiTests(TestCase):
    def test_nav_pages_widget_path(self):
        for rel in ELEVE_NAV_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('bottom_nav_eleve.html', text, msg=rel)

    def test_extra_pages_widget_eleve(self):
        for rel in ELEVE_EXTRA_PAGES:
            text = (TEMPLATES / rel).read_text(encoding='utf-8')
            self.assertIn('assistant_vocal_eleve.html', text, msg=rel)

    def test_bottom_nav_eleve_et_parent(self):
        text = (TEMPLATES / 'eleve/partials/bottom_nav_eleve.html').read_text(encoding='utf-8')
        self.assertIn('assistant_vocal_eleve.html', text)
        self.assertIn('assistant_vocal_parent.html', text)
