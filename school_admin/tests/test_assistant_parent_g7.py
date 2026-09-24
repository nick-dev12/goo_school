"""
Par6 — parité G1–G7 persona parent (cache, suggestions, pas de snapshot directeur).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase, TransactionTestCase

from school_admin.model.classe_model import Classe
from school_admin.model.lien_familial_model import LienFamilial
from school_admin.services.assistant_parent_tools import suggestions_after_parent_read
from school_admin.services.assistant_tools import build_assistant_context, enrich_class_snapshot
from school_admin.services.gemini_context_cache import (
    CACHE_DISPLAY_NAME_PARENT,
    ensure_tools_cache,
    reset_cache_state,
)
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)
from school_admin.tests.test_assistant_parent_scope import _make_parent


class AssistantParentG7SuggestionsTests(SimpleTestCase):
    def test_suggestions_notes_et_absences_meme_tour(self):
        tool_results = [
            ('get_notes_enfant', {'eleve_id': 1}),
            ('get_absences_enfant', {'total_absences': 2}),
        ]
        sugg = suggestions_after_parent_read(tool_results)
        labels = [s.get('label') for s in sugg]
        self.assertIn('Devoirs', labels)
        self.assertIn('Scolarité', labels)
        self.assertLessEqual(len(sugg), 3)

    def test_enrich_class_snapshot_parent_inchange(self):
        ctx = type('Ctx', (), {'persona': 'parent'})()
        base = [('get_notes_enfant', {'classe': '3e A'})]
        out = enrich_class_snapshot(
            ctx,
            base,
            refs={'classe': '3e A'},
            question='effectifs de la classe',
        )
        self.assertEqual(out, base)


class AssistantParentG7CacheTests(SimpleTestCase):
    def tearDown(self):
        reset_cache_state()

    def test_ensure_tools_cache_display_parent(self):
        captured = {}

        def fake_reuse(system_prompt, model, *, display_name, tools_schema, state, lock):
            captured['display_name'] = display_name
            state['name'] = 'cached-parent'
            state['model'] = model
            state['fingerprint'] = 'abc'
            state['token_count'] = 42
            return ('cached-parent', model, 42)

        with patch(
            'school_admin.services.gemini_context_cache.cache_enabled',
            return_value=True,
        ), patch(
            'school_admin.services.gemini_context_cache._reuse_or_create_cache',
            side_effect=fake_reuse,
        ):
            result = ensure_tools_cache(
                'prompt parent',
                'gemini-test',
                tools_schema=[{'function': {'name': 'get_mes_enfants'}}],
                persona='parent',
                profile='lycee',
            )
        self.assertIsNotNone(result)
        self.assertEqual(captured['display_name'], f'{CACHE_DISPLAY_NAME_PARENT}-lycee')


class AssistantParentG7ConsumerTests(TransactionTestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(
            nom='Par6 G7',
            niveau='college',
            code_classe=f'P6G7-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.parent = _make_parent(self.etab, suffix='g7')
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Diop', 'Awa', suffix='g7')
        LienFamilial.objects.create(
            parent=self.parent,
            eleve=self.eleve,
            type_lien='mere',
            statut='valide',
            actif=True,
        )

    def test_lectures_parent_sans_takeover_ni_pending(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.parent, 'session': {'eleve_consulte_id': self.eleve.id}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            allowed = await consumer._resolve_etablissement()
            self.assertTrue(allowed)
            consumer._reset_turn_stats()
            consumer.pending_action = None
            consumer._persist_pending = AsyncMock()
            consumer._dispatch_navigation = AsyncMock()

            for name in ('get_notes_enfant', 'get_absences_enfant', 'get_scolarite_enfant'):
                stop = await consumer._on_live_tool_result(
                    name,
                    {'eleve_id': self.eleve.id, 'message': 'ok'},
                )
                self.assertFalse(stop)
            self.assertIsNone(consumer.pending_action)
            self.assertEqual(consumer._turn_stats['takeover'], 0)
            consumer._persist_pending.assert_not_awaited()

            stop = await consumer._on_live_tool_result(
                'creer_publier_annonce',
                {
                    'statut': 'en_attente_confirmation',
                    'titre': 'Test',
                    'contenu': 'X',
                    'destinataires': ['parents'],
                },
            )
            self.assertFalse(stop)
            self.assertIsNone(consumer.pending_action)

        asyncio.run(_run())
