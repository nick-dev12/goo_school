"""
Elv6 — parité G1–G7 persona élève (cache, suggestions, pas takeover lectures).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase, TransactionTestCase

from school_admin.model.classe_model import Classe
from school_admin.services.assistant_eleve_tools import suggestions_after_eleve_read
from school_admin.services.assistant_tools import build_assistant_context, enrich_class_snapshot
from school_admin.services.gemini_context_cache import (
    CACHE_DISPLAY_NAME_ELEVE,
    ensure_tools_cache,
    reset_cache_state,
)
from school_admin.tests.test_assistant_directeur_tools import (
    _make_annee,
    _make_eleve_simple,
    _make_etablissement,
)


class AssistantEleveG7SuggestionsTests(SimpleTestCase):
    def test_suggestions_apres_notes(self):
        tool_results = [
            ('get_mes_notes', {'moyenne_generale': 12}),
        ]
        sugg = suggestions_after_eleve_read(tool_results)
        labels = [s.get('label') for s in sugg]
        self.assertIn('Devoirs', labels)

    def test_enrich_class_snapshot_eleve_inchange(self):
        ctx = type('Ctx', (), {'persona': 'eleve'})()
        base = [('get_mes_notes', {'classe': '3e A'})]
        out = enrich_class_snapshot(ctx, base, refs={'classe': '3e A'}, question='effectifs')
        self.assertEqual(out, base)


class AssistantEleveG7CacheTests(SimpleTestCase):
    def tearDown(self):
        reset_cache_state()

    def test_ensure_tools_cache_display_eleve(self):
        captured = {}

        def fake_reuse(system_prompt, model, *, display_name, tools_schema, state, lock):
            captured['display_name'] = display_name
            state['name'] = 'cached-eleve'
            state['model'] = model
            state['fingerprint'] = 'abc'
            state['token_count'] = 42
            return ('cached-eleve', model, 42)

        with patch(
            'school_admin.services.gemini_context_cache.cache_enabled',
            return_value=True,
        ), patch(
            'school_admin.services.gemini_context_cache._reuse_or_create_cache',
            side_effect=fake_reuse,
        ):
            result = ensure_tools_cache(
                'prompt eleve',
                'gemini-test',
                tools_schema=[{'function': {'name': 'get_mon_resume'}}],
                persona='eleve',
                profile='lycee',
            )
        self.assertIsNotNone(result)
        self.assertEqual(captured['display_name'], f'{CACHE_DISPLAY_NAME_ELEVE}-lycee')


class AssistantEleveG7ConsumerTests(TransactionTestCase):
    def setUp(self):
        self.etab = _make_etablissement()
        self.annee = _make_annee(self.etab)
        self.classe = Classe.objects.create(
            nom='Elv6 G7',
            niveau='college',
            code_classe=f'E6G7-{self.etab.pk}',
            capacite_max=30,
            etablissement=self.etab,
        )
        self.eleve = _make_eleve_simple(self.etab, self.classe, 'Ba', 'Moussa', suffix='e6g7')

    def test_lectures_sans_takeover(self):
        from school_admin.consumers.assistant_consumer import AssistantConsumer

        async def _run():
            consumer = AssistantConsumer()
            consumer.scope = {'user': self.eleve, 'session': {}}
            consumer.accept = AsyncMock()
            consumer.close = AsyncMock()
            self.assertTrue(await consumer._resolve_etablissement())
            consumer._reset_turn_stats()
            consumer.pending_action = None
            consumer._persist_pending = AsyncMock()
            consumer._dispatch_navigation = AsyncMock()

            for name in ('get_mes_notes', 'get_mes_absences', 'get_mes_devoirs'):
                stop = await consumer._on_live_tool_result(name, {'message': 'ok'})
                self.assertFalse(stop)
            self.assertIsNone(consumer.pending_action)
            self.assertEqual(consumer._turn_stats['takeover'], 0)
            consumer._persist_pending.assert_not_awaited()

            stop = await consumer._on_live_tool_result(
                'ouvrir_page',
                {'statut': 'ok', 'url': '/eleve/devoirs/', 'ouvrir': True, 'titre': 'Devoirs'},
            )
            self.assertFalse(stop)
            consumer._dispatch_navigation.assert_awaited()

        asyncio.run(_run())
